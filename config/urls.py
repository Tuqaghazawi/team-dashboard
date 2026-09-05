"""URL routing for the surgical oncology dashboard."""

from django.contrib import admin
from django.urls import include, path

from patients import views as patient_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),

    path('', patient_views.dashboard, name='dashboard'),
    path('patients/', include('patients.urls')),
    path('treatment/', patient_views.treatment_list, name='treatment_list'),
    path('surgery/', patient_views.surgery_schedule, name='surgery_schedule'),

    path('mdc/', include('mdc.urls')),
    path('inbox/', include('notifications.urls')),
    path('reports/', include('reports.urls')),
    path('teams/', include('teams.urls')),
]
