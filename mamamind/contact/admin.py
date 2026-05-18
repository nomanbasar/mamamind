from django.contrib import admin

from .models import ContactMessage


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "email",
        "enquiry_type",
        "subject",
        "status",
        "created_at",
    )
    list_filter = (
        "enquiry_type",
        "status",
        "created_at",
    )
    search_fields = (
        "name",
        "email",
        "subject",
        "message",
    )
    ordering = ("-id",)