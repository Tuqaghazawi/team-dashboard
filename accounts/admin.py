from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    """Show our extra ``role`` field in the admin panel."""

    # Columns shown in the list of users
    list_display = ("username", "first_name", "last_name", "role", "is_staff")
    list_filter = UserAdmin.list_filter + ("role",)

    # Add a "Role" section to the user edit page and the "add user" page
    fieldsets = UserAdmin.fieldsets + (("Role", {"fields": ("role",)}),)
    add_fieldsets = UserAdmin.add_fieldsets + (("Role", {"fields": ("role",)}),)
