# backend/crm/models.py
from django.db import models


# ============================================================
#  СУЩЕСТВУЮЩИЕ ТАБЛИЦЫ ИЗ leads.db (используются ботом)
#  ВАЖНО: managed = False → Django НЕ трогает схему БД
# ============================================================


class Lead(models.Model):
    """
    Маппинг на существующую таблицу `leads`, с которой уже работает почтовый бот.
    Django только читает/пишет данные через ORM, но не создаёт/не мигрирует таблицу.
    """

    id = models.IntegerField(primary_key=True)
    message_id = models.TextField()
    conversation_id = models.TextField(null=True, blank=True)
    from_address = models.TextField(null=True, blank=True)
    subject = models.TextField(null=True, blank=True)
    status = models.TextField()  # ВАЖНО: статус берём отсюда

    # Визовая информация / анкеты
    visa_country = models.TextField(null=True, blank=True)
    questionnaire_status = models.TextField(default="none")
    questionnaire_form_id = models.TextField(null=True, blank=True)
    questionnaire_response_id = models.TextField(null=True, blank=True)

    # Последнее письмо в треде
    last_message_id = models.TextField(null=True, blank=True)

    # В БД эти поля — TEXT, поэтому здесь тоже TextField.
    # На фронте/в API они прилетают как строки.
    last_contacted = models.TextField(null=True, blank=True)
    next_reminder_at = models.TextField(null=True, blank=True)

    reminders_sent = models.IntegerField(default=0)
    form_ack_sent = models.IntegerField(default=0)

    created_at = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "leads"
        managed = False
        ordering = ["-id"]

    def __str__(self):
        return f"{self.id} | {self.from_address or ''} | {self.subject or ''}"


class FormResponse(models.Model):
    """
    Таблица `form_responses` — ответы Google Forms,
    которые записывает скрипт google_forms_sync.py из бота.
    """

    id = models.IntegerField(primary_key=True)

    # Привязка к лиду (INTEGER, без ForeignKey)
    lead_id = models.IntegerField(null=True, blank=True)

    visa_country = models.TextField(null=True, blank=True)
    form_id = models.TextField(null=True, blank=True)
    response_id = models.TextField(unique=True)
    respondent_email = models.TextField(null=True, blank=True)
    raw_json = models.TextField(null=True, blank=True)
    created_at = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "form_responses"
        managed = False
        ordering = ["-id"]

    def __str__(self):
        return f"{self.id} | {self.visa_country} | {self.respondent_email or ''}"


class LeadForm(models.Model):
    """
    Таблица `lead_forms` — сырые текстовые анкеты, которые клиент заполнил
    прямо в письме (вариант с "1. ... 2. ... 3. ...").
    """

    id = models.IntegerField(primary_key=True)

    # Привязка к лиду (INTEGER)
    lead_id = models.IntegerField(null=True, blank=True)

    form_type = models.TextField(null=True, blank=True)  # 'poland', 'schengen', 'usa', 'generic', ...
    raw_text = models.TextField(null=True, blank=True)
    created_at = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "lead_forms"
        managed = False
        ordering = ["-id"]

    def __str__(self):
        return f"{self.id} | lead={self.lead_id} | {self.form_type or ''}"


class AuditLog(models.Model):
    """
    Таблица `audit_log` — журнал событий по лидам, который уже использует бот.
    """

    id = models.IntegerField(primary_key=True)

    # Привязка к лиду (INTEGER)
    lead_id = models.IntegerField(null=True, blank=True)

    event = models.TextField()
    details = models.TextField(null=True, blank=True)
    created_at = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "audit_log"
        managed = False
        ordering = ["-id"]

    def __str__(self):
        return f"{self.created_at or ''} | lead={self.lead_id} | {self.event}"


# ============================================================
#  НОВАЯ ТАБЛИЦА ДЛЯ CRM (создаётся миграциями)
# ============================================================


# models.py (фрагмент)

class BotSettings(models.Model):
    """
    Настройки бота / CRM. Одна запись с id=1.
    """

    id = models.IntegerField(primary_key=True, default=1)

    # Общие настройки
    bot_name = models.CharField(max_length=100, default="BCD Travel Bot")
    sender_email = models.CharField(max_length=255, default="visa@itplus.kz")

    # Тайминги напоминаний
    first_reminder_days = models.IntegerField(default=1)
    second_reminder_days = models.IntegerField(default=3)

    # 🔥 НОВОЕ: как часто крутить цикл бота (poller)
    poll_interval_seconds = models.IntegerField(default=5)

    # 🔥 НОВОЕ: в какое время суток можно отправлять письма (локальное время)
    # если нужно — в логике бота просто проверяем: start <= now.hour < end
    send_window_start_hour = models.IntegerField(default=9)   # 9:00
    send_window_end_hour = models.IntegerField(default=21)    # 21:00

    # Настройки поведения
    auto_create_leads = models.BooleanField(default=True)
    auto_change_status = models.BooleanField(default=True)
    auto_reminders_enabled = models.BooleanField(default=True)

    # Настройки Google Forms
    form_poland_url = models.CharField(max_length=500, blank=True, null=True)
    form_schengen_url = models.CharField(max_length=500, blank=True, null=True)
    form_usa_url = models.CharField(max_length=500, blank=True, null=True)
    form_generic_url = models.CharField(max_length=500, blank=True, null=True)

    # Дополнительная конфигурация (для будущих фич)
    extra_config = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "bot_settings"
        managed = True

    def __str__(self):
        return "Bot Settings"

