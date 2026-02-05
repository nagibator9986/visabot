# backend/crm/serializers.py
import json
from typing import Any, Dict, List

from rest_framework import serializers

from .models import Lead, LeadForm, FormResponse, AuditLog, BotSettings


# ---------- Маппинг статусов (из поля leads.status) ----------

STATUS_LABELS = {
    "new": "Новый",
    "info_provided": "Информация отправлена",
    "questionnaire_sent": "Анкета отправлена",
    "questionnaire_filled": "Анкета заполнена",
    "docs_in_progress": "Документы в работе",
    "ready_for_submission": "Готово к подаче",
    "followup": "Нужно напомнить",
    "nurturing_done": "Натуральный догрев завершён",
    "closed": "Закрыт",
}


# ---------- Lead ----------


class LeadSerializer(serializers.ModelSerializer):
    status_label = serializers.SerializerMethodField()
    forms_count = serializers.IntegerField(read_only=True)
    form_responses_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Lead
        fields = [
            "id",
            "from_address",
            "subject",
            "visa_country",
            "status",
            "status_label",
            "questionnaire_status",
            "questionnaire_form_id",
            "questionnaire_response_id",
            "last_message_id",
            "last_contacted",
            "next_reminder_at",
            "reminders_sent",
            "form_ack_sent",
            "forms_count",
            "form_responses_count",
        ]

    def get_status_label(self, obj: Lead) -> str | None:
        code = (obj.status or "").strip() if getattr(obj, "status", None) else ""
        if not code:
            return None
        return STATUS_LABELS.get(code, code)


# ---------- LeadForm (lead_forms) ----------


class LeadFormSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeadForm
        # В БД поле называется lead_id, связи ForeignKey нет
        fields = ["id", "lead_id", "form_type", "raw_text", "created_at"]
        read_only_fields = ["id", "created_at"]


# ---------- FormResponse (form_responses) + parsed_answers + attachments ----------


class ParsedAnswerSerializer(serializers.Serializer):
    question_id = serializers.CharField()
    label = serializers.CharField()
    value = serializers.CharField(allow_blank=True)


class FormAttachmentSerializer(serializers.Serializer):
    """
    Описание одного файла-вложения из Google Forms.
    Это НЕ модель, просто структура данных, собираемая из raw_json.
    """
    question_id = serializers.CharField()
    label = serializers.CharField()
    file_id = serializers.CharField()
    file_name = serializers.CharField()
    drive_url = serializers.CharField()


class FormResponseSerializer(serializers.ModelSerializer):
    """
    raw_json в БД → parsed_answers (список {question_id, label, value})
    И обратно: при PATCH с parsed_answers мы обновляем raw_json.

    attachments — виртуальное поле, собираемое из raw_json, если там
    сохранены данные о файлах (паспорт, фото и т.п.).
    """

    parsed_answers = serializers.SerializerMethodField()
    attachments = serializers.SerializerMethodField()

    class Meta:
        model = FormResponse
        fields = [
            "id",
            "lead_id",
            "visa_country",
            "form_id",
            "response_id",
            "respondent_email",
            "raw_json",
            "created_at",
            "parsed_answers",
            "attachments",  # 👈 ОБЯЗАТЕЛЬНО добавлено в fields
        ]
        read_only_fields = ["id", "created_at", "raw_json"]

    # ---- внутренний helper для raw_json ----

    def _get_raw_json_from_obj(self, obj: Any) -> str:
        """
        obj может быть:
          - моделью FormResponse
          - dict / ReturnDict (когда сериализатор используется вложенно
            в LeadDetailSerializer)
        """
        if isinstance(obj, dict):
            return obj.get("raw_json") or ""
        return getattr(obj, "raw_json", "") or ""

    # ---- parsed_answers: чтение raw_json -> список ответов ----

    def get_parsed_answers(self, obj: Any) -> List[Dict[str, str]]:
        raw = self._get_raw_json_from_obj(obj)
        if not raw:
            return []

        try:
            data = json.loads(raw)
        except Exception:
            return []

        result: list[dict[str, str]] = []

        # 1) Если структура {"answers": {...}}
        if isinstance(data, dict) and isinstance(data.get("answers"), dict):
            for qid, val in data["answers"].items():
                if isinstance(val, dict):
                    label = (
                        val.get("label")
                        or val.get("question")
                        or str(qid)
                    )
                    value = (
                        val.get("value")
                        or val.get("answer")
                        or ""
                    )
                else:
                    label = str(qid)
                    value = str(val)
                result.append(
                    {
                        "question_id": str(qid),
                        "label": label,
                        "value": value,
                    }
                )
            return result

        # 2) Общий случай: разворачиваем верхний уровень словаря
        if isinstance(data, dict):
            for key, val in data.items():
                label = str(key)
                if isinstance(val, dict) and "value" in val:
                    value = str(val.get("value") or "")
                else:
                    if isinstance(val, (dict, list)):
                        value = json.dumps(val, ensure_ascii=False)
                    else:
                        value = str(val)
                result.append(
                    {
                        "question_id": str(key),
                        "label": label,
                        "value": value,
                    }
                )
        return result

    # ---- attachments: чтение raw_json -> список файлов ----

    def get_attachments(self, obj: Any) -> List[Dict[str, str]]:
        """
        Сканирует raw_json на наличие загруженных файлов внутри ответов.
        Бот сохраняет их внутри answers -> {qid} -> files.
        """
        raw = self._get_raw_json_from_obj(obj)
        if not raw:
            return []

        try:
            data = json.loads(raw)
        except Exception:
            return []

        if not isinstance(data, dict):
            return []

        # Ищем файлы внутри answers
        answers = data.get("answers") or {}
        result: List[Dict[str, str]] = []

        # Проходим по всем вопросам
        for qid, content in answers.items():
            if not isinstance(content, dict):
                continue
            
            # Если есть ключ "files" (бот его туда кладет)
            files = content.get("files")
            if files and isinstance(files, list):
                label = content.get("label") or qid
                
                for f in files:
                    result.append({
                        "question_id": str(qid),
                        "label": str(label),
                        "file_id": str(f.get("fileId") or ""),
                        "file_name": str(f.get("fileName") or "file"),
                        "drive_url": str(f.get("driveUrl") or ""),
                    })

        return result

    # ---- запись: parsed_answers -> raw_json ----

    def update(self, instance: FormResponse, validated_data: Dict[str, Any]) -> FormResponse:
        """
        Позволяет PATCH /form-responses/{id}/ с телом:
          {
            "parsed_answers": [
              {"question_id": "q1", "label": "Имя", "value": "Иван"},
              ...
            ]
          }

        Мы соберём из них структуру {"answers": {...}} и положим в raw_json.

        attachments здесь пока НЕ изменяем, только читаем.
        """
        # Достаём parsed_answers именно из initial_data, а не validated_data,
        # потому что parsed_answers не поле модели.
        parsed_answers = self.initial_data.get("parsed_answers")
        if parsed_answers is not None:
            answers: dict[str, dict[str, str]] = {}
            for item in parsed_answers:
                qid = str(item.get("question_id") or "").strip()
                if not qid:
                    continue
                label = item.get("label") or qid
                value = item.get("value") or ""
                answers[qid] = {
                    "label": label,
                    "value": value,
                }

            # Пытаемся сохранить существующие поля из raw_json, если там что-то ещё есть
            try:
                base = json.loads(instance.raw_json or "{}")
                if not isinstance(base, dict):
                    base = {}
            except Exception:
                base = {}

            base["answers"] = answers
            instance.raw_json = json.dumps(base, ensure_ascii=False)

        # Обновляем остальные обычные поля (если придут)
        for field, value in validated_data.items():
            setattr(instance, field, value)

        instance.save()
        return instance


# ---------- AuditLog ----------


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = ["id", "lead_id", "event", "details", "created_at"]


# ---------- Детальный ответ по лиду ----------


class LeadDetailSerializer(serializers.Serializer):
    """
    Детальный ответ по лиду:
      - сам Lead
      - связанные LeadForm (анкеты)
      - связанные FormResponse (Google Forms) с parsed_answers и attachments
      - история AuditLog
    """

    lead = LeadSerializer()
    lead_forms = LeadFormSerializer(many=True)
    form_responses = FormResponseSerializer(many=True)
    audit_logs = AuditLogSerializer(many=True)


# ---------- BotSettings ----------


class BotSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = BotSettings
        fields = [
            "id",
            "bot_name",
            "sender_email",
            "first_reminder_days",
            "second_reminder_days",
            "poll_interval_seconds",
            "send_window_start_hour",
            "send_window_end_hour",
            "auto_create_leads",
            "auto_change_status",
            "auto_reminders_enabled",
            "form_poland_url",
            "form_schengen_url",
            "form_usa_url",
            "form_generic_url",
            "extra_config",
        ]
