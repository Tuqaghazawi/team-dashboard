from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("kind", "recipient", "patient", "created_at", "read_at", "emailed_at")
    list_filter = ("kind", "created_at")
    search_fields = ("subject", "patient__name", "patient__mrn")
