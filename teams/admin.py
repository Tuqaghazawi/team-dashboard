from django.contrib import admin

from .models import MDC, Team


@admin.register(MDC)
class MDCAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("consultant", "specialty")
    list_filter = ("specialty",)
    search_fields = ("consultant", "specialty")
