#!/usr/bin/env python3
"""
BCD TRAVEL Visa Bot — Main Loop
Версия: 4.1 (Fix Imports)
"""

import os
import time
import signal
import sys
import logging
import sqlite3
import threading
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from datetime import datetime

from dotenv import load_dotenv

# Внутренние модули
from db import init_db # <--- ИСПРАВЛЕНО: Импорт из db.py
from models import Lead, AuditLog, is_working_hours
from graph_api import (
    get_token, 
    fetch_unread, 
    fetch_thread, 
    send_reply, 
    send_mail, 
    mark_read_and_tag,
    forward_message
)
from google_forms_sync import sync_all_forms

# NLP v3
try:
    from ai_visa_assistant_v3 import (
        generate_reply_from_thread, 
        classify_message, 
        QuestionnaireLinks as FormLinks, 
        get_ai_branding
    )
except ImportError:
    # Fallback для старой версии (на всякий случай)
    from ai_nlp import (
        generate_reply_from_thread, 
        classify_message, 
        FormLinks
    )
    def get_ai_branding(): return None

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("bcd_bot")

load_dotenv()

# ==============================================================================
# КОНФИГУРАЦИЯ
# ==============================================================================

@dataclass
class BotConfig:
    poll_interval: int = int(os.getenv("POLL_INTERVAL_SECONDS", "30"))
    sync_interval: int = int(os.getenv("SYNC_INTERVAL_SECONDS", "300")) # Синхронизация форм раз в 5 минут
    first_reminder_days: int = int(os.getenv("FIRST_REMINDER_DAYS", "1"))
    second_reminder_days: int = int(os.getenv("SECOND_REMINDER_DAYS", "3"))
    mailbox_upn: str = os.getenv("MAILBOX_UPN", "RobotVisa@itplus.kz")
    form_links: FormLinks = FormLinks.from_config()

CONFIG = BotConfig()
SHUTDOWN_FLAG = False
PROCESSED_CACHE = set()

# ==============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==============================================================================

def text_to_html(text: str) -> str:
    if not text: return ""
    # Базовая защита + конвертация переносов строк
    safe_text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    lines = safe_text.split('\n')
    html_lines = []
    for line in lines:
        if line.strip().startswith("---") or line.strip().startswith("==="):
            html_lines.append(f"<hr>")
        elif line.strip():
            # Если строка похожа на ссылку, делаем её кликабельной
            if "http" in line:
                parts = line.split(" ")
                new_parts = []
                for p in parts:
                    if p.startswith("http"):
                        p = f'<a href="{p}">{p}</a>'
                    new_parts.append(p)
                line = " ".join(new_parts)
            html_lines.append(f"<div>{line}</div>")
        else:
            html_lines.append("<br>")
    return "".join(html_lines)

def signal_handler(sig, frame):
    global SHUTDOWN_FLAG
    logger.info("Получен сигнал остановки...")
    SHUTDOWN_FLAG = True

def async_sync_forms():
    """
    Запускает синхронизацию форм в фоновом режиме, чтобы не блокировать бота.
    """
    try:
        logger.info("🔄 Starting background form sync...")
        count = sync_all_forms()
        if count > 0:
            logger.info(f"✅ Background sync finished: {count} new forms.")
        else:
            logger.info("Background sync finished: No new forms.")
    except Exception as e:
        logger.error(f"❌ Background sync error: {e}", exc_info=True)

# ==============================================================================
# ЛОГИКА ОБРАБОТКИ
# ==============================================================================

def process_single_message(token: str, msg: Dict[str, Any]):
    msg_id = msg.get("id")
    
    if msg_id in PROCESSED_CACHE:
        try:
            mark_read_and_tag(token, msg_id, ["BotProcessed"])
        except: pass
        return

    conv_id = msg.get("conversationId")
    sender = msg.get("from", {})
    if not sender: 
        mark_read_and_tag(token, msg_id, ["SystemMsg"])
        PROCESSED_CACHE.add(msg_id)
        return

    sender_email = sender.get("emailAddress", {}).get("address")
    subject = msg.get("subject", "")
    
    # Проверка на самого себя (Loop protection)
    if sender_email.lower() == CONFIG.mailbox_upn.lower():
        mark_read_and_tag(token, msg_id, ["SelfSent"])
        PROCESSED_CACHE.add(msg_id)
        return

    # Проверка по БД - не отвечали ли мы уже на это письмо
    lead = Lead.get_by_email(sender_email)
    if lead and lead.last_message_id == msg_id:
        mark_read_and_tag(token, msg_id, ["AlreadyInDB"])
        PROCESSED_CACHE.add(msg_id)
        return

    logger.info(f"📨 Processing message from {sender_email}")

    try:
        # Получаем историю переписки
        thread_messages = fetch_thread(token, conv_id)
        if not thread_messages: thread_messages = [msg]
        
        # Определяем, какие формы уже отправлены
        existing_forms = {"poland": False, "schengen": False, "usa": False, "generic": False}
        if lead and lead.questionnaire_status in ("sent", "filled"):
            if lead.visa_country == "PL": existing_forms["poland"] = True
            elif lead.visa_country == "SCHENGEN": existing_forms["schengen"] = True
            elif lead.visa_country == "US": existing_forms["usa"] = True
            else: existing_forms["generic"] = True

        # 1. АНАЛИЗ СООБЩЕНИЯ
        analysis = classify_message(
            thread_messages, 
            our_address=CONFIG.mailbox_upn,
            previous_status=lead.status if lead else None,
            existing_poland_questionnaire=existing_forms["poland"],
            existing_schengen_questionnaire=existing_forms["schengen"],
            existing_usa_questionnaire=existing_forms["usa"],
            existing_generic_questionnaire=existing_forms["generic"]
        )
        
        intent = analysis.get("intent")
        forward_to = analysis.get("forward_to_email")
        
        # Пересылка нестандартных кейсов
        if forward_to:
            if forward_message(token, msg_id, forward_to, comment="AI Handover: Non-standard request"):
                mark_read_and_tag(token, msg_id, ["HandedOver"])
                PROCESSED_CACHE.add(msg_id)
                logger.info(f"Handed over to specialist: {forward_to}")
            return

        # 🔥 ВАЖНО: Создаем лида ДО генерации ответа, если его нет.
        if not lead:
            # Создаем черновик лида, если намерение похоже на заявку
            if intent not in ["spam", "other"] or analysis.get("needs_questionnaire"):
                lead = Lead.create(sender_email, conv_id, subject, intent)
                logger.info(f"Created new Lead ID={lead.id} pre-generation")

        # Подготовка конфига для генератора (передаем ID лида!)
        extra_ctx = {
            "lead_id": lead.id if lead else None
        }

        # 2. ГЕНЕРАЦИЯ ОТВЕТА
        # AI сам вставит ссылку с lead_id, если нужно
        ai_reply_text = generate_reply_from_thread(
            thread_messages,
            our_address=CONFIG.mailbox_upn,
            previous_status=lead.status if lead else None,
            existing_poland_questionnaire=existing_forms["poland"],
            existing_schengen_questionnaire=existing_forms["schengen"],
            existing_usa_questionnaire=existing_forms["usa"],
            existing_generic_questionnaire=existing_forms["generic"],
            questionnaire_links=CONFIG.form_links,
            extra_config=extra_ctx # Передаем контекст с ID
        )

        # 3. ОТПРАВКА
        html_body = text_to_html(ai_reply_text)
        sent_ok = send_reply(token, msg_id, html_body)

        if sent_ok:
            logger.info(f"✅ Reply sent to {sender_email}")
            
            # Если лида не было (и не создали выше из-за странного интента), создаем сейчас
            if not lead:
                lead = Lead.create(sender_email, conv_id, subject, intent)
            
            # Обновление данных лида
            new_status = analysis.get("new_status")
            if new_status: lead.status = new_status
            
            lead.message_id = msg_id
            lead.last_message_id = msg_id
            lead.last_contacted = datetime.utcnow()

            # Обновление статусов форм
            if analysis.get("offer_poland_questionnaire"):
                lead.visa_country = "PL"
                lead.questionnaire_status = "sent"
            elif analysis.get("offer_schengen_questionnaire"):
                lead.visa_country = "SCHENGEN"
                lead.questionnaire_status = "sent"
            elif analysis.get("offer_usa_questionnaire"):
                lead.visa_country = "US"
                lead.questionnaire_status = "sent"
            elif analysis.get("offer_generic_questionnaire"):
                lead.questionnaire_status = "sent"

            # Планирование напоминаний (только если не отмена и не спам)
            if intent in ("want_apply", "info_request") and new_status != "cancelled":
                if not lead.next_reminder_at:
                    lead.schedule_first_reminder(CONFIG.first_reminder_days)
            
            lead.save()
            AuditLog.log(lead.id, "bot_reply", f"Intent: {intent}")
            PROCESSED_CACHE.add(msg_id)

    except Exception as e:
        logger.error(f"Error processing single message {msg_id}: {e}", exc_info=True)
        PROCESSED_CACHE.add(msg_id)
        
    finally:
        try:
            mark_read_and_tag(token, msg_id, ["BotProcessed"])
        except: pass

def handle_unread_messages():
    token = get_token()
    if not token: return
    try:
        # Берем больше писем, так как теперь работаем стабильнее
        unread_msgs = fetch_unread(token, top=10)
    except: return

    if unread_msgs:
        logger.info(f"Found {len(unread_msgs)} unread messages")
        for msg in unread_msgs:
            if SHUTDOWN_FLAG: break
            process_single_message(token, msg)

def handle_reminders():
    token = get_token()
    if not token: return
    
    # 🔥 ПРОВЕРКА ТАЙМЗОН (Решение проблемы 4)
    # Если сейчас ночь в Казахстане, не шлем напоминания
    if not is_working_hours():
        return
    
    due_leads = Lead.get_due_reminders()
    if not due_leads: return
    
    logger.info(f"⏰ Processing {len(due_leads)} due reminders")
    for lead in due_leads:
        if SHUTDOWN_FLAG: break
        
        try:
            thread = fetch_thread(token, lead.conversation_id) if lead.conversation_id else []
            
            # Контекст для AI: это фоллоу-ап
            reminder_ctx = {
                "task": "generate_followup", 
                "stage": 1 if lead.reminders_sent == 0 else 2,
                "lead_id": lead.id # Передаем ID для ссылки
            }
            
            ai_text = generate_reply_from_thread(
                thread, 
                our_address=CONFIG.mailbox_upn, 
                extra_config=reminder_ctx, 
                questionnaire_links=CONFIG.form_links
            )
            
            # Отправка
            sent = False
            if thread and thread[0].get("id"):
                 sent = send_reply(token, thread[0]["id"], text_to_html(ai_text))
            elif lead.from_address:
                 # Если треда нет, шлем новое письмо
                 sent = send_mail(token, lead.from_address, f"Re: {lead.subject}", text_to_html(ai_text))
                 
            if sent:
                if lead.reminders_sent == 0:
                    lead.schedule_next_reminder(CONFIG.second_reminder_days)
                else:
                    lead.stop_reminders()
                    lead.status = "nurturing_done"
                    lead.save()
        except Exception as e:
            logger.error(f"Error handling reminder for lead {lead.id}: {e}")

def handle_form_acks():
    """
    Отправляет подтверждение получения анкеты
    """
    token = get_token()
    if not token: return
    
    db_path = os.getenv("LEADS_DB_PATH", "leads.db")
    try:
        # Используем контекстный менеджер для безопасности
        with sqlite3.connect(db_path, timeout=10) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            # Выбираем тех, кто заполнил анкету, но не получил отбивку
            cur.execute("SELECT * FROM leads WHERE questionnaire_status='filled' AND (form_ack_sent IS NULL OR form_ack_sent=0) AND from_address IS NOT NULL")
            rows = cur.fetchall()
            
        for row in rows:
            lead = Lead.from_row(row)
            branding = get_ai_branding()
            ft = branding.get_footer_ru() if branding else ""
            
            msg = f"Добрый день!\nМы получили вашу анкету и передали её специалистам на проверку.\nСкоро вернемся с обратной связью.{ft}"
            
            sent = False
            if lead.last_message_id:
                sent = send_reply(token, lead.last_message_id, text_to_html(msg))
            elif lead.from_address:
                sent = send_mail(token, lead.from_address, "Анкета получена", text_to_html(msg))
            
            if sent:
                lead.mark_form_ack_sent()
                logger.info(f"Sent form ack to lead {lead.id}")
                
    except Exception as e:
        logger.error(f"Error in handle_form_acks: {e}")

def main_loop():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info(f"🚀 Bot started (Ver 4.1). DB: {os.getenv('LEADS_DB_PATH', 'leads.db')}")
    
    # Проверка ссылок
    if not CONFIG.form_links.poland and not CONFIG.form_links.schengen:
        logger.warning("⚠️  WARNING: FORM LINKS ARE EMPTY! Bot will not be able to send forms.")
    
    init_db()

    last_sync_time = 0
    
    while not SHUTDOWN_FLAG:
        start_time = time.time()
        
        try:
            # 1. Обработка почты
            handle_unread_messages()
            
            # 2. Асинхронная синхронизация форм (Раз в N секунд)
            if time.time() - last_sync_time > CONFIG.sync_interval:
                # Запускаем в отдельном потоке (daemon), чтобы не тормозить цикл
                sync_thread = threading.Thread(target=async_sync_forms)
                sync_thread.daemon = True
                sync_thread.start()
                last_sync_time = time.time()
            
            # 3. Служебные задачи
            handle_form_acks()
            handle_reminders()
            
        except Exception as e:
            logger.critical(f"🔥 Critical Loop Error: {e}", exc_info=True)
            time.sleep(10) # Пауза при ошибке, чтобы не спамить лог
        
        # Очистка кэша
        if len(PROCESSED_CACHE) > 2000:
            PROCESSED_CACHE.clear()

        # Умный sleep
        elapsed = time.time() - start_time
        sleep_time = max(1, CONFIG.poll_interval - elapsed)
        if not SHUTDOWN_FLAG:
            time.sleep(sleep_time)

    logger.info("Bot stopped.")

if __name__ == "__main__":
    main_loop()