# lead_logic.py
from datetime import datetime
import os

from utils import logger, safe_strip
from ai_nlp import classify_message, generate_reply_from_thread, Message
from models import Lead, AuditLog
from forms import handle_form_answers_if_any
from db import get_connection

# Настройки по умолчанию можно переопределить через .env
MAX_THREAD_MESSAGES = int(os.getenv("MAX_THREAD_MESSAGES", "6"))
MAX_BODY_HTML_RAW_CHARS = int(os.getenv("MAX_BODY_HTML_RAW_CHARS", "20000"))
MAX_BODY_CHARS = int(os.getenv("MAX_BODY_CHARS", "3000"))


def _normalize_body_from_graph_message(m) -> str:
    """
    Берём тело письма из Graph-сообщения, чистим HTML и
    агрессивно ограничиваем размер, чтобы не раздувать контекст для LLM.
    """
    body_html = (m.get("body") or {}).get("content") or ""
    body_preview = m.get("bodyPreview") or ""
    body_raw = body_html or body_preview

    # Ограничиваем размер сырых HTML-данных
    if body_raw and len(body_raw) > MAX_BODY_HTML_RAW_CHARS:
        # Берём хвост, где обычно последние ответы
        body_raw = body_raw[-MAX_BODY_HTML_RAW_CHARS:]

    # Чистим HTML/лишние пробелы
    body_text = safe_strip(body_raw)

    # Ограничиваем уже очищенный текст
    if body_text and len(body_text) > MAX_BODY_CHARS:
        body_text = body_text[-MAX_BODY_CHARS:]

    return body_text or ""


def build_thread_context(thread):
    """
    Текстовый контекст для напоминаний.
    Использует только последние N писем треда и уже нормализованный текст.
    """
    text = "История переписки с клиентом:\n"
    if not thread:
        text += "\n(Переписка отсутствует)\n"
        return text

    raw = thread[-MAX_THREAD_MESSAGES:]

    for m in raw:
        sender = m.get("from", {}).get("emailAddress", {}).get("address", "unknown")
        body = _normalize_body_from_graph_message(m)
        dt = m.get("receivedDateTime", "")
        text += f"\n---\nОт: {sender}\nДата: {dt}\nТекст: {body}\n"

    text += "\nСформируй профессиональный ответ от имени BCD Travel."
    return text


def _build_thread_messages(thread, fallback_msg):
    """
    Преобразует список писем от Graph API в список Message для ai_nlp.

    Особенности:
    - Используем только последние MAX_THREAD_MESSAGES сообщений.
    - Нормализуем и режем тело письма, чтобы не перегружать LLM.
    """
    raw = thread if thread else [fallback_msg]
    raw = raw[-MAX_THREAD_MESSAGES:]

    msgs = []

    for m in raw:
        body = _normalize_body_from_graph_message(m)
        msgs.append(
            Message(
                from_address=(m.get("from", {}).get("emailAddress", {}).get("address") or ""),
                subject=m.get("subject") or "",
                body=body,
                received_at=m.get("receivedDateTime"),
            )
        )
    return msgs


def _build_form_block(form_code: str) -> str:
    form_code = (form_code or "").lower()

    poland_url = os.getenv("FORM_POLAND_URL") or os.getenv("POLAND_FORM_URL")
    schengen_url = os.getenv("FORM_SCHENGEN_URL") or os.getenv("SCHENGEN_FORM_URL")
    usa_url = os.getenv("FORM_USA_URL") or os.getenv("USA_FORM_URL")
    generic_url = os.getenv("FORM_GENERIC_URL") or os.getenv("GENERIC_FORM_URL")

    if form_code == "poland" and poland_url:
        return (
            "Для продолжения оформления визы в Польшу, пожалуйста, заполните анкету по ссылке:\n"
            f"{poland_url}\n\n"
            "После получения анкеты мы сможем подсказать точный перечень документов и следующий шаг."
        )

    if form_code == "schengen" and schengen_url:
        return (
            "Для оформления шенгенской визы (Франция / Италия / Испания и др.) "
            "пожалуйста, заполните анкету по ссылке:\n"
            f"{schengen_url}\n\n"
            "Это поможет нам собрать корректный пакет документов и подобрать оптимальный вариант подачи."
        )

    if form_code == "usa" and usa_url:
        return (
            "Для оформления визы США, пожалуйста, заполните анкету (опросник для DS-160) по ссылке:\n"
            f"{usa_url}\n\n"
            "После её получения мы сможем подготовить ваши данные для заполнения официальной анкеты."
        )

    if form_code == "generic" and generic_url:
        return (
            "Для оформления визы в выбранную страну, пожалуйста, заполните универсальную анкету по ссылке:\n"
            f"{generic_url}\n\n"
            "После получения анкеты мы проверим данные и отправим вам индивидуальные рекомендации по документам и дальнейшим шагам."
        )

    return ""


def _detect_existing_forms_for_lead(lead: Lead):
    if not lead:
        return False, False, False

    qs = (getattr(lead, "questionnaire_status", "") or "").lower()
    vc = (getattr(lead, "visa_country", "") or "").upper()
    form_id = getattr(lead, "questionnaire_form_id", "") or ""

    poland_id = os.getenv("POLAND_FORM_ID") or ""
    schengen_id = os.getenv("SCHENGEN_FORM_ID") or ""
    usa_id = os.getenv("USA_FORM_ID") or ""

    existing_poland = qs in ("sent", "filled") and (
        vc == "PL" or form_id == poland_id
    )
    existing_schengen = qs in ("sent", "filled") and (
        vc in ("FR", "IT", "ES", "SCHENGEN") or form_id == schengen_id
    )
    existing_usa = qs in ("sent", "filled") and (vc == "US" or form_id == usa_id)

    return existing_poland, existing_schengen, existing_usa


def _infer_form_code_from_country(country_code: str | None) -> str | None:
    if not country_code:
        return None
    cc = country_code.upper()
    if cc == "PL":
        return "poland"
    if cc in ("FR", "IT", "ES", "SCHENGEN"):
        return "schengen"
    if cc == "US":
        return "usa"
    return "generic"


def should_send_questionnaire(
    intent: str,
    lead: Lead | None,
    message_text: str,
    base_needs_form: bool,
) -> bool:
    text = (message_text or "").lower().strip()

    if lead is not None:
        qs = (getattr(lead, "questionnaire_status", "") or "").lower()
        if qs in ("sent", "filled"):
            return False

    ask_form_patterns = [
        "заполню вашу форму",
        "готов заполнить форму",
        "готов заполнить анкету",
        "заполню анкету",
        "можно вашу анкету",
        "можно вашу форму",
        "скиньте анкету",
        "скиньте форму",
        "пришлите анкету",
        "пришлите форму",
        "давайте я заполню вашу форму",
        "давайте я заполню анкету",
    ]
    if any(p in text for p in ask_form_patterns):
        return True

    if base_needs_form:
        return True

    if intent == "want_apply":
        return True

    if any(w in text for w in ["анкета", "форму", "формы"]) and any(
        c in text
        for c in ["польш", "poland", "italy", "итал", "france", "франц", "шенген", "usa", "сша"]
    ):
        return True

    return False


def process_incoming_message(msg, thread):
    conv_id = msg.get("conversationId")
    message_id = msg.get("id")
    email = msg["from"]["emailAddress"]["address"].lower()
    subject = msg.get("subject", "(без темы)")

    # Используем тот же нормализатор, что и для треда
    body_text = _normalize_body_from_graph_message(msg)

    logger.info(
        "Incoming message conv=%s from=%s subj=%s", conv_id, email, subject
    )

    thread_msgs = _build_thread_messages(thread, msg)

    lead = None
    if conv_id:
        lead = Lead.get_by_conversation(conv_id)
    if not lead and message_id:
        lead = Lead.get_by_message(message_id)

    previous_status = lead.status if lead else None

    existing_poland_form, existing_schengen_form, existing_usa_form = _detect_existing_forms_for_lead(lead)

    cls = classify_message(
        thread_messages=thread_msgs,
        previous_status=previous_status,
        existing_poland_form=existing_poland_form,
        existing_schengen_form=existing_schengen_form,
        existing_usa_form=existing_usa_form,
    )

    intent = cls["intent"]
    new_status = cls.get("new_status") or intent or "new"
    country_code = cls.get("country")
    base_needs_form = cls.get("needs_form", False)
    form_code = cls.get("form_code")

    if country_code is None and lead and getattr(lead, "visa_country", None):
        country_code = lead.visa_country

    now = datetime.utcnow()

    if not lead:
        lead = Lead(
            id=None,
            message_id=message_id,
            conversation_id=conv_id,
            from_address=email,
            subject=subject,
            status=new_status,
            last_contacted=now,
            next_reminder_at=None,
            reminders_sent=0,
        )
    else:
        lead.message_id = message_id
        lead.conversation_id = conv_id
        lead.from_address = email
        lead.subject = subject
        lead.status = new_status
        lead.last_contacted = now

    if country_code is not None and hasattr(lead, "visa_country"):
        lead.visa_country = country_code

    needs_form = should_send_questionnaire(
        intent=intent,
        lead=lead,
        message_text=body_text,
        base_needs_form=base_needs_form,
    )

    if needs_form and not form_code:
        form_code = _infer_form_code_from_country(country_code)

    if needs_form and form_code:
        qs = (getattr(lead, "questionnaire_status", "") or "").lower()
        if hasattr(lead, "questionnaire_status") and qs != "filled":
            lead.questionnaire_status = "sent"

        if hasattr(lead, "questionnaire_form_id"):
            if form_code == "poland":
                lead.questionnaire_form_id = (
                    os.getenv("POLAND_FORM_ID") or getattr(lead, "questionnaire_form_id", "")
                )
            elif form_code == "schengen":
                lead.questionnaire_form_id = (
                    os.getenv("SCHENGEN_FORM_ID") or getattr(lead, "questionnaire_form_id", "")
                )
            elif form_code == "usa":
                lead.questionnaire_form_id = (
                    os.getenv("USA_FORM_ID") or getattr(lead, "questionnaire_form_id", "")
                )
            elif form_code == "generic":
                lead.questionnaire_form_id = (
                    os.getenv("FORM_GENERIC_ID")
                    or os.getenv("GENERIC_FORM_ID")
                    or getattr(lead, "questionnaire_form_id", "")
                )

    if hasattr(lead, "last_message_id"):
        lead.last_message_id = message_id

    lead.save()

    AuditLog.log(
        lead.id,
        "user_message",
        f"intent={intent}, country={country_code}, needs_form={needs_form}, base_needs_form={base_needs_form}, form_code={form_code}",
    )

    if body_text and any(f"{i}." in body_text for i in range(1, 6)):
        conn = get_connection()
        try:
            handle_form_answers_if_any(
                conn=conn,
                lead={"id": lead.id},
                message_text=body_text,
            )
        finally:
            conn.close()

    reply_text = generate_reply_from_thread(
        thread_messages_or_text=thread_msgs,
        previous_status=previous_status,
        existing_poland_form=existing_poland_form,
        existing_schengen_form=existing_schengen_form,
        existing_usa_form=existing_usa_form,
    )

    if not reply_text:
        reply_text = (
            "Спасибо за обращение! Мы получили ваше письмо и вернёмся к вам с ответом в ближайшее время."
        )

    if needs_form and form_code:
        form_block = _build_form_block(form_code)
        if form_block:
            reply_text = reply_text.rstrip() + "\n\n" + form_block

    return reply_text, lead.id, intent
