from django.urls import path

from . import views

urlpatterns = [
    path("", views.team_home, name="team_home"),
    path("rotations/", views.rotation_list, name="rotation_list"),
    path("<int:pk>/", views.team_detail, name="team_detail"),
]
