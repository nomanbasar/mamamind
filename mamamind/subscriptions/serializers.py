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