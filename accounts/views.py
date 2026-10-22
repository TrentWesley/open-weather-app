from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.views import LoginView
from django.core.exceptions import NON_FIELD_ERRORS
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from accounts.forms import LoginForm, RegistrationForm
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
