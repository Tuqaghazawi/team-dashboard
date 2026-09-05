from django.urls import path

from . import views

urlpatterns = [
    path("", views.reports_home, name="reports_home"),
    path("<str:period>/download/", views.download_report, name="download_report"),
]
