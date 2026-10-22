from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.core.exceptions import NON_FIELD_ERRORS
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST

from accounts.forms import LoginForm, RegistrationForm, UnitPreferenceForm
from accounts.preferences import get_unit, set_unit
from accounts.ratelimit import LoginRateLimiter


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
    """FR-2: Django's LoginView, which validates `next` (NFR-SEC-8), plus rate limiting.

    NFR-SEC-7: blocked requests are refused before credentials are checked.
    """

    template_name = "accounts/login.html"
    authentication_form = LoginForm
    rate_limited_message = (
        "Too many failed login attempts. Please wait a few minutes and try again."
    )

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        self.limiter = LoginRateLimiter()
        self.client_ip = request.META.get("REMOTE_ADDR", "")
        self.attempted_username = request.POST.get("username", "")
        if self.limiter.is_blocked(self.client_ip, self.attempted_username):
            context = self.get_context_data(
                form=self.authentication_form(request),
                rate_limited_message=self.rate_limited_message,
            )
            return self.render_to_response(context, status=429)
        return super().post(request, *args, **kwargs)

    def form_valid(self, form: LoginForm) -> HttpResponse:
        self.limiter.reset(self.attempted_username)
        return super().form_valid(form)

    def form_invalid(self, form: LoginForm) -> HttpResponse:
        if form.has_error(NON_FIELD_ERRORS, "invalid_login"):
            self.limiter.record_failure(self.client_ip, self.attempted_username)
        return super().form_invalid(form)


@require_POST
def logout_view(request: HttpRequest) -> HttpResponse:
    """FR-2 AC-5: POST-only logout that ends the session and confirms it."""
    logout(request)
    messages.success(request, "You have been logged out.")
    return redirect("home")


@login_required
@require_http_methods(["GET", "POST"])
def preferences(request: HttpRequest) -> HttpResponse:
    """FR-3 AC-1/2: the logged-in user's preferences page."""
    form = UnitPreferenceForm(
        request.POST or None, initial={"temperature_unit": get_unit(request)}
    )
    if request.method == "POST" and form.is_valid():
        unit = set_unit(request, form.cleaned_data["temperature_unit"])
        messages.success(request, f"Temperature unit set to {unit.label}.")
        return redirect("preferences")
    return render(request, "accounts/preferences.html", {"form": form})


@require_POST
def toggle_unit(request: HttpRequest) -> HttpResponse:
    """FR-3 AC-1/3/5: switch units for anyone, then return to the same page."""
    form = UnitPreferenceForm(request.POST)
    if not form.is_valid():
        return HttpResponseBadRequest("Unknown temperature unit.")
    set_unit(request, form.cleaned_data["temperature_unit"])
    next_url = request.POST.get("next", "")
    if url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(next_url)
    return redirect("home")
