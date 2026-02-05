#!/usr/bin/env python3
"""
main.py — Auto responder + nurturing for RobotVisa@itplus.kz (BCD TRAVEL)

This version calls OpenAI via direct HTTP requests (requests) to avoid client/httpx compatibility issues.
"""
import os
import sys
import time
import logging
import sqlite3
import requests
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional

from dotenv import load_dotenv
import msal

load_dotenv()

# ---------------- Config ----------------
TENANT_ID = os.getenv("AZURE_TENANT_ID")
CLIENT_ID = os.getenv("AZURE_CLIENT_ID")
CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET")
MAILBOX_UPN = os.getenv("MAILBOX_UPN", "RobotVisa@itplus.kz")
MAILBOX_ID = os.getenv("MAILBOX_ID")  # optional
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))
DB_PATH = os.getenv("LEADS_DB_PATH", "leads.db")
FIRST_REMINDER_DAYS = int(os.getenv("FIRST_REMINDER_DAYS", "1"))
SECOND_REMINDER_DAYS = int(os.getenv("SECOND_REMINDER_DAYS", "3"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Basic validation
required = [TENANT_ID, CLIENT_ID, CLIENT_SECRET, OPENAI_API_KEY]
if not all(required):
    missing = [name for name, val in [
        ("AZURE_TENANT_ID", TENANT_ID),
        ("AZURE_CLIENT_ID", CLIENT_ID),
        ("AZURE_CLIENT_SECRET", CLIENT_SECRET),
        ("OPENAI_API_KEY", OPENAI_API_KEY),
    ] if not val]
    print("Missing environment variables:", ", ".join(missing))
    sys.exit(1)

# ---------------- Logging ----------------
logging.basicConfig(level=getattr(logging, LOG_LEVEL), format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("auto_responder")

# ---------------- MSAL / Graph ----------------
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPE = ["https://graph.microsoft.com/.default"]
GRAPH_BASE = "https://graph.microsoft.com/v1.0"

msal_app = msal.ConfidentialClientApplication(
    CLIENT_ID,
    authority=AUTHORITY,
    client_credential=CLIENT_SECRET
)

def get_graph_token() -> Optional[str]:
    try:
        res = msal_app.acquire_token_silent(SCOPE, account=None)
        if not res:
            res = msal_app.acquire_token_for_client(scopes=SCOPE)
        if "access_token" not in res:
            logger.error("Failed to acquire Graph token: %s", res)
            return None
        return res["access_token"]
    except Exception as e:
        logger.exception("Exception acquiring Graph token: %s", e)
        return None

def graph_request(method: str, url: str, token: str, params: dict = None, json_data: dict = None, retries: int = 2) -> Optional[requests.Response]:
    headers = {"Authorization": f"Bearer {token}"}
    if json_data is not None:
        headers["Content-Type"] = "application/json"
    for attempt in range(retries + 1):
        try:
            resp = requests.request(method, url, headers=headers, params=params, json=json_data, timeout=30)
            # handle transient Graph 429/5xx with retry
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                wait = (attempt + 1) * 2
                logger.warning("Graph transient %s, retrying after %ss (attempt %d/%d)", resp.status_code, wait, attempt+1, retries+1)
                time.sleep(wait)
                continue
            return resp
        except requests.RequestException as e:
            logger.warning("Graph request error (attempt %d/%d): %s", attempt+1, retries+1, e)
            time.sleep(1 + attempt * 2)
    logger.error("Graph request failed after %d attempts: %s %s", retries + 1, method, url)
    return None

# ---------------- DB (SQLite) ----------------
def init_db(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS leads (
      id INTEGER PRIMARY KEY,
      message_id TEXT UNIQUE,
      conversation_id TEXT,
      from_address TEXT,
      subject TEXT,
      status TEXT,
      last_contacted TEXT,
      next_reminder_at TEXT,
      reminders_sent INTEGER DEFAULT 0,
      created_at TEXT DEFAULT (datetime('now'))
    )
    """)
    conn.commit()

def upsert_lead(conn: sqlite3.Connection, message_id: str, conversation_id: str, from_addr: str,
                subject: str, status: str, last_contacted: Optional[datetime],
                next_reminder_at: Optional[datetime], reminders_sent: int):
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO leads (message_id, conversation_id, from_address, subject, status, last_contacted, next_reminder_at, reminders_sent)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(message_id) DO UPDATE SET
      conversation_id=excluded.conversation_id,
      from_address=excluded.from_address,
      subject=excluded.subject,
      status=excluded.status,
      last_contacted=excluded.last_contacted,
      next_reminder_at=excluded.next_reminder_at,
      reminders_sent=excluded.reminders_sent
    """, (
        message_id,
        conversation_id,
        from_addr,
        subject,
        status,
        last_contacted.isoformat() if last_contacted else None,
        next_reminder_at.isoformat() if next_reminder_at else None,
        reminders_sent
    ))
    conn.commit()

def get_lead_by_conversation(conn: sqlite3.Connection, conversation_id: str):
    cur = conn.cursor()
    cur.execute("SELECT * FROM leads WHERE conversation_id = ?", (conversation_id,))
    return cur.fetchone()

def get_lead_by_message(conn: sqlite3.Connection, message_id: str):
    cur = conn.cursor()
    cur.execute("SELECT * FROM leads WHERE message_id = ?", (message_id,))
    return cur.fetchone()

def get_due_reminders(conn: sqlite3.Connection, now: datetime):
    cur = conn.cursor()
    cur.execute("SELECT * FROM leads WHERE next_reminder_at IS NOT NULL AND datetime(next_reminder_at) <= datetime(?) AND status != 'closed'", (now.isoformat(),))
    return cur.fetchall()

def set_lead_closed(conn: sqlite3.Connection, message_id: str):
    cur = conn.cursor()
    cur.execute("UPDATE leads SET status='closed', next_reminder_at=NULL WHERE message_id = ?", (message_id,))
    conn.commit()

# ---------------- OpenAI via REST (requests) ----------------
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_HEADERS = {
    "Authorization": f"Bearer {OPENAI_API_KEY}",
    "Content-Type": "application/json"
}

def generate_text_via_rest(prompt: str, model: str = OPENAI_MODEL, max_tokens: int = 700, retries: int = 3) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a professional email assistant for BCD TRAVEL. Reply concisely and politely."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2,
        "max_tokens": max_tokens,
        "n": 1
    }
    for attempt in range(retries):
        try:
            resp = requests.post(OPENAI_URL, headers=OPENAI_HEADERS, json=payload, timeout=60)
            if resp.status_code == 200:
                j = resp.json()
                choices = j.get("choices")
                if choices and len(choices) > 0:
                    message = choices[0].get("message")
                    if message and "content" in message:
                        return message["content"].strip()
                    # fallback older field
                    text = choices[0].get("text")
                    if text:
                        return text.strip()
                logger.warning("OpenAI returned unexpected structure: %s", j)
                return ""
            # handle rate limits / transient errors
            if resp.status_code in (429, 500, 502, 503, 504):
                wait = (attempt + 1) * 2
                logger.warning("OpenAI transient %s, retry after %ss (attempt %d/%d): %s", resp.status_code, wait, attempt+1, retries, resp.text[:200])
                time.sleep(wait)
                continue
            # non-retryable error
            logger.error("OpenAI error %s: %s", resp.status_code, resp.text)
            raise RuntimeError(f"OpenAI API error {resp.status_code}")
        except requests.RequestException as e:
            logger.warning("OpenAI request exception (attempt %d/%d): %s", attempt+1, retries, e)
            time.sleep(1 + attempt*2)
    raise RuntimeError("OpenAI requests exhausted")

# ---------------- Prompt building ----------------
def build_prompt_for_reply(thread_msgs: List[Dict[str, Any]], purpose: str = "reply") -> str:
    system = (
        "Вы — профессиональный email-ассистент компании BCD TRAVEL. "
        "Пишите грамотно, формально, по сути. В конце подпись: 'С уважением, BCD TRAVEL, +7 (727) 000-0000, visa@itplus.kz'. "
        "Если чего-то не хватает — вежливо попросите уточнить. Не придумывайте факты."
    )
    convo = ""
    for m in thread_msgs:
        sender = m.get("from", {}).get("emailAddress", {}).get("address", "unknown")
        who = "Клиент" if sender.lower() != MAILBOX_UPN.lower() else "BCD_TRAVEL"
        subj = m.get("subject", "(без темы)")
        body = m.get("bodyPreview") or (m.get("body") or {}).get("content", "")[:800]
        time_str = m.get("receivedDateTime", "")
        convo += f"\n---\nОт: {who} ({sender})\nТема: {subj}\nДата: {time_str}\nТекст: {body}\n"
    if purpose == "reply":
        final = "\nСоставьте профессиональный ответ от имени BCD TRAVEL, вежливо и по существу. Не более 700 слов."
    else:
        final = "\nСоставьте вежливое follow-up (напоминание). Кратко, предложите дальнейшие шаги. Не более 300 слов."
    return system + "\n\nКонтекст переписки:" + convo + final

# ---------------- Mail operations ----------------
def fetch_unread_messages(token: str, top: int = 30) -> List[Dict[str, Any]]:
    mailbox = MAILBOX_UPN if MAILBOX_UPN else MAILBOX_ID
    url = f"{GRAPH_BASE}/users/{mailbox}/mailFolders/Inbox/messages"
    params = {
        "$top": top,
        "$filter": "isRead eq false",
        "$select": "id,subject,from,receivedDateTime,bodyPreview,conversationId"
    }
    r = graph_request("GET", url, token, params=params)
    if r is None:
        return []
    if r.status_code != 200:
        logger.error("Failed to fetch unread messages: %s %s", r.status_code, r.text)
        return []
    return r.json().get("value", [])

def fetch_conversation_messages(token: str, conversation_id: str) -> List[Dict[str, Any]]:
    if not conversation_id:
        return []
    mailbox = MAILBOX_UPN if MAILBOX_UPN else MAILBOX_ID
    url = f"{GRAPH_BASE}/users/{mailbox}/mailFolders/Inbox/messages"
    params = {
        "$filter": f"conversationId eq '{conversation_id}'",
        "$orderby": "receivedDateTime asc",
        "$select": "id,subject,from,receivedDateTime,bodyPreview,body,isRead"
    }
    r = graph_request("GET", url, token, params=params)
    if r is None:
        return []
    if r.status_code == 200:
        return r.json().get("value", [])
    if r.status_code == 400 and "InefficientFilter" in (r.text or ""):
        logger.warning("InefficientFilter when fetching conversation %s — fallback", conversation_id)
        return []
    logger.warning("Failed to fetch conversation messages: %s %s", r.status_code, r.text)
    return []

def create_reply_and_send(token: str, mailbox: str, message_id: str, html_content: str) -> bool:
    create_url = f"{GRAPH_BASE}/users/{mailbox}/messages/{message_id}/createReply"
    r = graph_request("POST", create_url, token, json_data={})
    if r is None or r.status_code not in (200, 201):
        logger.error("createReply failed: %s %s", getattr(r, "status_code", None), getattr(r, "text", None))
        return False
    draft = r.json()
    draft_id = draft.get("id")
    if not draft_id:
        logger.error("createReply returned no id")
        return False
    update_url = f"{GRAPH_BASE}/users/{mailbox}/messages/{draft_id}"
    body_patch = {"body": {"contentType": "HTML", "content": html_content.replace('\n', '<br>')}}
    graph_request("PATCH", update_url, token, json_data=body_patch)
    send_url = f"{GRAPH_BASE}/users/{mailbox}/messages/{draft_id}/send"
    s = graph_request("POST", send_url, token, json_data={})
    if s is not None and s.status_code in (202, 204):
        logger.info("Sent reply for message %s (draft %s)", message_id, draft_id)
        return True
    logger.error("Failed to send reply: %s %s", getattr(s, "status_code", None), getattr(s, "text", None))
    return False

def mark_message_read_and_tag(token: str, mailbox: str, message_id: str, tags: List[str]):
    url = f"{GRAPH_BASE}/users/{mailbox}/messages/{message_id}"
    patch = {"isRead": True, "categories": tags}
    r = graph_request("PATCH", url, token, json_data=patch)
    if r is None or r.status_code not in (200, 204):
        logger.warning("Failed to mark/tag message %s: %s %s", message_id, getattr(r, "status_code", None), getattr(r, "text", None))

# ---------------- Business logic ----------------
def handle_incoming_message(conn: sqlite3.Connection, token: str, msg: Dict[str, Any]):
    msg_id = msg.get("id")
    conv_id = msg.get("conversationId")
    from_addr = (msg.get("from", {}).get("emailAddress", {}).get("address") or "").lower()
    subject = msg.get("subject", "(без темы)")
    mailbox = MAILBOX_UPN if MAILBOX_UPN else MAILBOX_ID

    if not msg_id:
        logger.warning("Incoming message without id, skipping")
        return

    logger.info("Handling message %s from %s subj=%s", msg_id, from_addr, subject)

    # If existing lead for this conversation and incoming message is FROM client -> close
    if conv_id:
        existing = get_lead_by_conversation(conn, conv_id)
        if existing:
            if from_addr and from_addr != MAILBOX_UPN.lower():
                logger.info("Client replied in conversation %s — closing lead for message %s", conv_id, existing["message_id"])
                set_lead_closed(conn, existing["message_id"])
                mark_message_read_and_tag(token, mailbox, msg_id, ["Closed"])
                return

    # Build context
    thread = fetch_conversation_messages(token, conv_id) if conv_id else []
    if not thread:
        thread = [msg]

    prompt = build_prompt_for_reply(thread, purpose="reply")
    try:
        reply_text = generate_text_via_rest(prompt)
    except Exception as e:
        logger.exception("OpenAI generation error: %s", e)
        return

    final = f"{reply_text}\n\nС уважением,\nBCD TRAVEL\nТел: +7 (727) 000-0000\nEmail: visa@itplus.kz"

    ok = create_reply_and_send(token, mailbox, msg_id, final)
    if ok:
        now = datetime.now(timezone.utc)
        next_reminder = now + timedelta(days=FIRST_REMINDER_DAYS)
        upsert_lead(conn, msg_id, conv_id, from_addr, subject, "replied", now, next_reminder, 0)
        mark_message_read_and_tag(token, mailbox, msg_id, ["RepliedByBCD", "nurture_pending"])
        logger.info("Replied and scheduled first reminder at %s", next_reminder.isoformat())
    else:
        logger.error("Failed to reply to %s", msg_id)

def process_due_reminder(conn: sqlite3.Connection, token: str, lead_row):
    mailbox = MAILBOX_UPN if MAILBOX_UPN else MAILBOX_ID
    now = datetime.now(timezone.utc)
    message_id = lead_row["message_id"]
    conversation_id = lead_row["conversation_id"]
    reminders_sent = lead_row["reminders_sent"] or 0

    logger.info("Processing reminder for %s reminders_sent=%s", message_id, reminders_sent)

    thread = fetch_conversation_messages(token, conversation_id) if conversation_id else []
    if not thread:
        r = graph_request("GET", f"{GRAPH_BASE}/users/{mailbox}/messages/{message_id}", token, params={"$select":"id,subject,from,bodyPreview,receivedDateTime"})
        if r is not None and r.status_code == 200:
            thread = [r.json()]

    prompt = build_prompt_for_reply(thread, purpose="reminder")
    try:
        reminder_text = generate_text_via_rest(prompt, max_tokens=400)
    except Exception as e:
        logger.exception("OpenAI error generating reminder: %s", e)
        return

    final = f"{reminder_text}\n\nС уважением,\nBCD TRAVEL\nТел: +7 (727) 000-0000\nEmail: visa@itplus.kz"
    sent = create_reply_and_send(token, mailbox, message_id, final)
    if sent:
        now = datetime.now(timezone.utc)
        if reminders_sent == 0:
            next_reminder = now + timedelta(days=SECOND_REMINDER_DAYS)
            new_count = 1
            new_status = "nurturing"
        elif reminders_sent == 1:
            next_reminder = None
            new_count = 2
            new_status = "nurturing"
        else:
            next_reminder = None
            new_count = reminders_sent + 1
            new_status = "nurturing"

        upsert_lead(conn, message_id, conversation_id, lead_row["from_address"], lead_row["subject"], new_status, now, next_reminder, new_count)
        tags = ["RepliedByBCD", "nurture_pending"] if new_count < 2 else ["RepliedByBCD", "nurture_escalated"]
        mark_message_read_and_tag(token, mailbox, message_id, tags)
        logger.info("Reminder sent for %s; reminders_sent -> %s", message_id, new_count)
    else:
        logger.error("Failed to send reminder for %s", message_id)

# ---------------- Main loop ----------------
def main_loop():
    # без detect_types, чтобы sqlite НЕ пытался сам парсить timestamp
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    logger.info("Started auto_responder; DB=%s", DB_PATH)


    try:
        while True:
            token = get_graph_token()
            if not token:
                logger.error("No graph token, sleeping 30s")
                time.sleep(30)
                continue

            # 1) New unread messages
            try:
                unread = fetch_unread_messages(token, top=30)
                logger.debug("Found %d unread", len(unread))
                for msg in unread:
                    conv = msg.get("conversationId")
                    if conv:
                        existing = get_lead_by_conversation(conn, conv)
                        if existing and existing["status"] == "closed":
                            logger.info("Skipping closed conversation %s (message %s)", conv, msg["id"])
                            mark_message_read_and_tag(token, MAILBOX_UPN if MAILBOX_UPN else MAILBOX_ID, msg["id"], ["Closed"])
                            continue
                    handle_incoming_message(conn, token, msg)
            except Exception:
                logger.exception("Error processing unread messages")

            # 2) Due reminders
            try:
                now = datetime.now(timezone.utc)
                due = get_due_reminders(conn, now)
                logger.debug("Found %d due reminders", len(due))
                for row in due:
                    process_due_reminder(conn, token, row)
            except Exception:
                logger.exception("Error processing reminders")

            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        logger.info("Shutting down (user interrupt)")
    finally:
        conn.close()

if __name__ == "__main__":
    main_loop()
