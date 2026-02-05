from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    # admin по желанию, можно убрать
    path("admin/", admin.site.urls),
    path("api/", include("crm.urls")),
]
