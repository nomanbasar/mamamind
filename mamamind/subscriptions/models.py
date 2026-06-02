from django.conf import settings
from django.db import models


class SubscriptionPlan(models.Model):
    class BillingCycle(models.TextChoices):
        MONTHLY = "monthly", "Monthly"
        YEARLY = "yearly", "Yearly"

    name = models.CharField(max_length=100)
    code = models.SlugField(max_length=100, unique=True)

    price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default="usd")
    billing_cycle = models.CharField(
        max_length=20,
        choices=BillingCycle.choices,
        default=BillingCycle.MONTHLY,
    )

    member_limit = models.PositiveIntegerField(default=1)
    description = models.TextField(blank=True, null=True)
    features = models.JSONField(default=list, blank=True)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["price", "id"]

    def __str__(self):
        return f"{self.name} - {self.price} {self.currency}"


class UserSubscription(models.Model):
    class Status(models.TextChoices):
        INCOMPLETE = "incomplete", "Incomplete"
        ACTIVE = "active", "Active"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Expired"
        PAST_DUE = "past_due", "Past Due"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="subscriptions",
    )
    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.PROTECT,
        related_name="user_subscriptions",
    )

    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.INCOMPLETE,
    )

    stripe_customer_id = models.CharField(max_length=255, blank=True, null=True)
    stripe_subscription_id = models.CharField(max_length=255, blank=True, null=True)
    stripe_checkout_session_id = models.CharField(max_length=255, blank=True, null=True)

    current_period_start = models.DateTimeField(blank=True, null=True)
    current_period_end = models.DateTimeField(blank=True, null=True)

    cancel_at_period_end = models.BooleanField(default=False)
    cancelled_at = models.DateTimeField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return f"{self.user.email} - {self.plan.name} - {self.status}"