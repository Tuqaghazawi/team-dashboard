from django.contrib import admin

from .models import MDCListing


@admin.register(MDCListing)
class MDCListingAdmin(admin.ModelAdmin):
    list_display = ("patient", "mdc", "meeting_date", "presented", "added_at")
    list_filter = ("mdc", "meeting_date", "presented")
    search_fields = ("patient__name", "patient__mrn")
    list_select_related = ("patient", "mdc")
    date_hierarchy = "meeting_date"
