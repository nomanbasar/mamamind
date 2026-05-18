from django.contrib import admin

from .models import FAQ


@admin.register(FAQ)
class FAQAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "question",
        "category",
        "is_active",
        "created_at",
    )
    list_filter = ("category", "is_active")
    search_fields = ("question", "answer")
    ordering = ("-id",)