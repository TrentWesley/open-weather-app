from django.contrib import messages
from django.contrib.auth import login
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from accounts.forms import RegistrationForm


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
