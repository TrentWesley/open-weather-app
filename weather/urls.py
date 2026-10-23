from django.urls import path

from weather import views

urlpatterns = [
    path("", views.home, name="home"),
    path("search/", views.search, name="search"),
    path("weather/", views.dashboard, name="dashboard"),
    path("weather/reverse/", views.reverse_geocode, name="reverse_geocode"),
    path(
        "weather/tiles/<str:layer>/<int:z>/<int:x>/<int:y>/", views.map_tile, name="map_tile"
    ),
    path("favorites/", views.favorites, name="favorites"),
    path("favorites/<int:pk>/delete/", views.delete_favorite, name="favorite_delete"),
]
