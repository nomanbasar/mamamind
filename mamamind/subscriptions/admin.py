from django.contrib import admin

from .models import SubscriptionPlan, UserSubscription


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "code",
        "price",
        "currency",
        "billing_cycle",
        "member_limit",
        "is_active",
        "created_at",
    )
    list_filter = (
        "billing_cycle",
        "currency",
        "is_active",
    )
    search_fields = (
        "name",
        "code",
        "description",
    )
    ordering = ("price", "id")


@admin.register(UserSubscription)
class UserSubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "plan",
        "status",
        "current_period_start",
        "current_period_end",
        "cancel_at_period_end",
        "created_at",
    )
    list_filter = (
        "status",
        "cancel_at_period_end",
        "plan",
    )
    search_fields = (
        "user__email",
        "user__full_name",
        "stripe_customer_id",
        "stripe_subscription_id",
    )
    ordering = ("-id",)