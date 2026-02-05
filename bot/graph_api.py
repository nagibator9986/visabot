import os
import logging
from typing import List, Dict, Any, Optional

import requests
import msal
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("visa_bot.graph")

TENANT_ID = os.getenv("AZURE_TENANT_ID")
CLIENT_ID = os.getenv("AZURE_CLIENT_ID")
CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET")
MAILBOX_UPN = os.getenv("MAILBOX_UPN", "RobotVisa@itplus.kz")
MAILBOX_ID = os.getenv("MAILBOX_ID")

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def _get_authority() -> str:
    if not TENANT_ID or TENANT_ID.lower() == "none":
        raise RuntimeError(
            "AZURE_TENANT_ID не задан. Укажи его в .env или переменных окружения.\n"
            "Пример: AZURE_TENANT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
        )
    return f"https://login.microsoftonline.com/{TENANT_ID}"


SCOPE = ["https://graph.microsoft.com/.default"]

_msal_app: Optional[msal.ConfidentialClientApplication] = None


def _get_msal_app() -> msal.ConfidentialClientApplication:
    global _msal_app
    if _msal_app is not None:
        return _msal_app

    if not CLIENT_ID or not CLIENT_SECRET:
        raise RuntimeError(
            "Не заданы AZURE_CLIENT_ID или AZURE_CLIENT_SECRET. "
            "Проверь .env или переменные окружения."
        )

    authority = _get_authority()
    logger.info("Инициализация MSAL ConfidentialClientApplication с authority=%s", authority)
    _msal_app = msal.ConfidentialClientApplication(
        CLIENT_ID,
        authority=authority,
        client_credential=CLIENT_SECRET,
    )
    return _msal_app


def get_token() -> Optional[str]:
    try:
        app = _get_msal_app()
        result = app.acquire_token_silent(SCOPE, account=None)
        if not result:
            result = app.acquire_token_for_client(scopes=SCOPE)
        if "access_token" not in result:
            logger.error("Не удалось получить токен Graph: %s", result)
            return None
        return result["access_token"]
    except Exception as e:
        logger.exception("Ошибка при получении токена Graph: %s", e)
        return None


def graph_request(
    method: str,
    url: str,
    token: str,
    params: dict | None = None,
    json_data: dict | None = None,
    retries: int = 2,
) -> Optional[requests.Response]:
    headers = {"Authorization": f"Bearer {token}"}
    if json_data is not None:
        headers["Content-Type"] = "application/json"

    for attempt in range(retries + 1):
        try:
            resp = requests.request(
                method,
                url,
                headers=headers,
                params=params,
                json=json_data,
                timeout=30,
            )
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                wait = (attempt + 1) * 2
                logger.warning(
                    "Graph transient %s, retry через %s c (попытка %d/%d)",
                    resp.status_code,
                    wait,
                    attempt + 1,
                    retries + 1,
                )
                import time as _t

                _t.sleep(wait)
                continue
            return resp
        except requests.RequestException as e:
            logger.warning(
                "Ошибка Graph-запроса (попытка %d/%d): %s",
                attempt + 1,
                retries + 1,
                e,
            )
            import time as _t

            _t.sleep(1 + attempt * 2)

    logger.error("Graph запрос провалился после %d попыток: %s %s", retries + 1, method, url)
    return None


def _get_mailbox_identifier() -> str:
    return MAILBOX_UPN if MAILBOX_UPN else MAILBOX_ID


# ---------- Функции работы с почтой ----------

def fetch_unread(token: str, top: int = 30) -> List[Dict[str, Any]]:
    user = _get_mailbox_identifier()
    url = f"{GRAPH_BASE}/users/{user}/mailFolders/Inbox/messages"
    params = {
        "$top": top,
        "$filter": "isRead eq false",
        "$select": "id,subject,from,receivedDateTime,bodyPreview,conversationId",
    }
    r = graph_request("GET", url, token, params=params)
    if r is None:
        return []
    if r.status_code != 200:
        logger.error("Не удалось получить непрочитанные письма: %s %s", r.status_code, r.text)
        return []
    return r.json().get("value", [])


def fetch_thread(token: str, conversation_id: str) -> List[Dict[str, Any]]:
    if not conversation_id:
        return []
    user = _get_mailbox_identifier()
    url = f"{GRAPH_BASE}/users/{user}/mailFolders/Inbox/messages"
    params = {
        "$filter": f"conversationId eq '{conversation_id}'",
        "$orderby": "receivedDateTime asc",
        "$select": "id,subject,from,receivedDateTime,bodyPreview,body,isRead",
    }
    r = graph_request("GET", url, token, params=params)
    if r is None:
        return []
    if r.status_code == 200:
        return r.json().get("value", [])
    if r.status_code == 400 and "InefficientFilter" in (r.text or ""):
        logger.warning("InefficientFilter при загрузке переписки %s — fallback к одному письму", conversation_id)
        return []
    logger.warning("Не удалось получить переписку: %s %s", r.status_code, r.text)
    return []


def send_reply(token: str, message_id: str, html_content: str) -> bool:
    user = _get_mailbox_identifier()
    create_url = f"{GRAPH_BASE}/users/{user}/messages/{message_id}/createReply"
    r = graph_request("POST", create_url, token, json_data={})
    if r is None or r.status_code not in (200, 201):
        logger.error("createReply не удался: %s %s", getattr(r, "status_code", None), getattr(r, "text", None))
        return False

    draft = r.json()
    draft_id = draft.get("id")
    if not draft_id:
        logger.error("createReply вернул пустой id")
        return False

    update_url = f"{GRAPH_BASE}/users/{user}/messages/{draft_id}"
    body_patch = {"body": {"contentType": "HTML", "content": html_content.replace("\n", "<br>")}}
    graph_request("PATCH", update_url, token, json_data=body_patch)

    send_url = f"{GRAPH_BASE}/users/{user}/messages/{draft_id}/send"
    s = graph_request("POST", send_url, token, json_data={})
    if s is not None and s.status_code in (202, 204):
        logger.info("Ответ отправлен для message_id=%s (draft=%s)", message_id, draft_id)
        return True

    logger.error("Ошибка при отправке ответа: %s %s", getattr(s, "status_code", None), getattr(s, "text", None))
    return False


def mark_read_and_tag(token: str, message_id: str, tags: list[str]):
    user = _get_mailbox_identifier()
    url = f"{GRAPH_BASE}/users/{user}/messages/{message_id}"
    patch = {"isRead": True, "categories": tags}
    r = graph_request("PATCH", url, token, json_data=patch)
    if r is None or r.status_code not in (200, 204):
        logger.warning(
            "Не удалось пометить/проставить категории письму %s: %s %s",
            message_id,
            getattr(r, "status_code", None),
            getattr(r, "text", None),
        )


def forward_message(token: str, message_id: str, to_address: str, comment: str = "") -> bool:
    """
    Пересылает (Forward) письмо на указанный адрес.
    """
    user = _get_mailbox_identifier()
    url = f"{GRAPH_BASE}/users/{user}/messages/{message_id}/forward"

    payload = {
        "Comment": comment,
        "ToRecipients": [
            {
                "EmailAddress": {
                    "Address": to_address
                }
            }
        ]
    }

    r = graph_request("POST", url, token, json_data=payload)
    
    if r is not None and r.status_code in (200, 202, 204):
        logger.info("Сообщение %s успешно переслано на %s", message_id, to_address)
        return True

    logger.error(
        "Ошибка при пересылке (forward) сообщения: %s %s",
        getattr(r, "status_code", None),
        getattr(r, "text", None),
    )
    return False


def send_mail(token: str, to_address: str, subject: str, html_content: str) -> bool:
    """
    Отправить НОВОЕ письмо (не reply) от нашего почтового ящика на указанный адрес.
    """
    user = _get_mailbox_identifier()
    url = f"{GRAPH_BASE}/users/{user}/sendMail"

    payload = {
        "message": {
            "subject": subject,
            "body": {
                "contentType": "HTML",
                "content": html_content,
            },
            "toRecipients": [
                {"emailAddress": {"address": to_address}}
            ],
        },
        "saveToSentItems": True,
    }

    r = graph_request("POST", url, token, json_data=payload)
    if r is not None and r.status_code in (200, 202):
        logger.info("Отправлено новое письмо на %s (subject=%s)", to_address, subject)
        return True

    logger.error(
        "Ошибка при отправке нового письма: %s %s",
        getattr(r, "status_code", None),
        getattr(r, "text", None),
    )
    return False