from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.views import LoginView
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from accounts.forms import LoginForm, RegistrationForm


@require_http_methods(["GET", "POST"])
def register(request: HttpRequest) -> HttpResponse:
    """FR-1: create an account, log the new user in, and send them home."""
    if request.user.is_authenticated:
        return redirect("home")
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, f"Account created. Welcome, {user.username}!")
        return redirect("home")
    return render(request, "accounts/register.html", {"form": form})


class AccountLoginView(LoginView):
    """FR-2: Django's LoginView, which validates `next` (NFR-SEC-8), with our form."""

    template_name = "accounts/login.html"
    authentication_form = LoginForm


@require_POST
def logout_view(request: HttpRequest) -> HttpResponse:
    """FR-2 AC-5: POST-only logout that ends the session and confirms it."""
    logout(request)
    messages.success(request, "You have been logged out.")
    return redirect("home")
