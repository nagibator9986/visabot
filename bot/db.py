# db.py
import os
import sqlite3
from pathlib import Path
from dotenv import load_dotenv

# ----------------------------------------------------------------------
# Загрузка переменных окружения из .env
# ----------------------------------------------------------------------
load_dotenv()

# Берём путь к базе из переменной окружения, если нет — дефолт в текущей папке
DB_PATH = os.getenv(
    "LEADS_DB_PATH",
    os.path.join(os.getcwd(), "leads.db")
)

# ----------------------------------------------------------------------
# Убедимся, что директория существует
# ----------------------------------------------------------------------
db_dir = Path(DB_PATH).parent
db_dir.mkdir(parents=True, exist_ok=True)

# ----------------------------------------------------------------------
# Функция получения соединения
# ----------------------------------------------------------------------
def get_connection():
    # Увеличиваем таймаут ожидания блокировки до 20 секунд
    conn = sqlite3.connect(DB_PATH, timeout=20.0)
    conn.row_factory = sqlite3.Row
    
    # 🔥 Включаем WAL-режим для решения проблемы "database is locked"
    # Это позволяет читать и писать в базу одновременно
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    
    return conn

# ----------------------------------------------------------------------
# Вспомогательная функция для проверки колонки
# ----------------------------------------------------------------------
def _column_exists(conn, table_name: str, column_name: str) -> bool:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table_name})")
    cols = [row["name"] for row in cur.fetchall()]
    return column_name in cols

# ----------------------------------------------------------------------
# Инициализация базы и таблиц
# ----------------------------------------------------------------------
def init_db():
    conn = get_connection()
    cur = conn.cursor()

    # ---------- таблица leads ----------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY,
            message_id TEXT,
            conversation_id TEXT,
            from_address TEXT,
            subject TEXT,
            status TEXT,
            visa_country TEXT,
            questionnaire_status TEXT DEFAULT 'none',
            questionnaire_form_id TEXT,
            questionnaire_response_id TEXT,
            last_message_id TEXT,
            last_contacted TEXT,
            next_reminder_at TEXT,
            reminders_sent INTEGER DEFAULT 0,
            form_ack_sent INTEGER DEFAULT 0,
            summary TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """
    )

    # Добавляем недостающие колонки, если их нет (Миграции)
    needed_columns = {
        "visa_country": "TEXT",
        "questionnaire_status": "TEXT DEFAULT 'none'",
        "questionnaire_form_id": "TEXT",
        "questionnaire_response_id": "TEXT",
        "last_message_id": "TEXT",
        "form_ack_sent": "INTEGER DEFAULT 0",
        "summary": "TEXT",  # 🔥 Новое поле для AI-саммари
    }
    
    for col, col_type in needed_columns.items():
        if not _column_exists(conn, "leads", col):
            print(f"Миграция: Добавляем колонку {col} в leads...")
            cur.execute(f"ALTER TABLE leads ADD COLUMN {col} {col_type}")

    # ---------- таблица form_responses ----------
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

    # ---------- таблица audit_log ----------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY,
            lead_id INTEGER,
            event TEXT,
            details TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    if not _column_exists(conn, "audit_log", "details"):
        cur.execute("ALTER TABLE audit_log ADD COLUMN details TEXT")
    
    # ---------- таблица lead_forms ----------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS lead_forms (
            id INTEGER PRIMARY KEY,
            lead_id INTEGER,
            form_type TEXT,
            raw_text TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """
    )

    conn.commit()
    conn.close()

# ----------------------------------------------------------------------
# Для теста
# ----------------------------------------------------------------------
if __name__ == "__main__":
    init_db()
    print("База и таблицы готовы (режим WAL включен):", DB_PATH)