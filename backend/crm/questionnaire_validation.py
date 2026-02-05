# backend/crm/questionnaire_validation.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import re
from datetime import datetime, date

from .models import FormResponse, Lead, AuditLog
from .serializers import FormResponseSerializer


@dataclass
class ValidationIssue:
    field_key: str          # canonical key (passport_number, full_name, etc.)
    field_label: str        # human label from form ("Номер паспорта")
    level: str              # "error" | "warning"
    code: str               # machine code ("passport_too_short", ...)
    message: str            # human-readable message


@dataclass
class ValidationResult:
    is_valid: bool
    errors: List[ValidationIssue]
    warnings: List[ValidationIssue]
    normalized_values: Dict[str, Any]


# ---------- Маппинг label -> canonical key ----------

FIELD_LABEL_MAP: Dict[str, str] = {}


def _add_alias(key: str, aliases: List[str]) -> None:
    for a in aliases:
        FIELD_LABEL_MAP[a.strip().lower()] = key


# Базовые поля, которые мы хотим валидировать
_add_alias("full_name", [
    "фио",
    "фамилия имя отчество",
    "фамилия, имя, отчество",
    "фамилия и имя",
    "full name",
    "name and surname",
])

_add_alias("birth_date", [
    "дата рождения",
    "date of birth",
    "dob",
])

_add_alias("passport_number", [
    "номер паспорта",
    "паспорт",
    "passport number",
    "passport no",
])

_add_alias("passport_expiry_date", [
    "срок действия паспорта",
    "дата окончания паспорта",
    "passport expiry date",
    "passport expiration date",
])

_add_alias("phone", [
    "телефон",
    "номер телефона",
    "phone",
    "phone number",
    "mobile phone",
])

_add_alias("email", [
    "email",
    "e-mail",
    "почта",
    "электронная почта",
])

_add_alias("travel_start_date", [
    "дата начала поездки",
    "дата выезда",
    "дата въезда",
    "planned arrival date",
    "start of trip",
])

_add_alias("travel_end_date", [
    "дата окончания поездки",
    "дата возвращения",
    "planned departure date",
    "end of trip",
])


def _normalize_label(label: str) -> str:
    return re.sub(r"\s+", " ", label or "").strip().lower()


def _parse_date(value: str) -> Optional[date]:
    """
    Пытаемся распарсить дату в нескольких популярных форматах.
    Возвращаем date или None.
    """
    v = (value or "").strip()
    if not v:
        return None

    formats = ["%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"]
    for fmt in formats:
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            continue
    return None


def _extract_digits(value: str) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


def _detect_field_key(label: str) -> Optional[str]:
    norm = _normalize_label(label)
    return FIELD_LABEL_MAP.get(norm)


# ---------- Основная логика валидации одного FormResponse ----------

def validate_form_response(
    form_response: FormResponse,
    visa_country: Optional[str] = None,
) -> ValidationResult:
    """
    Валидация одного ответа Google Forms.
    Использует FormResponseSerializer, чтобы получить parsed_answers.
    """

    serializer = FormResponseSerializer(form_response)
    data = serializer.data
    parsed_answers = data.get("parsed_answers") or []

    # Собираем значения по canonical ключам
    values: Dict[str, Dict[str, Any]] = {}
    for ans in parsed_answers:
        label = ans.get("label") or ""
        value = ans.get("value") or ""
        key = _detect_field_key(label)
        if not key:
            continue
        # если один и тот же ключ был несколько раз, берём последний ответ
        values[key] = {
            "label": label,
            "value": value,
        }

    errors: List[ValidationIssue] = []
    warnings: List[ValidationIssue] = []
    normalized: Dict[str, Any] = {}

    def add_issue(field_key: str, level: str, code: str, message: str) -> None:
        label = values.get(field_key, {}).get("label", field_key)
        issue = ValidationIssue(
            field_key=field_key,
            field_label=label,
            level=level,
            code=code,
            message=message,
        )
        if level == "error":
            errors.append(issue)
        else:
            warnings.append(issue)

    # ----- full_name -----
    if "full_name" in values:
        raw = values["full_name"]["value"].strip()
        if not raw:
            add_issue("full_name", "error", "required", "Поле ФИО обязательно для заполнения.")
        else:
            # минимальная проверка — хотя бы 2 слова
            parts = [p for p in re.split(r"\s+", raw) if p]
            if len(parts) < 2:
                add_issue(
                    "full_name",
                    "warning",
                    "too_short",
                    "Рекомендуется указать полностью фамилию и имя (возможно, отчество).",
                )
            # Нормализуем регистр
            normalized["full_name"] = " ".join(p.capitalize() for p in parts)
    else:
        add_issue("full_name", "error", "missing", "Не найдено поле с ФИО в анкете.")

    # ----- birth_date -----
    if "birth_date" in values:
        raw = values["birth_date"]["value"].strip()
        if not raw:
            add_issue("birth_date", "error", "required", "Дата рождения обязательна для заполнения.")
        else:
            d = _parse_date(raw)
            if not d:
                add_issue(
                    "birth_date",
                    "error",
                    "invalid_format",
                    "Дата рождения указана в неверном формате. Используйте формат ДД.ММ.ГГГГ.",
                )
            else:
                if d > date.today():
                    add_issue(
                        "birth_date",
                        "error",
                        "in_future",
                        "Дата рождения не может быть в будущем.",
                    )
                normalized["birth_date"] = d.isoformat()
    else:
        add_issue(
            "birth_date",
            "warning",
            "missing",
            "Дата рождения не найдена в анкете. Проверьте, что это поле есть и заполнено.",
        )

    # ----- passport_number -----
    if "passport_number" in values:
        raw = values["passport_number"]["value"].strip().upper()
        if not raw:
            add_issue(
                "passport_number",
                "error",
                "required",
                "Номер паспорта обязателен для заполнения.",
            )
        else:
            # Убираем пробелы
            compact = re.sub(r"\s+", "", raw)
            # Простейшая проверка — длина и допустимые символы
            if len(compact) < 8:
                add_issue(
                    "passport_number",
                    "error",
                    "too_short",
                    "Номер паспорта слишком короткий. Проверьте, что указали полный номер.",
                )
            if not re.match(r"^[A-Z0-9]+$", compact):
                add_issue(
                    "passport_number",
                    "warning",
                    "bad_chars",
                    "Номер паспорта содержит недопустимые символы. Разрешены латинские буквы и цифры.",
                )
            normalized["passport_number"] = compact
    else:
        add_issue(
            "passport_number",
            "error",
            "missing",
            "Не найдено поле с номером паспорта. Убедитесь, что в анкете есть такой вопрос.",
        )

    # ----- passport_expiry_date -----
    if "passport_expiry_date" in values:
        raw = values["passport_expiry_date"]["value"].strip()
        if raw:
            d = _parse_date(raw)
            if not d:
                add_issue(
                    "passport_expiry_date",
                    "warning",
                    "invalid_format",
                    "Срок действия паспорта указан в непонятном формате. Используйте ДД.ММ.ГГГГ.",
                )
            else:
                normalized["passport_expiry_date"] = d.isoformat()
                # если паспорт скоро истекает — предупреждение
                today = date.today()
                if d <= today:
                    add_issue(
                        "passport_expiry_date",
                        "error",
                        "expired",
                        "Срок действия паспорта уже истёк. Нужен действующий загранпаспорт.",
                    )
                else:
                    delta_days = (d - today).days
                    if delta_days < 180:
                        add_issue(
                            "passport_expiry_date",
                            "warning",
                            "expiring_soon",
                            "Срок действия паспорта менее 6 месяцев. Для многих стран это может быть проблемой.",
                        )
        else:
            add_issue(
                "passport_expiry_date",
                "warning",
                "empty",
                "Рекомендуется указать срок действия паспорта.",
            )

    # ----- phone -----
    if "phone" in values:
        raw = values["phone"]["value"]
        digits = _extract_digits(raw)
        if len(digits) < 10:
            add_issue(
                "phone",
                "error",
                "too_short",
                "Номер телефона слишком короткий. Укажите номер полностью с кодом города/страны.",
            )
        normalized["phone"] = raw.strip()
    else:
        add_issue(
            "phone",
            "warning",
            "missing",
            "Рекомендуется указать контактный номер телефона.",
        )

    # ----- email -----
    if "email" in values:
        raw = values["email"]["value"].strip()
        if not raw:
            add_issue(
                "email",
                "error",
                "required",
                "Поле Email обязательно для заполнения.",
            )
        else:
            # простая проверка email
            if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", raw):
                add_issue(
                    "email",
                    "error",
                    "invalid_format",
                    "Email указан в неверном формате. Проверьте адрес.",
                )
        normalized["email"] = raw
    else:
        add_issue(
            "email",
            "error",
            "missing",
            "Не найдено поле Email. Убедитесь, что в анкете есть вопрос про электронную почту.",
        )

    # ----- даты поездки -----
    start = None
    end = None

    if "travel_start_date" in values:
        raw = values["travel_start_date"]["value"].strip()
        if raw:
            d = _parse_date(raw)
            if not d:
                add_issue(
                    "travel_start_date",
                    "warning",
                    "invalid_format",
                    "Дата начала поездки указана в непонятном формате.",
                )
            else:
                start = d
                normalized["travel_start_date"] = d.isoformat()

    if "travel_end_date" in values:
        raw = values["travel_end_date"]["value"].strip()
        if raw:
            d = _parse_date(raw)
            if not d:
                add_issue(
                    "travel_end_date",
                    "warning",
                    "invalid_format",
                    "Дата окончания поездки указана в непонятном формате.",
                )
            else:
                end = d
                normalized["travel_end_date"] = d.isoformat()

    if start and end and end < start:
        add_issue(
            "travel_end_date",
            "error",
            "end_before_start",
            "Дата окончания поездки не может быть раньше даты начала.",
        )

    # ----- итог -----
    is_valid = len(errors) == 0
    return ValidationResult(
        is_valid=is_valid,
        errors=errors,
        warnings=warnings,
        normalized_values=normalized,
    )


# ---------- Хелпер: полная обработка + обновление лида ----------

def validate_form_response_and_update_lead(
    form_response: FormResponse,
) -> Dict[str, Any]:
    """
    Высокоуровневая функция:
    - валидирует FormResponse
    - если есть lead_id, обновляет Lead.questionnaire_status и Lead.status
    - пишет AuditLog
    - возвращает dict для API
    """

    result = validate_form_response(
        form_response,
        visa_country=form_response.visa_country,
    )

    lead: Optional[Lead] = None
    if form_response.lead_id:
        try:
            lead = Lead.objects.get(id=form_response.lead_id)
        except Lead.DoesNotExist:
            lead = None

    questionnaire_status = None
    lead_status = None

    if lead:
        if result.is_valid:
            questionnaire_status = "valid"
            # если до этого была анкета заполнена, переводим в "данные проверены"
            lead_status = "data_validated_ok"
        else:
            questionnaire_status = "invalid"
            lead_status = "data_validation_failed"

        if questionnaire_status:
            lead.questionnaire_status = questionnaire_status
        if lead_status:
            lead.status = lead_status

        lead.save()

        # Пишем в AuditLog
        issues_summary = []
        for e in result.errors:
            issues_summary.append(f"[ERROR] {e.field_label}: {e.message}")
        for w in result.warnings:
            issues_summary.append(f"[WARN] {w.field_label}: {w.message}")

        AuditLog.objects.create(
            lead_id=lead.id,
            event="questionnaire_validated",
            details="\n".join(issues_summary) or "Анкета проверена, замечаний нет.",
        )

    # Формируем ответ для API / бота / фронта
    return {
        "form_response_id": form_response.id,
        "lead_id": lead.id if lead else None,
        "is_valid": result.is_valid,
        "questionnaire_status": questionnaire_status,
        "lead_status": lead_status,
        "errors": [
            {
                "field_key": e.field_key,
                "field_label": e.field_label,
                "level": e.level,
                "code": e.code,
                "message": e.message,
            }
            for e in result.errors
        ],
        "warnings": [
            {
                "field_key": w.field_key,
                "field_label": w.field_label,
                "level": w.level,
                "code": w.code,
                "message": w.message,
            }
            for w in result.warnings
        ],
        "normalized_values": result.normalized_values,
    }
