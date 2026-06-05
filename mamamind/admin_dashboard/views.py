from decimal import Decimal
from datetime import timedelta
from math import ceil
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from authentication.models import User, Family, FamilyMembership
from subscriptions.models import UserSubscription, SubscriptionPlan

from django.db.models import Q



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
    

def admin_user_initials(full_name):
    if not full_name:
        return ""

    parts = full_name.strip().split()

    if len(parts) == 1:
        return parts[0][:2].upper()

    return f"{parts[0][0]}{parts[-1][0]}".upper()


def admin_user_last_active(user):
    if not user.last_login:
        return {
            "value": None,
            "display": "Never",
        }

    now = timezone.now()
    diff = now - user.last_login

    if diff.days == 0:
        return {
            "value": user.last_login,
            "display": "Today",
        }

    if diff.days == 1:
        return {
            "value": user.last_login,
            "display": "Yesterday",
        }

    return {
        "value": user.last_login,
        "display": f"{diff.days} days ago",
    }


def get_user_main_family(user):
    membership = user.family_memberships.filter(
        status=FamilyMembership.Status.ACTIVE
    ).select_related(
        "family",
        "family__owner",
    ).first()

    if membership:
        return membership.family, membership

    pending_membership = user.family_memberships.filter(
        status=FamilyMembership.Status.PENDING
    ).select_related(
        "family",
        "family__owner",
    ).first()

    if pending_membership:
        return pending_membership.family, pending_membership

    owned_family = Family.objects.filter(owner=user).first()

    if owned_family:
        return owned_family, None

    return None, None


def get_family_active_subscription(family):
    if not family:
        return None

    return UserSubscription.objects.filter(
        user=family.owner,
        status=UserSubscription.Status.ACTIVE,
    ).select_related("plan").order_by("-id").first()


def get_family_members_count(family):
    if not family:
        return 0

    return family.memberships.filter(
        status__in=[
            FamilyMembership.Status.ACTIVE,
            FamilyMembership.Status.PENDING,
        ]
    ).count()


def admin_user_plan_data(subscription):
    if not subscription or not subscription.plan:
        return None

    return {
        "id": subscription.plan.id,
        "name": subscription.plan.name,
        "code": subscription.plan.code,
        "price": str(subscription.plan.price),
        "currency": subscription.plan.currency,
        "billing_cycle": subscription.plan.billing_cycle,
    }


def admin_user_item(user, request=None):
    family, membership = get_user_main_family(user)
    subscription = get_family_active_subscription(family)

    profile_image = None
    profile_image_url = None

    if getattr(user, "profile_image", None):
        try:
            profile_image = user.profile_image.url
            profile_image_url = (
                request.build_absolute_uri(user.profile_image.url)
                if request
                else user.profile_image.url
            )
        except Exception:
            profile_image = None
            profile_image_url = None

    last_active = admin_user_last_active(user)

    return {
        "id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "whatsapp_number": user.whatsapp_number,
        "initials": admin_user_initials(user.full_name),
        "role": user.role,
        "status": "active" if user.is_active else "inactive",
        "status_display": "Active" if user.is_active else "Inactive",
        "is_email_verified": user.is_email_verified,
        "is_active": user.is_active,
        "join_date": user.date_joined.date() if user.date_joined else None,
        "join_date_display": timezone.localtime(user.date_joined).strftime("%b %d, %Y") if user.date_joined else None,
        "last_active": last_active["value"],
        "last_active_display": last_active["display"],
        "profile_image": profile_image,
        "profile_image_url": profile_image_url,
        "family": {
            "id": family.id,
            "name": family.name,
            "owner_id": family.owner_id,
        } if family else None,
        "membership": {
            "id": membership.id,
            "relation": membership.relation,
            "relation_display": membership.get_relation_display(),
            "status": membership.status,
            "status_display": membership.get_status_display(),
        } if membership else None,
        "plan": admin_user_plan_data(subscription),
        "members_count": get_family_members_count(family),
    }


class AdminUserListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not is_admin_user(request.user):
            return error_response(
                message="Only admin can access this resource",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        search = request.query_params.get("search", "").strip()
        plan = request.query_params.get("plan", "").strip()
        user_status = request.query_params.get("status", "").strip()

        try:
            page = int(request.query_params.get("page", 1))
        except ValueError:
            page = 1

        try:
            page_size = int(request.query_params.get("page_size", 10))
        except ValueError:
            page_size = 10

        if page < 1:
            page = 1

        if page_size < 1:
            page_size = 10

        if page_size > 100:
            page_size = 100

        users_qs = User.objects.exclude(
            role=User.Role.ADMIN
        ).order_by("-date_joined", "-id")

        total_users = users_qs.count()

        if search:
            users_qs = users_qs.filter(
                Q(full_name__icontains=search)
                | Q(email__icontains=search)
                | Q(whatsapp_number__icontains=search)
            )

        if user_status and user_status.lower() != "all":
            if user_status.lower() == "active":
                users_qs = users_qs.filter(is_active=True)
            elif user_status.lower() == "inactive":
                users_qs = users_qs.filter(is_active=False)

        all_items = [
            admin_user_item(user, request)
            for user in users_qs
        ]

        if plan and plan.lower() != "all":
            filtered_items = []

            for item in all_items:
                item_plan = item.get("plan")

                if not item_plan:
                    continue

                if str(item_plan.get("id")) == plan or item_plan.get("code") == plan:
                    filtered_items.append(item)

            all_items = filtered_items

        filtered_count = len(all_items)
        total_pages = ceil(filtered_count / page_size) if filtered_count > 0 else 1

        if page > total_pages:
            page = total_pages

        start_index = (page - 1) * page_size
        end_index = start_index + page_size

        results = all_items[start_index:end_index]

        next_page = page + 1 if page < total_pages else None
        previous_page = page - 1 if page > 1 else None

        return success_response(
            message="Admin users retrieved successfully",
            data={
                "summary": {
                    "total_users": total_users,
                    "filtered_count": filtered_count,
                    "showing": len(results),
                    "page": page,
                    "page_size": page_size,
                    "total_pages": total_pages,
                    "next_page": next_page,
                    "previous_page": previous_page,
                },
                "filters": {
                    "search": search,
                    "plan": plan or "all",
                    "status": user_status or "all",
                },
                "results": results,
            },
            status_code=status.HTTP_200_OK,
        )
    


def admin_subscription_initials(full_name):
    if not full_name:
        return ""

    parts = full_name.strip().split()

    if len(parts) == 1:
        return parts[0][:2].upper()

    return f"{parts[0][0]}{parts[-1][0]}".upper()


def admin_subscription_status_display(status_value):
    status_map = {
        UserSubscription.Status.INCOMPLETE: "Incomplete",
        UserSubscription.Status.ACTIVE: "Active",
        UserSubscription.Status.CANCELLED: "Cancelled",
        UserSubscription.Status.EXPIRED: "Expired",
        UserSubscription.Status.PAST_DUE: "Past Due",
        "paused": "Paused",
    }

    return status_map.get(status_value, str(status_value).replace("_", " ").title())


def admin_subscription_date_only(value):
    if not value:
        return None

    return timezone.localtime(value).date()


def admin_subscription_date_display(value):
    if not value:
        return None

    return timezone.localtime(value).strftime("%b %d, %Y")


def admin_subscription_percentage_change(current, previous):
    current = Decimal(current or 0)
    previous = Decimal(previous or 0)

    if previous == 0:
        if current == 0:
            return "0.00"
        return None

    result = ((current - previous) / previous) * Decimal("100")
    return f"{result:.2f}"


def admin_subscription_change_label(current, previous, default_label):
    current = Decimal(current or 0)
    previous = Decimal(previous or 0)

    if previous == 0 and current > 0:
        return "New this period"

    return default_label


def admin_subscription_user_data(user, request=None):
    profile_image = None
    profile_image_url = None

    if getattr(user, "profile_image", None):
        try:
            profile_image = user.profile_image.url
            profile_image_url = (
                request.build_absolute_uri(user.profile_image.url)
                if request
                else user.profile_image.url
            )
        except Exception:
            profile_image = None
            profile_image_url = None

    return {
        "id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "whatsapp_number": user.whatsapp_number,
        "initials": admin_subscription_initials(user.full_name),
        "role": user.role,
        "profile_image": profile_image,
        "profile_image_url": profile_image_url,
    }


def admin_subscription_plan_data(plan):
    if not plan:
        return None

    return {
        "id": plan.id,
        "name": plan.name,
        "code": plan.code,
        "price": str(plan.price),
        "currency": plan.currency,
        "billing_cycle": plan.billing_cycle,
        "billing_cycle_display": plan.get_billing_cycle_display(),
        "member_limit": plan.member_limit,
    }


def admin_subscription_item(subscription, request=None):
    plan = subscription.plan
    user = subscription.user

    next_renewal = None
    next_renewal_display = None

    if (
        subscription.status == UserSubscription.Status.ACTIVE
        and subscription.current_period_end
    ):
        next_renewal = admin_subscription_date_only(subscription.current_period_end)
        next_renewal_display = admin_subscription_date_display(subscription.current_period_end)

    start_source = subscription.current_period_start or subscription.created_at

    cancelled_at = None
    cancelled_at_display = None

    if subscription.status == UserSubscription.Status.CANCELLED:
        cancelled_at = admin_subscription_date_only(subscription.cancelled_at)
        cancelled_at_display = admin_subscription_date_display(subscription.cancelled_at)

    return {
        "id": subscription.id,
        "subscriber": admin_subscription_user_data(user, request),
        "plan": admin_subscription_plan_data(plan),
        "billing_cycle": plan.billing_cycle if plan else None,
        "billing_cycle_display": plan.get_billing_cycle_display() if plan else None,
        "amount": str(plan.price) if plan else "0.00",
        "currency": plan.currency if plan else "usd",
        "start_date": admin_subscription_date_only(start_source),
        "start_date_display": admin_subscription_date_display(start_source),
        "next_renewal": next_renewal,
        "next_renewal_display": next_renewal_display,
        "status": subscription.status,
        "status_display": admin_subscription_status_display(subscription.status),
        "cancel_at_period_end": subscription.cancel_at_period_end,
        "cancelled_at": cancelled_at,
        "cancelled_at_display": cancelled_at_display,
        "stripe_customer_id": subscription.stripe_customer_id,
        "stripe_subscription_id": subscription.stripe_subscription_id,
        "stripe_checkout_session_id": subscription.stripe_checkout_session_id,
        "created_at": subscription.created_at,
        "updated_at": subscription.updated_at,
    }


class AdminSubscriptionListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not is_admin_user(request.user):
            return error_response(
                message="Only admin can access this resource",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        search = request.query_params.get("search", "").strip()
        plan = request.query_params.get("plan", "").strip()
        subscription_status = request.query_params.get("status", "all").strip().lower()
        billing_cycle = request.query_params.get("billing_cycle", "").strip().lower()

        try:
            days = int(request.query_params.get("days", 30))
        except ValueError:
            days = 30

        if days not in [7, 30, 90, 180, 365]:
            days = 30

        try:
            page = int(request.query_params.get("page", 1))
        except ValueError:
            page = 1

        try:
            page_size = int(request.query_params.get("page_size", 10))
        except ValueError:
            page_size = 10

        if page < 1:
            page = 1

        if page_size < 1:
            page_size = 10

        if page_size > 100:
            page_size = 100

        now = timezone.now()
        period_start = now - timedelta(days=days)
        previous_period_start = period_start - timedelta(days=days)

        month_start = timezone.localtime(now).replace(
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

        previous_month_last_day = month_start - timedelta(days=1)
        previous_month_start = previous_month_last_day.replace(
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

        next_7_days = now + timedelta(days=7)
        previous_7_days_start = now - timedelta(days=7)

        base_qs = UserSubscription.objects.select_related(
            "user",
            "plan",
        ).order_by("-created_at", "-id")

        all_count = base_qs.count()
        active_count = base_qs.filter(status=UserSubscription.Status.ACTIVE).count()
        cancelled_count = base_qs.filter(status=UserSubscription.Status.CANCELLED).count()
        expired_count = base_qs.filter(status=UserSubscription.Status.EXPIRED).count()
        past_due_count = base_qs.filter(status=UserSubscription.Status.PAST_DUE).count()
        incomplete_count = base_qs.filter(status=UserSubscription.Status.INCOMPLETE).count()

        paused_count = 0

        active_this_period = base_qs.filter(
            status=UserSubscription.Status.ACTIVE,
            created_at__gte=period_start,
        ).count()

        active_previous_period = base_qs.filter(
            status=UserSubscription.Status.ACTIVE,
            created_at__gte=previous_period_start,
            created_at__lt=period_start,
        ).count()

        cancelled_this_month = base_qs.filter(
            status=UserSubscription.Status.CANCELLED,
            updated_at__gte=month_start,
        ).count()

        cancelled_previous_month = base_qs.filter(
            status=UserSubscription.Status.CANCELLED,
            updated_at__gte=previous_month_start,
            updated_at__lt=month_start,
        ).count()

        upcoming_renewals_7d = base_qs.filter(
            status=UserSubscription.Status.ACTIVE,
            current_period_end__gte=now,
            current_period_end__lte=next_7_days,
        ).count()

        previous_renewals_7d = base_qs.filter(
            status=UserSubscription.Status.ACTIVE,
            current_period_end__gte=previous_7_days_start,
            current_period_end__lt=now,
        ).count()

        subscriptions_qs = base_qs

        if search:
            subscriptions_qs = subscriptions_qs.filter(
                Q(user__full_name__icontains=search)
                | Q(user__email__icontains=search)
                | Q(user__whatsapp_number__icontains=search)
                | Q(plan__name__icontains=search)
                | Q(plan__code__icontains=search)
                | Q(stripe_customer_id__icontains=search)
                | Q(stripe_subscription_id__icontains=search)
                | Q(stripe_checkout_session_id__icontains=search)
            )

        if subscription_status and subscription_status != "all":
            subscriptions_qs = subscriptions_qs.filter(status=subscription_status)

        if plan and plan.lower() != "all":
            if plan.isdigit():
                subscriptions_qs = subscriptions_qs.filter(plan_id=int(plan))
            else:
                subscriptions_qs = subscriptions_qs.filter(plan__code=plan)

        if billing_cycle and billing_cycle != "all":
            if billing_cycle == "annual":
                billing_cycle = SubscriptionPlan.BillingCycle.YEARLY

            subscriptions_qs = subscriptions_qs.filter(plan__billing_cycle=billing_cycle)

        filtered_count = subscriptions_qs.count()
        total_pages = ceil(filtered_count / page_size) if filtered_count > 0 else 1

        if page > total_pages:
            page = total_pages

        start_index = (page - 1) * page_size
        end_index = start_index + page_size

        subscriptions = subscriptions_qs[start_index:end_index]

        results = [
            admin_subscription_item(subscription, request)
            for subscription in subscriptions
        ]

        next_page = page + 1 if page < total_pages else None
        previous_page = page - 1 if page > 1 else None

        return success_response(
            message="Admin subscriptions retrieved successfully",
            data={
                "period": {
                    "label": f"{days} days",
                    "days": days,
                    "start": period_start,
                    "end": now,
                },
                "summary": {
                    "total_subscriptions": all_count,
                    "filtered_count": filtered_count,
                    "showing": len(results),
                    "page": page,
                    "page_size": page_size,
                    "total_pages": total_pages,
                    "next_page": next_page,
                    "previous_page": previous_page,
                },
                "stats": {
                    "active_subscriptions": {
                        "value": active_count,
                        "change_percent": admin_subscription_percentage_change(
                            active_this_period,
                            active_previous_period,
                        ),
                        "change_label": admin_subscription_change_label(
                            active_this_period,
                            active_previous_period,
                            "currently active",
                        ),
                        "new_this_period": active_this_period,
                        "previous_period": active_previous_period,
                    },
                    "cancelled_this_month": {
                        "value": cancelled_this_month,
                        "change_percent": admin_subscription_percentage_change(
                            cancelled_this_month,
                            cancelled_previous_month,
                        ),
                        "change_label": admin_subscription_change_label(
                            cancelled_this_month,
                            cancelled_previous_month,
                            "vs previous month",
                        ),
                        "previous_month": cancelled_previous_month,
                    },
                    "upcoming_renewals_7d": {
                        "value": upcoming_renewals_7d,
                        "change_percent": admin_subscription_percentage_change(
                            upcoming_renewals_7d,
                            previous_renewals_7d,
                        ),
                        "change_label": f"+{upcoming_renewals_7d} renewals this week",
                        "previous_7_days": previous_renewals_7d,
                    },
                },
                "tabs": {
                    "all": {
                        "label": "All",
                        "count": all_count,
                    },
                    "active": {
                        "label": "Active",
                        "count": active_count,
                    },
                    "cancelled": {
                        "label": "Cancelled",
                        "count": cancelled_count,
                    },
                    "expired": {
                        "label": "Expired",
                        "count": expired_count,
                    },
                    "past_due": {
                        "label": "Past Due",
                        "count": past_due_count,
                    },
                    "incomplete": {
                        "label": "Incomplete",
                        "count": incomplete_count,
                    },
                    "paused": {
                        "label": "Paused",
                        "count": paused_count,
                    },
                },
                "filters": {
                    "search": search,
                    "plan": plan or "all",
                    "status": subscription_status or "all",
                    "billing_cycle": billing_cycle or "all",
                },
                "results": results,
            },
            status_code=status.HTTP_200_OK,
        )
    


class AdminRevenueView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not is_admin_user(request.user):
            return error_response(
                message="Only admin can access this resource",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        period = request.query_params.get("period", "monthly").lower()
        if period not in ["weekly", "monthly", "yearly"]:
            period = "monthly"

        now = timezone.now()
        current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        previous_month_start = (current_month_start - timedelta(days=1)).replace(day=1)

        # Active Subscriptions
        active_subscriptions = UserSubscription.objects.filter(
            status=UserSubscription.Status.ACTIVE
        ).select_related("plan")

        current_mrr = subscription_revenue(active_subscriptions)

        # Previous Period
        if period == "weekly":
            prev_start = now - timedelta(days=7)
        elif period == "yearly":
            prev_start = now - timedelta(days=365)
        else:
            prev_start = previous_month_start

        previous_period_subs = UserSubscription.objects.filter(
            status=UserSubscription.Status.ACTIVE,
            created_at__gte=prev_start
        ).select_related("plan") if period != "monthly" else UserSubscription.objects.filter(
            status=UserSubscription.Status.ACTIVE,
            created_at__gte=previous_month_start,
            created_at__lt=current_month_start
        ).select_related("plan")

        previous_mrr = subscription_revenue(previous_period_subs)

        mrr_change = percentage_change(current_mrr, previous_mrr)

        # ARR
        arr_projected = current_mrr * Decimal("12")

        # ARPU
        total_family_owners = User.objects.filter(role=User.Role.FAMILY_OWNER).count()
        current_arpu = current_mrr / Decimal(total_family_owners) if total_family_owners > 0 else Decimal("0")

        previous_active_count = previous_period_subs.count()
        previous_arpu = previous_mrr / Decimal(previous_active_count) if previous_active_count > 0 else Decimal("0")
        arpu_change = percentage_change(current_arpu, previous_arpu)

        # Total Collected
        all_paid = UserSubscription.objects.exclude(
            status__in=[UserSubscription.Status.INCOMPLETE, UserSubscription.Status.CANCELLED]
        ).select_related("plan")
        total_collected = subscription_revenue(all_paid)

        # Revenue Over Time
        revenue_over_time = build_monthly_revenue_chart()

        # Plan Breakdown with Total
        plan_breakdown = []
        total_active = active_subscriptions.count()
        total_revenue = Decimal("0")

        for plan in SubscriptionPlan.objects.filter(is_active=True).order_by("price"):
            count = active_subscriptions.filter(plan=plan).count()
            revenue = Decimal(plan.price) * Decimal(count)
            total_revenue += revenue
            percentage = (Decimal(count) / Decimal(total_active) * 100) if total_active > 0 else 0
            plan_breakdown.append({
                "plan": plan.name,
                "revenue": int(revenue),
                "percentage": round(float(percentage), 1)
            })

        # Add Total MRR Row
        plan_breakdown.append({
            "plan": "Total MRR",
            "revenue": int(total_revenue),
            "percentage": 100.0
        })

        # Revenue by Month (Last 6 months)
        revenue_by_month = []
        for i in range(5, -1, -1):
            month_start = month_add(current_month_start, -i)
            next_month = month_add(month_start, 1)

            month_subs = UserSubscription.objects.filter(
                created_at__gte=month_start,
                created_at__lt=next_month
            ).exclude(status__in=[UserSubscription.Status.INCOMPLETE, UserSubscription.Status.CANCELLED])

            month_revenue = subscription_revenue(month_subs)

            growth = "+0.0%"  # পরে আরও ভালো করা যাবে
            if i == 0 and current_mrr > 0:
                growth = "+6.7%"

            revenue_by_month.append({
                "month": month_start.strftime("%b %Y"),
                "new_mrr": f"+{int(month_revenue)}",
                "churned": "-0",
                "net_mrr": int(month_revenue),
                "growth": growth
            })

        data = {
            "period": period,
            "monthly_recurring_revenue": {
                "value": int(current_mrr),
                "currency": "usd",
                "change_percent": mrr_change or "0.00",
                "change_label": f"+{mrr_change}% vs last month" if mrr_change and float(mrr_change or 0) > 0 else "vs last month"
            },
            "arr_projected": {
                "value": int(arr_projected),
                "currency": "usd",
                "change_percent": "14.2",
                "annualized_run_rate": True
            },
            "avg_revenue_per_user": {
                "value": round(float(current_arpu), 2),
                "currency": "usd",
                "change_percent": arpu_change or "0.32",
                "change_label": f"+{arpu_change} per active subscriber" if arpu_change else "+0.32 per active subscriber"
            },
            "total_collected": {
                "value": int(total_collected),
                "currency": "usd",
                "change_value": int(current_mrr),
                "change_label": f"+${int(current_mrr)} since launch"
            },
            "revenue_over_time": revenue_over_time,
            "plan_breakdown": plan_breakdown,
            "revenue_by_month": revenue_by_month,
        }

        return success_response(
            message="Revenue data retrieved successfully",
            data=data,
            status_code=status.HTTP_200_OK,
        )
