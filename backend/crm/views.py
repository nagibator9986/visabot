# backend/crm/views.py
from typing import Any, Dict, List

import json
from django.db.models import Q
from django.db.models import Q
from django.shortcuts import get_object_or_404
from .serializers import STATUS_LABELS
from rest_framework import viewsets, generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from .questionnaire_validation import validate_form_response_and_update_lead

from .models import (
    Lead,
    LeadForm,
    FormResponse,
    AuditLog,
    BotSettings,
)
from .serializers import (
    LeadSerializer,
    LeadFormSerializer,
    FormResponseSerializer,
    AuditLogSerializer,
    LeadDetailSerializer,
    BotSettingsSerializer,
)

# ======================================
# LEADS
# ======================================


class LeadViewSet(viewsets.ModelViewSet):
    """
    CRUD по лидам.
    Статус и страна — обычные поля таблицы leads.
    """

    serializer_class = LeadSerializer
    queryset = Lead.objects.all().order_by("-id")

    def get_queryset(self):
        qs = super().get_queryset()

        status_param = self.request.query_params.get("status")
        visa_country = self.request.query_params.get("visa_country")
        search = self.request.query_params.get("search")

        if status_param:
            qs = qs.filter(status=status_param)

        if visa_country:
            qs = qs.filter(visa_country=visa_country)

        if search:
            qs = qs.filter(
                Q(from_address__icontains=search)
                | Q(subject__icontains=search)
            )

        return qs


class LeadDetailAPIView(APIView):
    """
    Детальная инфа по одному лиду:
      - сам Lead
      - его lead_forms
      - его form_responses (по lead_id ИЛИ по совпадению email)
      - его audit_log (последние 50 записей)
    """

    def get(self, request, pk: int):
        lead = get_object_or_404(Lead, pk=pk)

        # Анкеты, заполненные текстом в письме
        lead_forms = LeadForm.objects.filter(lead_id=lead.id).order_by("-id")

        # 🔥 ВАЖНО: берём ответы Google Forms либо по lead_id, либо по email
        form_responses = FormResponse.objects.filter(
            Q(lead_id=lead.id)
            | Q(
                respondent_email__isnull=False,
                respondent_email__iexact=(lead.from_address or "").strip(),
            )
        ).order_by("-id")

        audit_logs = AuditLog.objects.filter(lead_id=lead.id).order_by("-id")[:50]

        data = {
            "lead": LeadSerializer(lead).data,
            "lead_forms": LeadFormSerializer(lead_forms, many=True).data,
            "form_responses": FormResponseSerializer(form_responses, many=True).data,
            "audit_logs": AuditLogSerializer(audit_logs, many=True).data,
        }

        # сюда передаём уже готовый dict как "instance"
        serializer = LeadDetailSerializer(data)
        return Response(serializer.data)


class LeadQuestionnaireAPIView(APIView):
    """
    Сводная анкета по лиду: объединяем ответы Google Forms и (опционально)
    текст ручной анкеты в одно поле `fields`.

    Формат ответа:
    {
      "lead_id": 123,
      "fields": [
        {
          "code": "q1",
          "label": "ФИО",
          "value": "Иван Иванов",
          "source": "gform"
        },
        {
          "code": "manual_raw",
          "label": "Ручная анкета (текст из письма)",
          "value": "1. ФИО: ... 2. ДР: ...",
          "source": "manual"
        },
        ...
      ]
    }
    """

    def get(self, request, pk: int):
        lead = get_object_or_404(Lead, pk=pk)

        # --- 1. Берём все form_responses по lead_id и разворачиваем parsed_answers
        form_responses = FormResponse.objects.filter(lead_id=lead.id).order_by("id")
        fr_serializer = FormResponseSerializer(form_responses, many=True)
        fr_data = fr_serializer.data

        fields_by_qid: Dict[str, Dict[str, str]] = {}

        for fr in fr_data:
            parsed_answers = fr.get("parsed_answers") or []
            for pa in parsed_answers:
                qid = str(pa.get("question_id") or "").strip()
                if not qid:
                    continue
                label = (pa.get("label") or qid).strip()
                value = (pa.get("value") or "").strip()
                if not value:
                    continue

                existing = fields_by_qid.get(qid)
                if not existing:
                    fields_by_qid[qid] = {
                        "code": qid,
                        "label": label,
                        "value": value,
                        "source": "gform",
                    }
                else:
                    # Если уже есть значение, аккуратно дописываем через " / "
                    if value not in existing["value"]:
                        existing["value"] = f'{existing["value"]} / {value}'

        fields: List[Dict[str, str]] = list(fields_by_qid.values())

        # --- 2. Добавляем последнюю ручную анкету как отдельное поле
        lead_forms = LeadForm.objects.filter(lead_id=lead.id).order_by("-id")
        if lead_forms.exists():
            lf = lead_forms.first()
            if lf and lf.raw_text:
                fields.append(
                    {
                        "code": "manual_raw",
                        "label": "Ручная анкета (текст из письма)",
                        "value": lf.raw_text,
                        "source": "manual",
                    }
                )

        return Response(
            {
                "lead_id": lead.id,
                "fields": fields,
            }
        )


# ======================================
# LEAD FORMS
# ======================================


class LeadFormViewSet(viewsets.ModelViewSet):
    """
    CRUD по таблице lead_forms.
    """

    serializer_class = LeadFormSerializer
    queryset = LeadForm.objects.all().order_by("-id")

    def get_queryset(self):
        qs = super().get_queryset()
        lead_id = self.request.query_params.get("lead_id")
        if lead_id:
            qs = qs.filter(lead_id=lead_id)
        return qs


# ======================================
# FORM RESPONSES (Google Forms)
# ======================================


class FormResponseViewSet(viewsets.ModelViewSet):
    """
    Теперь НЕ только read-only:
    - GET /api/form-responses/
    - GET /api/form-responses/{id}/
    - PATCH /api/form-responses/{id}/ с parsed_answers для обновления raw_json
    """

    queryset = FormResponse.objects.all().order_by("-id")
    serializer_class = FormResponseSerializer

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        parsed_answers = request.data.get("parsed_answers")

        if parsed_answers is None:
            # ничего не меняем, просто возвращаем текущие данные
            serializer = self.get_serializer(instance)
            return Response(serializer.data)

        if not isinstance(parsed_answers, list):
            return Response(
                {"detail": "parsed_answers must be a list"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Загружаем текущее raw_json
        try:
            data = json.loads(instance.raw_json or "{}")
        except json.JSONDecodeError:
            data = {}

        answers = data.setdefault("answers", {})

        # Обновляем значения по question_id, в формате, похожем на Google Forms API
        for item in parsed_answers:
            qid = item.get("question_id")
            value = (item.get("value") or "").strip()
            if not qid:
                continue

            ans = answers.setdefault(qid, {})
            text_block = ans.setdefault("textAnswers", {})
            arr = text_block.setdefault("answers", [])

            if arr:
                # обновляем первый ответ
                arr[0]["value"] = value
            else:
                arr.append({"value": value})

        # Сохраняем обратно
        instance.raw_json = json.dumps(data, ensure_ascii=False)
        instance.save()

        serializer = self.get_serializer(instance)
        return Response(serializer.data)

# backend/crm/views.py (после FormResponseViewSet)

class FormResponseValidateAPIView(APIView):
    """
    POST /api/form-responses/{id}/validate/

    Валидирует один ответ Google Forms.
    Если у FormResponse есть lead_id, обновляет Lead.status и Lead.questionnaire_status,
    пишет запись в AuditLog и возвращает результат.

    Можно вызывать:
      - из CRM (кнопка "Проверить анкету")
      - из скрипта google_forms_sync сразу после записи FormResponse
    """

    def post(self, request, pk: int):
        form_response = get_object_or_404(FormResponse, pk=pk)

        result = validate_form_response_and_update_lead(form_response)

        return Response(result)

# ======================================
# AUDIT LOG
# ======================================


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    История событий по лидам.
    """

    serializer_class = AuditLogSerializer
    queryset = AuditLog.objects.all().order_by("-id")

    def get_queryset(self):
        qs = super().get_queryset()
        lead_id = self.request.query_params.get("lead_id")
        if lead_id:
            qs = qs.filter(lead_id=lead_id)
        return qs


# ======================================
# BOT SETTINGS
# ======================================


class BotSettingsView(generics.RetrieveUpdateAPIView):
    """
    Всегда работаем с единственной записью настроек (id=1).
    """

    serializer_class = BotSettingsSerializer

    def get_object(self):
        obj, _created = BotSettings.objects.get_or_create(id=1)
        return obj


# ======================================
# STATUSES (БЕЗ отдельной модели)
# ======================================


class StatusListAPIView(APIView):
    """
    Возвращает уникальный список статусов из таблицы leads.
    Пример:
    [
      {"code": "new", "label": "Новый"},
      {"code": "questionnaire_sent", "label": "Анкета отправлена"},
      ...
    ]
    """

    def get(self, request):
        raw_statuses = (
            Lead.objects
            .exclude(status__isnull=True)
            .exclude(status__exact="")
            .values_list("status", flat=True)
        )

        seen: set[str] = set()
        items: list[dict[str, str]] = []

        for s in raw_statuses:
            code = (s or "").strip()   # убираем пробелы вокруг
            if not code:
                continue
            if code in seen:
                continue
            seen.add(code)

            items.append({
                "code": code,
                "label": STATUS_LABELS.get(code, code),  # человекочитаемое имя
            })

        # можно отсортировать по коду, чтобы выпадающий список был аккуратным
        items.sort(key=lambda x: x["code"])
        return Response(items)


# ======================================
# VISAS (фиктивные данные, без БД)
# ======================================


VISA_DATA: Dict[str, Dict[str, Any]] = {
    "usa": {
        "code": "usa",
        "name": "США",
        "type": "Туристическая / Бизнес (B1/B2)",
        "description": "Оформление неиммиграционной визы США для туризма и деловых поездок.",
        "requirements": [
            "Заполненная анкета DS-160",
            "Действующий загранпаспорт",
            "Фотография по требованиям посольства",
            "Подтверждение записи на собеседование",
        ],
        "processing_time": "Обычно 2–8 недель, в зависимости от загруженности консульства.",
    },
    "poland": {
        "code": "poland",
        "name": "Польша",
        "type": "Национальная / Шенгенская виза",
        "description": "Оформление визы для поездок в Польшу: учеба, работа, туризм.",
        "requirements": [
            "Анкета на визу в Польшу",
            "Загранпаспорт",
            "Фотографии 3.5x4.5",
            "Подтверждение цели поездки (приглашение, бронирование и т.п.)",
        ],
        "processing_time": "От 7 до 30 дней.",
    },
    "france": {
        "code": "france",
        "name": "Франция",
        "type": "Шенгенская виза",
        "description": "Краткосрочная виза для поездок во Францию и другие страны Шенгена.",
        "requirements": [
            "Заполненная анкета",
            "Загранпаспорт",
            "Фотографии",
            "Подтверждение проживания и финансов",
        ],
        "processing_time": "От 5 до 15 дней.",
    },
    "italy": {
        "code": "italy",
        "name": "Италия",
        "type": "Шенгенская виза",
        "description": "Туристические и деловые поездки в Италию и другие страны Шенгена.",
        "requirements": [
            "Анкета на визу",
            "Загранпаспорт",
            "Фотографии",
            "Финансовые гарантии и бронь отеля/билетов",
        ],
        "processing_time": "От 5 до 15 дней.",
    },
    "spain": {
        "code": "spain",
        "name": "Испания",
        "type": "Шенгенская виза",
        "description": "Виза для отдыха и работы в Испании и шенгенской зоне.",
        "requirements": [
            "Анкета",
            "Загранпаспорт",
            "Фотографии",
            "Подтверждение проживания и доходов",
        ],
        "processing_time": "От 5 до 20 дней.",
    },
    "germany": {
        "code": "germany",
        "name": "Германия",
        "type": "Шенгенская виза",
        "description": "Служебные, деловые и туристические поездки в Германию.",
        "requirements": [
            "Анкета",
            "Загранпаспорт",
            "Фотографии",
            "Письмо от работодателя / приглашение",
        ],
        "processing_time": "От 5 до 20 дней.",
    },
    "schengen": {
        "code": "schengen",
        "name": "Шенген",
        "type": "Общая шенгенская виза",
        "description": "Виза для поездок по странам Шенгенского соглашения.",
        "requirements": [
            "Анкета",
            "Загранпаспорт",
            "Фотографии",
            "Маршрут поездки, бронь отелей, страховка",
        ],
        "processing_time": "От 5 до 20 дней.",
    },
}


class VisaListAPIView(APIView):
    """
    Список всех типов виз (фиктивные данные, без БД).
    """

    def get(self, request):
        return Response(list(VISA_DATA.values()))


class VisaDetailAPIView(APIView):
    """
    Детальная информация по визе.
    """

    def get(self, request, code: str):
        key = code.lower()
        visa = VISA_DATA.get(key)
        if not visa:
            return Response({"detail": "Visa not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(visa)


class VisaStartAPIView(APIView):
    """
    Фиктивный эндпоинт для "запуска" подачи на визу.
    Пишем запись в AuditLog (если передали lead_id) и возвращаем ок.
    """

    def post(self, request, code: str):
        key = code.lower()
        if key not in VISA_DATA:
            return Response({"detail": "Visa not found"}, status=status.HTTP_404_NOT_FOUND)

        lead_id = request.data.get("lead_id")
        if lead_id:
            AuditLog.objects.create(
                lead_id=lead_id,
                event="visa_start",
                details=f"User started visa process for {key}",
            )

        return Response(
            {"status": "ok", "message": f"Visa process started for {key}"},
            status=status.HTTP_200_OK,
        )
