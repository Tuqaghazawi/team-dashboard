from django.urls import path

from . import views

urlpatterns = [
    path("", views.patient_list, name="patient_list"),
    path("register/", views.patient_register, name="patient_register"),
    path("<int:pk>/", views.patient_detail, name="patient_detail"),
    path("<int:pk>/clinical/", views.edit_clinical, name="edit_clinical"),
    # Workup
    path("<int:pk>/workup/start/", views.begin_workup, name="begin_workup"),
    path("<int:pk>/workup/add/", views.add_investigation, name="add_investigation"),
    path(
        "<int:pk>/workup/<int:investigation_pk>/result/",
        views.record_result,
        name="record_result",
    ),
    # Neoadjuvant treatment
    path("<int:pk>/treatment/start/", views.start_treatment, name="start_treatment"),
    path("<int:pk>/treatment/<int:course_pk>/cycle/", views.record_cycle, name="record_cycle"),
    path("<int:pk>/treatment/<int:course_pk>/close/", views.close_treatment, name="close_treatment"),
    # Surgery
    path("<int:pk>/surgery/list/", views.list_for_surgery, name="list_for_surgery"),
    path(
        "<int:pk>/surgery/<int:booking_pk>/performed/",
        views.record_surgery,
        name="record_surgery",
    ),
]
