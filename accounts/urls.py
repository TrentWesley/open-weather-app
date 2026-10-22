from django.urls import path

from accounts import views

urlpatterns = [
    path("accounts/register/", views.register, name="register"),
]
