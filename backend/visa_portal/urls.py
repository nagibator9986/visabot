from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView

urlpatterns = [
    # admin по желанию, можно убрать
    path("admin/", admin.site.urls),
    path("api/", include("crm.urls")),

    re_path(r'^.*$', TemplateView.as_view(template_name='index.html')),
]
