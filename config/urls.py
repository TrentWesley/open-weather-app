"""Root URL configuration; see the URL table in AGENTS.md."""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("accounts.urls")),
    path("", include("weather.urls")),
]
