from django.http import HttpRequest, HttpResponse
from django.shortcuts import render


def home(request: HttpRequest) -> HttpResponse:
    """Home page. The location search form is added in Phase 3 (FR-4)."""
    return render(request, "weather/home.html")
