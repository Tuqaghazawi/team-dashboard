from django.urls import path

from . import views

urlpatterns = [
    path("", views.mdc_board, name="mdc_board"),
    path("add/<int:patient_pk>/", views.add_listing, name="mdc_add_listing"),
    path("listing/<int:pk>/decision/", views.record_decision, name="record_decision"),
    path(
        "suggest/<int:patient_pk>/<str:kind>/",
        views.request_suggestion,
        name="request_suggestion",
    ),
    path(
        "deck/<int:mdc_pk>/<str:meeting_date>/",
        views.download_mdc_deck,
        name="download_mdc_deck",
    ),
    path("planning-deck/", views.download_planning_deck, name="download_planning_deck"),
]
