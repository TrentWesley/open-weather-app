from django.urls import path

from accounts import views

urlpatterns = [
    path("accounts/register/", views.register, name="register"),
    path("accounts/login/", views.AccountLoginView.as_view(), name="login"),
    path("accounts/logout/", views.logout_view, name="logout"),
]
