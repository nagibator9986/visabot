import os
import sqlite3
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, List
import pytz  # 🔥 pip install pytz

logger = logging.getLogger("visa_bot.models")

# Убедимся, что путь к БД совпадает с Бэкендом
DB_PATH = os.getenv("LEADS_DB_PATH", os.path.join(os.getcwd(), "leads.db"))

# 🔥 Настройка таймзон (Казахстан)
LOCAL_TZ = pytz.timezone('Asia/Qyzylorda') 
UTC_TZ = pytz.UTC

# ---------- Вспомогательные функции по дате ----------

def get_local_now() -> datetime:
    """Текущее время в локальной таймзоне"""
    return datetime.now(LOCAL_TZ)

def is_working_hours() -> bool:
    """
    Проверка тихих часов.
    Возвращает True, если сейчас рабочее время (например, 09:00 - 21:00)
    """
    now = get_local_now()
    return 9 <= now.hour < 22

def dt_to_str(dt: Optional[datetime]) -> Optional[str]:
    """
    datetime -> строка 'YYYY-MM-DD HH:MM:SS'.
    Если dt имеет таймзону, переводим в UTC и убираем tzinfo перед записью,
    так как в БД храним UTC-время без смещения.
    """
    if dt is None:
        return None
    
    # Если дата с таймзоной, приводим к UTC
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC_TZ)
        
    return dt.replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")


def str_to_dt(s: Optional[str]) -> Optional[datetime]:
    """
    Строка из БД (UTC) -> datetime (naive UTC).
    """
    if not s:
        return None
    s = s.strip()

    if "T" in s:
        s = s.replace("T", " ")
        if "+" in s:
            s = s.split("+", 1)[0]
        if "Z" in s:
            s = s.replace("Z", "")

    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            return datetime.fromisoformat(s)
        except Exception:
            logger.warning("Не удалось распарсить дату: %r", s)
            return None


# ---------- Соединение с БД ----------

def get_connection() -> sqlite3.Connection:
    # Здесь тоже используем таймаут и WAL для надежности, если импортируют отсюда
    conn = sqlite3.connect(DB_PATH, timeout=20.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn

# ---------- Модель Lead ----------

@dataclass
class Lead:
    id: Optional[int]
    message_id: str
    conversation_id: Optional[str]
    from_address: Optional[str]
    subject: Optional[str]
    status: str

    # --- поля по визам / анкетам ---
    visa_country: Optional[str] = None
    questionnaire_status: str = "none"
    questionnaire_form_id: Optional[str] = None
    questionnaire_response_id: Optional[str] = None
    last_message_id: Optional[str] = None

    # --- напоминания / тайминги ---
    last_contacted: Optional[datetime] = None
    next_reminder_at: Optional[datetime] = None
    reminders_sent: int = 0

    # --- служебный флаг ---
    form_ack_sent: int = 0
    
    # 🔥 --- AI Context ---
    summary: Optional[str] = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Lead":
        cols = set(row.keys())
        return cls(
            id=row["id"],
            message_id=row["message_id"],
            conversation_id=row["conversation_id"],
            from_address=row["from_address"],
            subject=row["subject"],
            status=row["status"] or "new",
            visa_country=row["visa_country"] if "visa_country" in cols else None,
            questionnaire_status=row["questionnaire_status"] if "questionnaire_status" in cols else "none",
            questionnaire_form_id=row["questionnaire_form_id"] if "questionnaire_form_id" in cols else None,
            questionnaire_response_id=row["questionnaire_response_id"] if "questionnaire_response_id" in cols else None,
            last_message_id=row["last_message_id"] if "last_message_id" in cols else None,
            last_contacted=str_to_dt(row["last_contacted"]),
            next_reminder_at=str_to_dt(row["next_reminder_at"]),
            reminders_sent=row["reminders_sent"] or 0,
            form_ack_sent=row["form_ack_sent"] if "form_ack_sent" in cols and row["form_ack_sent"] is not None else 0,
            summary=row["summary"] if "summary" in cols else None,
        )
    
    @classmethod
    def create(cls, from_address: str, conversation_id: str, subject: str = None, initial_intent: str = None) -> "Lead":
        status = "new"
        if initial_intent == "want_apply":
            status = "questionnaire_sent"
        elif initial_intent == "info_request":
            status = "info_provided"
            
        now = datetime.utcnow()
        temp_msg_id = f"gen_{int(now.timestamp())}"
        
        lead = cls(
            id=None,
            message_id=temp_msg_id,
            conversation_id=conversation_id,
            from_address=from_address,
            subject=subject or "No Subject",
            status=status,
            visa_country=None,
            questionnaire_status="none",
            last_contacted=now,
            next_reminder_at=None,
            reminders_sent=0,
            summary=None
        )
        lead.save()
        logger.info(f"Created new Lead ID={lead.id} for {from_address}")
        return lead

    def save(self):
        conn = get_connection()
        cur = conn.cursor()

        if self.id:
            cur.execute("SELECT id FROM leads WHERE id = ?", (self.id,))
            row = cur.fetchone()
        elif self.message_id:
            cur.execute("SELECT id FROM leads WHERE message_id = ?", (self.message_id,))
            row = cur.fetchone()
        else:
            row = None

        if row:
            # UPDATE
            if not self.id:
                self.id = row["id"]

            cur.execute(
                """
                UPDATE leads
                SET
                    conversation_id           = ?,
                    from_address              = ?,
                    subject                   = ?,
                    status                    = ?,
                    visa_country              = ?,
                    questionnaire_status      = ?,
                    questionnaire_form_id     = ?,
                    questionnaire_response_id = ?,
                    last_message_id           = ?,
                    last_contacted            = ?,
                    next_reminder_at          = ?,
                    reminders_sent            = ?,
                    form_ack_sent             = ?,
                    summary                   = ?
                WHERE id = ?
                """,
                (
                    self.conversation_id,
                    self.from_address,
                    self.subject,
                    self.status,
                    self.visa_country,
                    self.questionnaire_status,
                    self.questionnaire_form_id,
                    self.questionnaire_response_id,
                    self.last_message_id,
                    dt_to_str(self.last_contacted),
                    dt_to_str(self.next_reminder_at),
                    self.reminders_sent,
                    self.form_ack_sent,
                    self.summary,
                    self.id,
                ),
            )
        else:
            # INSERT
            cur.execute(
                """
                INSERT INTO leads (
                    message_id,
                    conversation_id,
                    from_address,
                    subject,
                    status,
                    visa_country,
                    questionnaire_status,
                    questionnaire_form_id,
                    questionnaire_response_id,
                    last_message_id,
                    last_contacted,
                    next_reminder_at,
                    reminders_sent,
                    form_ack_sent,
                    summary
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.message_id,
                    self.conversation_id,
                    self.from_address,
                    self.subject,
                    self.status,
                    self.visa_country,
                    self.questionnaire_status,
                    self.questionnaire_form_id,
                    self.questionnaire_response_id,
                    self.last_message_id,
                    dt_to_str(self.last_contacted),
                    dt_to_str(self.next_reminder_at),
                    self.reminders_sent,
                    self.form_ack_sent,
                    self.summary,
                ),
            )
            self.id = cur.lastrowid

        conn.commit()
        conn.close()

    # ----- выборки -----

    @classmethod
    def get_by_id(cls, lead_id: int) -> Optional["Lead"]:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        return cls.from_row(row)

    @classmethod
    def get_by_conversation(cls, conversation_id: str) -> Optional["Lead"]:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM leads WHERE conversation_id = ?", (conversation_id,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        return cls.from_row(row)
        
    @classmethod
    def get_by_email(cls, email: str) -> Optional["Lead"]:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM leads WHERE from_address = ? ORDER BY id DESC LIMIT 1", (email,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        return cls.from_row(row)

    @classmethod
    def get_by_message(cls, message_id: str) -> Optional["Lead"]:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM leads WHERE message_id = ?", (message_id,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        return cls.from_row(row)

    @classmethod
    def get_due_reminders(cls) -> List["Lead"]:
        """
        Возвращает лидов, для которых пора отправить follow-up.
        Сравниваем UTC сейчас с UTC в базе.
        """
        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT * FROM leads
            WHERE next_reminder_at IS NOT NULL
              AND next_reminder_at <= ?
              AND status != 'closed'
            """,
            (now_str,),
        )
        rows = cur.fetchall()
        conn.close()
        return [cls.from_row(r) for r in rows]

    # ----- статусы / напоминания -----

    def mark_closed(self):
        old_status = self.status
        self.status = "closed"
        self.next_reminder_at = None
        self.save()
        AuditLog.log(self.id, "status_change", f"{old_status} -> closed")
        
    def mark_form_ack_sent(self):
        self.form_ack_sent = 1
        self.save()
        AuditLog.log(self.id, "form_ack_sent", "Confirmation email sent")

    def schedule_first_reminder(self, days: int):
        """Планируем напоминание на утро (10:00) через N дней"""
        local_now = get_local_now()
        next_date = local_now + timedelta(days=days)
        # Ставим на 10 утра по местному времени
        next_date = next_date.replace(hour=10, minute=0, second=0, microsecond=0)
        
        # Сохраняем (save() сам сконвертирует в UTC)
        self.next_reminder_at = next_date
        self.save()
        AuditLog.log(self.id, "schedule_first_reminder", f"next in {days} days (at 10:00 Local)")

    def schedule_next_reminder(self, days: int):
        """Планируем следующее напоминание на утро (10:00)"""
        self.reminders_sent += 1
        
        local_now = get_local_now()
        next_date = local_now + timedelta(days=days)
        next_date = next_date.replace(hour=10, minute=0, second=0, microsecond=0)
        
        self.next_reminder_at = next_date
        self.save()
        AuditLog.log(
            self.id,
            "schedule_next_reminder",
            f"reminders_sent={self.reminders_sent}, next in {days} days (at 10:00 Local)",
        )

    def stop_reminders(self):
        self.next_reminder_at = None
        self.save()
        AuditLog.log(self.id, "stop_reminders", "reminders disabled")


# ---------- Модель AuditLog ----------

@dataclass
class AuditLog:
    id: Optional[int]
    lead_id: Optional[int]
    event: str
    details: Optional[str]
    created_at: Optional[datetime] = None

    def save(self):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO audit_log (lead_id, event, details, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                self.lead_id,
                self.event,
                self.details,
                dt_to_str(self.created_at or datetime.utcnow()),
            ),
        )
        conn.commit()
        cur.execute("SELECT last_insert_rowid() AS id")
        row = cur.fetchone()
        if row:
            self.id = row["id"]
        conn.close()

    @classmethod
    def log(cls, lead_id: Optional[int], event: str, details: Optional[str] = None):
        entry = cls(
            id=None,
            lead_id=lead_id,
            event=event,
            details=details,
            created_at=datetime.utcnow(),
        )
        entry.save()
        logger.info("AUDIT: lead_id=%s event=%s details=%s", lead_id, event, details)