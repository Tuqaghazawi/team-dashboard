from django.urls import path

from . import views

urlpatterns = [
    path("add/<int:patient_pk>/", views.add_listing, name="mdc_add_listing"),
]
