from django.contrib import admin

from .models import Reminder


@admin.register(Reminder)
class ReminderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "family",
        "owner",
        "created_by",
        "visibility",
        "recurring",
        "reminder_date",
        "reminder_time",
        "is_completed",
        "created_at",
    )
    list_filter = (
        "visibility",
        "recurring",
        "is_completed",
        "reminder_date",
        "family",
    )
    search_fields = (
        "title",
        "family__name",
        "owner__email",
        "owner__full_name",
        "created_by__email",
        "created_by__full_name",
    )