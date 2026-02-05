# google_forms_sync.py
import os
import json
import logging
from datetime import datetime

from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import db  # твой db.py

load_dotenv()

logger = logging.getLogger("visa_bot.forms_sync")
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

# --- Google Forms API config ---
SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "credentials.json")

SCOPES = [
    "https://www.googleapis.com/auth/forms.responses.readonly",
]

FORM_POLAND_ID = os.getenv("FORM_POLAND_ID")      # ID формы для Польши
FORM_SCHENGEN_ID = os.getenv("FORM_SCHENGEN_ID")  # ID формы для Шенгена
FORM_USA_ID = os.getenv("FORM_USA_ID")            # ID формы для США


def get_forms_service():
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        raise RuntimeError(f"Файл сервисного аккаунта не найден: {SERVICE_ACCOUNT_FILE}")

    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=SCOPES,
    )
    service = build("forms", "v1", credentials=creds)
    return service


def _ensure_form_responses_table(conn):
    """
    На всякий случай — создаём таблицу form_responses, если её ещё нет.
    (Она уже есть в db.init_db, но лишний раз не помешает.)
    """
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


def _extract_email_from_answers(answers: dict) -> str | None:
    """
    Примитивная попытка вытащить e-mail из ответов:
    - ищем текст, в котором встречается '@'.
    """
    if not answers:
        return None

    for answer in answers.values():
        text_answers = answer.get("textAnswers", {}).get("answers", [])
        for ta in text_answers:
            value = ta.get("value") or ""
            value = value.strip()
            if "@" in value and "." in value:
                return value
    return None


def _find_lead_id_for_email(conn, email: str | None) -> int | None:
    """
    Пытаемся найти лид в таблице leads по адресу электронной почты.
    Берём последний по created_at.
    """
    if not email:
        return None

    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, from_address
        FROM leads
        WHERE lower(from_address) = lower(?)
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (email,),
    )
    row = cur.fetchone()
    if not row:
        return None
    return row["id"]


def sync_form_responses_for_form(service, form_id: str, visa_country: str) -> int:
    """
    Синхронизируем одну форму:
    - читаем все responses
    - пишем в form_responses
    - пытаемся привязать к lead_id по email
    Возвращает количество новых сохранённых ответов.
    """
    if not form_id:
        return 0

    logger.info("Синхронизация ответов Google Form form_id=%s (visa_country=%s)", form_id, visa_country)

    conn = db.get_connection()
    _ensure_form_responses_table(conn)
    cur = conn.cursor()

    saved_count = 0
    page_token = None

    while True:
        try:
            req = service.forms().responses().list(
                formId=form_id,
                pageToken=page_token
            )
            resp = req.execute()
        except HttpError as e:
            logger.error("Ошибка при чтении ответов формы %s: %s", form_id, e)
            break

        responses = resp.get("responses", [])
        logger.info("Получено %d ответов (порция)", len(responses))

        for r in responses:
            response_id = r.get("responseId")
            answers = r.get("answers", {})
            create_time = r.get("createTime")  # ISO-строка от Google

            # Уже существует?
            cur.execute("SELECT id FROM form_responses WHERE response_id = ?", (response_id,))
            if cur.fetchone():
                continue  # пропускаем уже сохранённое

            respondent_email = _extract_email_from_answers(answers)
            lead_id = _find_lead_id_for_email(conn, respondent_email)

            raw_json = json.dumps(r, ensure_ascii=False)
            created_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

            cur.execute(
                """
                INSERT INTO form_responses (lead_id, visa_country, form_id, response_id, respondent_email, raw_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (lead_id, visa_country, form_id, response_id, respondent_email, raw_json, created_at),
            )
            conn.commit()
            saved_count += 1

            logger.info(
                "Сохранён ответ формы: response_id=%s, email=%s, lead_id=%s",
                response_id,
                respondent_email,
                lead_id,
            )

        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    conn.close()
    logger.info("Форма %s: сохранено новых ответов: %d", form_id, saved_count)
    return saved_count


def main():
    service = get_forms_service()

    total = 0

    if FORM_POLAND_ID:
        total += sync_form_responses_for_form(service, FORM_POLAND_ID, "poland")

    if FORM_SCHENGEN_ID:
        total += sync_form_responses_for_form(service, FORM_SCHENGEN_ID, "schengen")

    if FORM_USA_ID:
        total += sync_form_responses_for_form(service, FORM_USA_ID, "usa")

    logger.info("Готово. Всего новых ответов по всем формам: %d", total)


if __name__ == "__main__":
    main()
