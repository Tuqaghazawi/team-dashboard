from django.contrib import admin

from .models import Patient


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ("name", "mrn", "age", "specialty", "team", "stage", "next_review_date", "registered_at")
    list_filter = ("specialty", "stage", "team")
    search_fields = ("name", "mrn", "diagnosis")
    list_select_related = ("team",)
