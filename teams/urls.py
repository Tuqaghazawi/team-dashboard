from django.urls import path

from . import views

urlpatterns = [
    path("rotations/", views.rotation_list, name="rotation_list"),
]
