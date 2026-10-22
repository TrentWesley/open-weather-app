from django.urls import path

from weather import views

urlpatterns = [
    path("", views.home, name="home"),
    path("search/", views.search, name="search"),
    path("weather/", views.dashboard, name="dashboard"),
    path("weather/reverse/", views.reverse_geocode, name="reverse_geocode"),
]
