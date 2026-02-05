# google_forms_sync.py
import os
import re
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from graph_api import send_mail, get_token
import db
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import requests

from models import AuditLog, Lead

load_dotenv()

# ----------------------------------------------------------------------
#  ЛОГГЕР
# ----------------------------------------------------------------------
logger = logging.getLogger("visa_bot.forms_sync")
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")

# ----------------------------------------------------------------------
#  GOOGLE FORMS API CONFIG
# ----------------------------------------------------------------------
SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "google-services.json")

SCOPES = [
    "https://www.googleapis.com/auth/forms.responses.readonly",
    "https://www.googleapis.com/auth/forms.body.readonly",
]

FORM_POLAND_ID = os.getenv("FORM_POLAND_ID")
FORM_SCHENGEN_ID = os.getenv("FORM_SCHENGEN_ID")
FORM_USA_ID = os.getenv("FORM_USA_ID")

# ----------------------------------------------------------------------
#  DJANGO / EMAIL НАСТРОЙКИ ДЛЯ ВАЛИДАЦИИ
# ----------------------------------------------------------------------
DJANGO_API_BASE = os.getenv("DJANGO_API_BASE", "http://localhost:8000/api")

BOT_SENDER_EMAIL = os.getenv("BOT_SENDER_EMAIL", "visa@bcdtravel.kz")


def send_email(to_email: str, subject: str, body: str) -> None:
    """
    Реальная отправка письма через Graph API.
    """
    token = get_token()
    if not token:
        logger.error("[EMAIL] Не удалось получить токен для отправки письма на %s", to_email)
        return

    html_body = body.replace("\n", "<br>")
    
    success = send_mail(token, to_email, subject, html_body)
    
    if success:
        logger.info("[EMAIL] Письмо успешно отправлено на %s", to_email)
    else:
        logger.error("[EMAIL] Ошибка отправки письма на %s", to_email)


def validate_and_notify(form_response_id: int, respondent_email: Optional[str]) -> None:
    """
    1) Вызывает Django-эндпоинт /api/form-responses/{id}/validate/
    2) По результату отправляет пользователю письмо
    """
    if not respondent_email:
        logger.info(
            "[VALIDATION] form_response_id=%s: нет email респондента, письмо не шлём",
            form_response_id,
        )
        return

    url = f"{DJANGO_API_BASE}/form-responses/{form_response_id}/validate/"

    try:
        resp = requests.post(url, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        logger.error(
            "[VALIDATION] Ошибка при запросе %s: %s",
            url,
            e,
        )
        return

    try:
        data = resp.json()
    except Exception as e:
        logger.error(
            "[VALIDATION] Не удалось распарсить JSON от %s: %s",
            url,
            e,
        )
        return

    is_valid = data.get("is_valid", False)
    errors = data.get("errors") or []
    warnings = data.get("warnings") or []

    # ----- Вариант 1: всё ок -----
    if is_valid and not errors:
        subject = "Анкета принята и успешно проверена"
        body = (
            "Здравствуйте!\n\n"
            "Спасибо, что заполнили анкету для оформления визы.\n"
            "Мы проверили ваши данные — критических ошибок не обнаружено.\n\n"
            "Мы приступаем к дальнейшей обработке вашего запроса.\n\n"
            "С уважением,\n"
            "BCD TRAVEL Казахстан\n"
            f"{BOT_SENDER_EMAIL}\n"
        )
        send_email(respondent_email, subject, body)
        logger.info(
            "[VALIDATION] form_response_id=%s: анкета валидна, письмо 'всё ок' отправлено",
            form_response_id,
        )
        return

    # ----- Вариант 2: есть ошибки -----
    errors_text = "\n".join(
        f"- {e.get('field_label')}: {e.get('message')}"
        for e in errors
    ) or "Мы обнаружили несколько неточностей в данных."

    warnings_text = ""
    if warnings:
        warnings_text = "\n\nДополнительно рекомендуем проверить:\n" + "\n".join(
            f"- {w.get('field_label')}: {w.get('message')}"
            for w in warnings
        )

    subject = "Проверьте, пожалуйста, данные анкеты"
    body = (
        "Здравствуйте!\n\n"
        "Спасибо, что заполнили анкету для оформления визы.\n\n"
        "При проверке мы обнаружили следующие ошибки в данных:\n"
        f"{errors_text}"
        f"{warnings_text}\n\n"
        "Пожалуйста, исправьте эти данные и отправьте форму повторно,\n"
        "либо ответьте на это письмо с корректной информацией.\n\n"
        "Если у вас возникнут вопросы — просто ответьте на это письмо.\n\n"
        "С уважением,\n"
        "BCD TRAVEL Казахстан\n"
        f"{BOT_SENDER_EMAIL}\n"
    )

    send_email(respondent_email, subject, body)
    logger.info(
        "[VALIDATION] form_response_id=%s: анкета с ошибками, письмо с ошибками отправлено",
        form_response_id,
    )


def get_forms_service():
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        raise RuntimeError(
            f"Файл сервисного аккаунта не найден: {SERVICE_ACCOUNT_FILE}"
        )

    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    service = build("forms", "v1", credentials=creds)
    return service


def _ensure_form_responses_table(conn):
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS form_responses (
            id INTEGER PRIMARY KEY,
            lead_id INTEGER,
            visa_country TEXT,
            form_id TEXT,
            response_id TEXT UNIQUE,
            respondent_email TEXT,
            raw_json TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.commit()


def _find_lead_id_for_email(conn, email: Optional[str]) -> Optional[int]:
    if not email:
        return None

    email_norm = email.strip().lower()
    if not email_norm:
        return None

    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, from_address, created_at
        FROM leads
        WHERE lower(trim(from_address)) = ?
        ORDER BY datetime(COALESCE(created_at, '1970-01-01')) DESC, id DESC
        LIMIT 1
        """,
        (email_norm,),
    )
    row = cur.fetchone()
    if not row:
        logger.info(
            "[LEAD MATCH] Лид по email '%s' не найден в таблице leads",
            email_norm,
        )
        return None

    logger.info(
        "[LEAD MATCH] Нашли lead_id=%s для email='%s'",
        row["id"],
        email_norm,
    )
    return row["id"]


def _map_visa_country_for_lead(visa_country: Optional[str]) -> Optional[str]:
    if not visa_country:
        return None
    vc = visa_country.lower()
    if vc == "poland":
        return "PL"
    if vc == "schengen":
        return "SCHENGEN"
    if vc == "usa":
        return "US"
    return None


def _mark_lead_questionnaire_filled(
    conn,
    lead_id: Optional[int],
    visa_country: Optional[str],
    response_id: str,
):
    if not lead_id:
        return

    visa_country_code = _map_visa_country_for_lead(visa_country)

    logger.info(
        "[LEAD UPDATE] Обновляем lead_id=%s: questionnaire_status='filled', "
        "questionnaire_response_id='%s', visa_country='%s'",
        lead_id,
        response_id,
        visa_country_code,
    )

    cur = conn.cursor()
    cur.execute(
        """
        UPDATE leads
        SET
            questionnaire_status = 'filled',
            questionnaire_response_id = COALESCE(questionnaire_response_id, ?),
            visa_country = COALESCE(visa_country, ?)
        WHERE id = ?
        """,
        (response_id, visa_country_code, lead_id),
    )
    conn.commit()

    try:
        AuditLog.log(
            lead_id=lead_id,
            event="questionnaire_filled",
            details=(
                f"Form response synced from Google Forms, "
                f"response_id={response_id}, visa_country={visa_country}"
            ),
        )
    except Exception as e:
        logger.warning(
            "Не удалось записать AuditLog для lead_id=%s: %s", lead_id, e
        )


def _build_questions_index(service, form_id: str) -> Dict[str, str]:
    if not form_id:
        return {}

    try:
        form = service.forms().get(formId=form_id).execute()
    except HttpError as e:
        logger.error("Не удалось получить структуру формы %s: %s", form_id, e)
        return {}

    index: Dict[str, str] = {}

    def walk_items(items: list) -> None:
        for item in items or []:
            question_item = item.get("questionItem")
            if question_item:
                question = (question_item.get("question") or {}) if isinstance(
                    question_item, dict
                ) else {}
                qid = question.get("questionId")
                title = (
                    item.get("title")
                    or question.get("title")
                    or qid
                )
                if qid and title:
                    index[qid] = str(title)

            nested = item.get("items")
            if isinstance(nested, list) and nested:
                walk_items(nested)

    walk_items(form.get("items", []))
    return index


def _extract_email_from_answers_raw(answers_raw: Dict[str, Any]) -> Optional[str]:
    if not answers_raw:
        return None

    # textAnswers
    for ans in answers_raw.values():
        if not isinstance(ans, dict):
            continue
        text_block = ans.get("textAnswers") or {}
        arr = text_block.get("answers") or []
        for item in arr:
            if not isinstance(item, dict):
                continue
            value = (item.get("value") or "").strip()
            if value and EMAIL_RE.search(value):
                return value

    # choiceAnswers
    for ans in answers_raw.values():
        if not isinstance(ans, dict):
            continue
        choice_block = ans.get("choiceAnswers") or {}
        values = choice_block.get("values") or []
        for v in values:
            s = str(v).strip()
            if s and EMAIL_RE.search(s):
                return s

    return None


# ----------------------------------------------------------------------
#  🔥 НОВАЯ ФУНКЦИЯ ДЛЯ ПОИСКА LEAD ID (Шаг 4)
# ----------------------------------------------------------------------
def _extract_lead_id_from_answers(answers_raw: Dict[str, Any], questions_index: Dict[str, str]) -> Optional[int]:
    """
    Ищет ответ на вопрос "LeadID" (или похожий) и возвращает ID.
    Решает проблему "зомби-ссылок", когда email в форме отличается от email в переписке.
    """
    if not answers_raw: return None

    for qid, ans in answers_raw.items():
        # Получаем название вопроса
        question_title = questions_index.get(qid, "").lower()
        
        # Ищем вопрос, в названии которого есть 'leadid', 'lead id' или 'lead_id'
        # Это поле должно быть добавлено в Google Form (можно скрытым)
        if "leadid" in question_title or "lead_id" in question_title or "lead id" in question_title:
            text_block = ans.get("textAnswers") or {}
            arr = text_block.get("answers") or []
            if arr:
                val = arr[0].get("value", "").strip()
                if val and val.isdigit():
                    return int(val)
    return None


def _normalize_response_payload(
    response: Dict[str, Any],
    questions_index: Dict[str, str],
) -> Dict[str, Any]:
    answers_raw = response.get("answers") or {}
    norm_answers: Dict[str, Dict[str, Any]] = {}

    for qid, ans in answers_raw.items():
        if not isinstance(ans, dict):
            norm_answers[str(qid)] = {
                "label": questions_index.get(str(qid), str(qid)),
                "value": str(ans),
            }
            continue

        label = (
            questions_index.get(qid)
            or ans.get("questionTitle")
            or qid
        )

        value = ""
        files: list[dict[str, str]] = []

        # ---- textAnswers ----
        text_block = ans.get("textAnswers")
        if isinstance(text_block, dict):
            arr = text_block.get("answers") or []
            texts: list[str] = []
            for item in arr:
                if not isinstance(item, dict):
                    continue
                v = (item.get("value") or "").strip()
                if v:
                    texts.append(v)
            if texts:
                value = "; ".join(texts)

        # ---- choiceAnswers ----
        if not value:
            choice_block = ans.get("choiceAnswers")
            if isinstance(choice_block, dict):
                values = choice_block.get("values") or []
                if values:
                    value = "; ".join(str(v) for v in values if v)

        # ---- dateAnswers ----
        if not value:
            date_block = ans.get("dateAnswers")
            if isinstance(date_block, dict):
                arr = date_block.get("answers") or []
                parts: list[str] = []
                for d in arr:
                    if not isinstance(d, dict):
                        continue
                    y = d.get("year")
                    m = d.get("month")
                    day = d.get("day")
                    if y or m or day:
                        parts.append(
                            f"{y or ''}-"
                            f"{str(m or '').zfill(2) if m else ''}-"
                            f"{str(day or '').zfill(2) if day else ''}".strip("-")
                        )
                if parts:
                    value = "; ".join(parts)

        # ---- fileUploadAnswers ----
        file_block = ans.get("fileUploadAnswers")
        if isinstance(file_block, dict):
            f_arr = file_block.get("answers") or []
            file_names: list[str] = []
            for f in f_arr:
                if not isinstance(f, dict):
                    continue
                fid = f.get("fileId")
                fname = f.get("fileName") or fid or ""
                if not fid:
                    continue

                drive_url = f"https://drive.google.com/file/d/{fid}/view"
                files.append(
                    {
                        "fileId": fid,
                        "fileName": fname,
                        "driveUrl": drive_url,
                    }
                )
                file_names.append(fname)

            if file_names:
                if value:
                    value = value + "; " + "; ".join(file_names)
                else:
                    value = "; ".join(file_names)

        if not value:
            value = json.dumps(ans, ensure_ascii=False)

        entry: Dict[str, Any] = {
            "label": str(label),
            "value": value,
        }
        if files:
            entry["files"] = files

        norm_answers[str(qid)] = entry

    meta = {
        "response_id": response.get("responseId"),
        "create_time": response.get("createTime"),
        "last_submitted_time": response.get("lastSubmittedTime"),
    }

    return {
        "meta": meta,
        "answers": norm_answers,
    }


def sync_form_responses_for_form(service, form_id: str, visa_country: str) -> int:
    if not form_id:
        logger.warning(
            "sync_form_responses_for_form вызван с пустым form_id (visa_country=%s)",
            visa_country,
        )
        return 0

    logger.info(
        "Синхронизация ответов Google Form form_id=%s (visa_country=%s)",
        form_id,
        visa_country,
    )

    conn = db.get_connection()
    _ensure_form_responses_table(conn)
    cur = conn.cursor()

    questions_index = _build_questions_index(service, form_id)

    saved_count = 0
    page_token: str | None = None

    while True:
        try:
            req = service.forms().responses().list(
                formId=form_id,
                pageToken=page_token,
            )
            resp = req.execute()
        except HttpError as e:
            logger.error("Ошибка при чтении ответов формы %s: %s", form_id, e)
            break

        responses = resp.get("responses", []) or []
        logger.info(
            "Получено %d ответов (порция) для формы %s",
            len(responses),
            form_id,
        )

        for r in responses:
            response_id = r.get("responseId")
            if not response_id:
                continue

            answers_raw = r.get("answers") or {}
            respondent_email = _extract_email_from_answers_raw(answers_raw)
            
            # 🔥 1. Пытаемся найти Lead ID явно (Пункт 2 - решение зомби-ссылок)
            lead_id = _extract_lead_id_from_answers(answers_raw, questions_index)
            
            # Проверяем, существует ли лид с таким ID (защита от мусорных данных)
            if lead_id:
                cur.execute("SELECT id FROM leads WHERE id = ?", (lead_id,))
                if not cur.fetchone():
                    logger.warning(f"Found explicit LEAD_ID={lead_id}, but no such lead in DB. Falling back to email.")
                    lead_id = None
                else:
                    logger.info(f"✅ Found explicit LEAD_ID={lead_id} in form response! Ignoring email mismatch.")

            # 🔥 2. Если ID не найден, ищем по Email (старая логика)
            if not lead_id:
                lead_id = _find_lead_id_for_email(conn, respondent_email)

            # Проверка на существование ответа в БД
            cur.execute(
                "SELECT id, lead_id FROM form_responses WHERE response_id = ?",
                (response_id,),
            )
            existing = cur.fetchone()
            
            if existing:
                # Бэкфилл: если раньше лида не было, а теперь нашли (или появился новый Lead ID)
                if existing["lead_id"] is None and lead_id:
                     cur.execute(
                        "UPDATE form_responses SET lead_id = ? WHERE id = ?",
                        (lead_id, existing["id"]),
                    )
                     conn.commit()
                     logger.info(f"[BACKFILL] Linked existing response {existing['id']} to lead {lead_id}")
                     _mark_lead_questionnaire_filled(conn, lead_id, visa_country, response_id)
                continue

            # Если лида нет ни по ID, ни по Email, но есть Email — создаём нового
            if not lead_id and respondent_email:
                try:
                    new_lead = Lead(
                        id=None,
                        message_id=f"form:{response_id}",
                        conversation_id=None,
                        from_address=respondent_email,
                        subject="Анкета на визу (Google Forms)",
                        status="questionnaire_filled",
                        visa_country=_map_visa_country_for_lead(visa_country),
                        questionnaire_status="filled",
                        questionnaire_form_id=form_id,
                        questionnaire_response_id=response_id,
                        last_message_id=None,
                        last_contacted=None,
                        next_reminder_at=None,
                        reminders_sent=0,
                        form_ack_sent=0,
                        summary=None
                    )
                    new_lead.save()
                    lead_id = new_lead.id
                    logger.info(f"[LEAD CREATE] Created new lead {lead_id} from form response email {respondent_email}")
                except Exception as e:
                    logger.error(f"Failed to create lead from form: {e}")

            # Сохранение ответа
            normalized_payload = _normalize_response_payload(r, questions_index)
            raw_json = json.dumps(normalized_payload, ensure_ascii=False)
            created_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

            cur.execute(
                """
                INSERT INTO form_responses (
                    lead_id,
                    visa_country,
                    form_id,
                    response_id,
                    respondent_email,
                    raw_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lead_id,
                    visa_country,
                    form_id,
                    response_id,
                    respondent_email,
                    raw_json,
                    created_at,
                ),
            )
            conn.commit()
            saved_count += 1
            form_response_id = cur.lastrowid

            logger.info(f"[DB] Saved form response id={form_response_id}, lead_id={lead_id}")

            if lead_id:
                _mark_lead_questionnaire_filled(conn, lead_id, visa_country, response_id)

            try:
                validate_and_notify(form_response_id, respondent_email)
            except Exception as e:
                logger.error(f"[VALIDATION] Error: {e}")

        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    conn.close()
    logger.info("Форма %s: сохранено новых ответов: %d", form_id, saved_count)
    return saved_count


def sync_all_forms() -> int:
    try:
        service = get_forms_service()
    except Exception as e:
        logger.error("Не удалось инициализировать Google Forms service: %s", e)
        return 0

    total = 0
    if FORM_POLAND_ID:
        total += sync_form_responses_for_form(service, FORM_POLAND_ID, "poland")
    if FORM_SCHENGEN_ID:
        total += sync_form_responses_for_form(service, FORM_SCHENGEN_ID, "schengen")
    if FORM_USA_ID:
        total += sync_form_responses_for_form(service, FORM_USA_ID, "usa")

    if total > 0:
        logger.info("Синхронизация форм завершена, новых ответов: %d", total)
    return total


def main():
    sync_all_forms()


if __name__ == "__main__":
    main()