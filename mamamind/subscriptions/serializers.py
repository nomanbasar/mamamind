from rest_framework import serializers
from .models import SubscriptionPlan, UserSubscription


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    billing_cycle_display = serializers.CharField(
        source="get_billing_cycle_display",
        read_only=True,
    )

    class Meta:
        model = SubscriptionPlan
        fields = [
            "id",
            "name",
            "code",
            "price",
            "currency",
            "billing_cycle",
            "billing_cycle_display",
            "member_limit",
            "description",
            "features",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "billing_cycle_display",
            "created_at",
            "updated_at",
        ]


class PublicSubscriptionPlanSerializer(serializers.ModelSerializer):
    billing_cycle_display = serializers.CharField(
        source="get_billing_cycle_display",
        read_only=True,
    )
    is_current = serializers.SerializerMethodField()

    class Meta:
        model = SubscriptionPlan
        fields = [
            "id",
            "name",
            "code",
            "price",
            "currency",
            "billing_cycle",
            "billing_cycle_display",
            "member_limit",
            "description",
            "features",
            "is_current",
        ]

    def get_is_current(self, obj):
        current_subscription = self.context.get("current_subscription")

        if not current_subscription:
            return False

        return current_subscription.plan_id == obj.id and current_subscription.status == UserSubscription.Status.ACTIVE


class UserSubscriptionSerializer(serializers.ModelSerializer):
    plan = PublicSubscriptionPlanSerializer(read_only=True)
    status_display = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )

    class Meta:
        model = UserSubscription
        fields = [
            "id",
            "plan",
            "status",
            "status_display",
            "stripe_customer_id",
            "stripe_subscription_id",
            "current_period_start",
            "current_period_end",
            "cancel_at_period_end",
            "cancelled_at",
            "created_at",
            "updated_at",
        ]


class CheckoutSerializer(serializers.Serializer):
    plan_id = serializers.IntegerField()

    def validate_plan_id(self, value):
        plan = SubscriptionPlan.objects.filter(
            id=value,
            is_active=True,
        ).first()

        if not plan:
            raise serializers.ValidationError("Active subscription plan not found")

        self.context["plan"] = plan
        return value


class CancelSubscriptionSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, allow_null=True)




class UserSubscriptionInvoiceSerializer(serializers.ModelSerializer):
    invoice_number = serializers.SerializerMethodField()
    date = serializers.SerializerMethodField()
    plan = serializers.SerializerMethodField()
    amount = serializers.SerializerMethodField()
    currency = serializers.SerializerMethodField()
    status_display = serializers.SerializerMethodField()
    pdf_url = serializers.SerializerMethodField()

    class Meta:
        model = UserSubscription
        fields = [
            "id",
            "invoice_number",
            "date",
            "plan",
            "amount",
            "currency",
            "status",
            "status_display",
            "pdf_url",
            "stripe_checkout_session_id",
            "created_at",
        ]

    def get_invoice_number(self, obj):
        year = obj.created_at.year if obj.created_at else 2026
        return f"INV-{year}-{obj.id:03d}"

    def get_date(self, obj):
        if obj.current_period_start:
            return obj.current_period_start.date()
        if obj.created_at:
            return obj.created_at.date()
        return None

    def get_plan(self, obj):
        return obj.plan.name if obj.plan else None

    def get_amount(self, obj):
        if obj.plan:
            return str(obj.plan.price)
        return "0.00"

    def get_currency(self, obj):
        if obj.plan:
            return obj.plan.currency
        return "usd"

    def get_status_display(self, obj):
        if hasattr(obj, "get_status_display"):
            return obj.get_status_display()
        return obj.status

    def get_pdf_url(self, obj):
        return None