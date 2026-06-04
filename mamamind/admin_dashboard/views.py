from decimal import Decimal
from datetime import timedelta

from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from authentication.models import User
from subscriptions.models import UserSubscription, SubscriptionPlan


def success_response(message, data=None, status_code=status.HTTP_200_OK):
    return Response(
        {
            "success": True,
            "message": message,
            "data": data or {},
        },
        status=status_code,
    )


def error_response(message, data=None, status_code=status.HTTP_400_BAD_REQUEST):
    return Response(
        {
            "success": False,
            "message": message,
            "data": data or {},
        },
        status=status_code,
    )


def is_admin_user(user):
    if not user or not user.is_authenticated:
        return False

    return (
        getattr(user, "role", None) == User.Role.ADMIN
        or user.is_staff
        or user.is_superuser
    )


def money(value):
    value = Decimal(value or 0)
    return f"{value:.2f}"


def percent(value):
    value = Decimal(value or 0)
    return f"{value:.2f}"


def percentage_change(current, previous):
    """
    Previous period 0 হলে real percentage change calculate করা যায় না.
    Current > 0 এবং previous = 0 হলে None return করব.
    Frontend চাইলে এই case-এ 'New this period' দেখাবে.
    """
    current = Decimal(current or 0)
    previous = Decimal(previous or 0)

    if previous == 0:
        if current == 0:
            return "0.00"
        return None

    result = ((current - previous) / previous) * Decimal("100")
    return f"{result:.2f}"


def change_label(current, previous, default_label):
    current = Decimal(current or 0)
    previous = Decimal(previous or 0)

    if previous == 0 and current > 0:
        return "New this period"

    return default_label


def subscription_revenue(queryset):
    total = Decimal("0.00")

    for subscription in queryset.select_related("plan"):
        if subscription.plan and subscription.plan.price:
            total += Decimal(subscription.plan.price)

    return total


def month_add(month_start, offset):
    year = month_start.year
    month = month_start.month + offset

    while month <= 0:
        month += 12
        year -= 1

    while month > 12:
        month -= 12
        year += 1

    return month_start.replace(year=year, month=month, day=1)


def build_monthly_revenue_chart():
    today = timezone.localdate()
    this_month_start = today.replace(day=1)

    chart = []

    for offset in range(-5, 1):
        month_start = month_add(this_month_start, offset)
        next_month_start = month_add(month_start, 1)

        monthly_subscriptions = UserSubscription.objects.filter(
            created_at__date__gte=month_start,
            created_at__date__lt=next_month_start,
        ).exclude(
            status__in=[
                UserSubscription.Status.INCOMPLETE,
                UserSubscription.Status.CANCELLED,
            ]
        ).select_related("plan")

        revenue = subscription_revenue(monthly_subscriptions)

        chart.append(
            {
                "month": month_start.strftime("%b"),
                "year": month_start.year,
                "revenue": money(revenue),
            }
        )

    return chart


def build_subscribers_by_plan():
    active_subscriptions = UserSubscription.objects.filter(
        status=UserSubscription.Status.ACTIVE
    ).select_related("plan")

    total_active = active_subscriptions.count()

    plans = SubscriptionPlan.objects.all().order_by("id")

    result = []

    for plan in plans:
        count = active_subscriptions.filter(plan=plan).count()

        if total_active > 0:
            plan_percentage = (Decimal(count) / Decimal(total_active)) * Decimal("100")
        else:
            plan_percentage = Decimal("0.00")

        result.append(
            {
                "plan_id": plan.id,
                "plan_name": plan.name,
                "plan_code": plan.code,
                "count": count,
                "percentage": percent(plan_percentage),
            }
        )

    return result


def admin_profile(user, request):
    profile_image = None
    profile_image_url = None

    if getattr(user, "profile_image", None):
        try:
            profile_image = user.profile_image.url
            profile_image_url = request.build_absolute_uri(user.profile_image.url)
        except Exception:
            profile_image = None
            profile_image_url = None

    return {
        "id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "role": user.role,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
        "profile_image": profile_image,
        "profile_image_url": profile_image_url,
    }


class AdminDashboardOverviewView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not is_admin_user(request.user):
            return error_response(
                message="Only admin can access this resource",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        try:
            days = int(request.query_params.get("days", 30))
        except ValueError:
            days = 30

        if days not in [7, 30, 90, 180, 365]:
            days = 30

        now = timezone.now()
        current_start = now - timedelta(days=days)
        previous_start = current_start - timedelta(days=days)

        users_qs = User.objects.exclude(role=User.Role.ADMIN)
        family_owner_qs = User.objects.filter(role=User.Role.FAMILY_OWNER)

        total_users = users_qs.count()
        total_family_owners = family_owner_qs.count()

        users_this_period = users_qs.filter(
            date_joined__gte=current_start
        ).count()

        users_previous_period = users_qs.filter(
            date_joined__gte=previous_start,
            date_joined__lt=current_start,
        ).count()

        active_subscriptions_qs = UserSubscription.objects.filter(
            status=UserSubscription.Status.ACTIVE
        ).select_related("plan")

        active_subscription_count = active_subscriptions_qs.count()

        active_subscriptions_this_period = UserSubscription.objects.filter(
            status=UserSubscription.Status.ACTIVE,
            created_at__gte=current_start,
        ).count()

        active_subscriptions_previous_period = UserSubscription.objects.filter(
            status=UserSubscription.Status.ACTIVE,
            created_at__gte=previous_start,
            created_at__lt=current_start,
        ).count()

        if total_family_owners > 0:
            active_subscription_ratio = (
                Decimal(active_subscription_count) / Decimal(total_family_owners)
            ) * Decimal("100")
        else:
            active_subscription_ratio = Decimal("0.00")

        current_paid_subscriptions = UserSubscription.objects.filter(
            created_at__gte=current_start,
        ).exclude(
            status__in=[
                UserSubscription.Status.INCOMPLETE,
                UserSubscription.Status.CANCELLED,
            ]
        ).select_related("plan")

        previous_paid_subscriptions = UserSubscription.objects.filter(
            created_at__gte=previous_start,
            created_at__lt=current_start,
        ).exclude(
            status__in=[
                UserSubscription.Status.INCOMPLETE,
                UserSubscription.Status.CANCELLED,
            ]
        ).select_related("plan")

        current_revenue = subscription_revenue(current_paid_subscriptions)
        previous_revenue = subscription_revenue(previous_paid_subscriptions)

        cancelled_this_period = UserSubscription.objects.filter(
            status=UserSubscription.Status.CANCELLED,
            updated_at__gte=current_start,
        ).count()

        cancelled_previous_period = UserSubscription.objects.filter(
            status=UserSubscription.Status.CANCELLED,
            updated_at__gte=previous_start,
            updated_at__lt=current_start,
        ).count()

        total_active_or_cancelled = UserSubscription.objects.filter(
            status__in=[
                UserSubscription.Status.ACTIVE,
                UserSubscription.Status.CANCELLED,
            ]
        ).count()

        if total_active_or_cancelled > 0:
            churn_rate = (
                Decimal(cancelled_this_period) / Decimal(total_active_or_cancelled)
            ) * Decimal("100")
        else:
            churn_rate = Decimal("0.00")

        previous_active_or_cancelled = UserSubscription.objects.filter(
            status__in=[
                UserSubscription.Status.ACTIVE,
                UserSubscription.Status.CANCELLED,
            ],
            created_at__lt=current_start,
        ).count()

        if previous_active_or_cancelled > 0:
            previous_churn_rate = (
                Decimal(cancelled_previous_period) / Decimal(previous_active_or_cancelled)
            ) * Decimal("100")
        else:
            previous_churn_rate = Decimal("0.00")

        return success_response(
            message="Admin dashboard overview retrieved successfully",
            data={
                "period": {
                    "label": f"{days} days",
                    "days": days,
                    "start": current_start,
                    "end": now,
                },
                "admin": admin_profile(request.user, request),
                "notifications": {
                    "unread_count": 0,
                },
                "stats": {
                    "total_users": {
                        "value": total_users,
                        "change_percent": percentage_change(
                            users_this_period,
                            users_previous_period,
                        ),
                        "change_label": change_label(
                            users_this_period,
                            users_previous_period,
                            f"+{users_this_period} this period",
                        ),
                        "new_this_period": users_this_period,
                        "previous_period": users_previous_period,
                    },
                    "active_subscriptions": {
                        "value": active_subscription_count,
                        "change_percent": percentage_change(
                            active_subscriptions_this_period,
                            active_subscriptions_previous_period,
                        ),
                        "change_label": change_label(
                            active_subscriptions_this_period,
                            active_subscriptions_previous_period,
                            "vs previous period",
                        ),
                        "ratio_label": f"{active_subscription_ratio:.1f}% of family owners",
                        "total_family_owners": total_family_owners,
                        "new_this_period": active_subscriptions_this_period,
                        "previous_period": active_subscriptions_previous_period,
                    },
                    "monthly_revenue": {
                        "value": money(current_revenue),
                        "currency": "usd",
                        "change_percent": percentage_change(
                            current_revenue,
                            previous_revenue,
                        ),
                        "change_label": change_label(
                            current_revenue,
                            previous_revenue,
                            "vs previous period",
                        ),
                        "previous_period_revenue": money(previous_revenue),
                    },
                    "churn_rate": {
                        "value": percent(churn_rate),
                        "change_percent": percentage_change(
                            churn_rate,
                            previous_churn_rate,
                        ),
                        "change_label": change_label(
                            churn_rate,
                            previous_churn_rate,
                            "vs previous period",
                        ),
                        "cancelled_this_period": cancelled_this_period,
                        "cancelled_previous_period": cancelled_previous_period,
                    },
                },
                "monthly_revenue_chart": build_monthly_revenue_chart(),
                "subscribers_by_plan": build_subscribers_by_plan(),
            },
            status_code=status.HTTP_200_OK,
        )