# backend/crm/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    LeadViewSet,
    LeadFormViewSet,
    FormResponseViewSet,
    AuditLogViewSet,
    LeadDetailAPIView,
    LeadQuestionnaireAPIView,   # 👈 НОВОЕ
    BotSettingsView,
    StatusListAPIView,
    VisaListAPIView,
    VisaDetailAPIView,
    VisaStartAPIView,
    FormResponseValidateAPIView,
)

router = DefaultRouter()
router.register(r"leads", LeadViewSet, basename="lead")
router.register(r"lead-forms", LeadFormViewSet, basename="lead-form")
router.register(r"form-responses", FormResponseViewSet, basename="form-response")
router.register(r"audit-log", AuditLogViewSet, basename="audit-log")

urlpatterns = [
    path("", include(router.urls)),

    # Детальный лид
    path("leads/<int:pk>/detail/", LeadDetailAPIView.as_view(), name="lead-detail"),

    # Сводная анкета по лиду
    path(
        "leads/<int:pk>/questionnaire/",
        LeadQuestionnaireAPIView.as_view(),
        name="lead-questionnaire",
    ),
    path(
        "form-responses/<int:pk>/validate/",
        FormResponseValidateAPIView.as_view(),
        name="form-response-validate",
    ),
    # Настройки бота
    path("bot-settings/", BotSettingsView.as_view(), name="bot-settings"),

    # Статусы (из таблицы leads)
    path("statuses/", StatusListAPIView.as_view(), name="statuses"),

    # Визы
    path("visas/", VisaListAPIView.as_view(), name="visa-list"),
    path("visas/<str:code>/", VisaDetailAPIView.as_view(), name="visa-detail"),
    path("visas/<str:code>/start/", VisaStartAPIView.as_view(), name="visa-start"),
]
