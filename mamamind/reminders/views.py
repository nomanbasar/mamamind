from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from authentication.models import FamilyMembership
from subscriptions.models import UserSubscription

from .models import Reminder
from .serializers import ReminderSerializer


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


def get_active_membership(user):
    return user.family_memberships.filter(
        status=FamilyMembership.Status.ACTIVE,
    ).select_related("family", "family__owner").first()


def get_active_subscription_for_family(family):
    return UserSubscription.objects.filter(
        user=family.owner,
        status=UserSubscription.Status.ACTIVE,
    ).select_related("plan").order_by("-id").first()


def is_family_owner(user, family):
    return family.owner_id == user.id


def get_visible_reminders_queryset(user, family):
    base_qs = Reminder.objects.filter(family=family).select_related(
        "owner",
        "created_by",
        "family",
    )

    if is_family_owner(user, family):
        return base_qs

    return base_qs.filter(
        Q(visibility=Reminder.Visibility.SHARED)
        | Q(owner=user)
        | Q(created_by=user)
    )


def can_manage_reminder(user, reminder):
    if is_family_owner(user, reminder.family):
        return True

    if reminder.created_by_id == user.id:
        return True

    if reminder.owner_id == user.id:
        return True

    return False


def apply_filter(qs, filter_type):
    now = timezone.localtime()
    today = now.date()

    if filter_type == "upcoming":
        return qs.filter(
            is_completed=False,
        ).filter(
            Q(reminder_date__gt=today)
            | Q(reminder_date=today, reminder_time__gte=now.time())
        )

    if filter_type == "this_week":
        week_end = today + timedelta(days=7)
        return qs.filter(
            reminder_date__gte=today,
            reminder_date__lte=week_end,
        )

    if filter_type == "shared":
        return qs.filter(visibility=Reminder.Visibility.SHARED)

    if filter_type == "private":
        return qs.filter(visibility=Reminder.Visibility.PRIVATE)

    if filter_type == "completed":
        return qs.filter(is_completed=True)

    return qs


def reminder_stats(qs):
    now = timezone.localtime()
    today = now.date()

    upcoming_count = qs.filter(
        is_completed=False,
    ).filter(
        Q(reminder_date__gt=today)
        | Q(reminder_date=today, reminder_time__gte=now.time())
    ).count()

    return {
        "total": qs.count(),
        "upcoming": upcoming_count,
        "shared": qs.filter(visibility=Reminder.Visibility.SHARED).count(),
        "private": qs.filter(visibility=Reminder.Visibility.PRIVATE).count(),
        "completed": qs.filter(is_completed=True).count(),
    }


class ReminderListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        membership = get_active_membership(request.user)

        if not membership:
            return error_response(
                message="Active family membership not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        family = membership.family
        subscription = get_active_subscription_for_family(family)

        if not subscription:
            return error_response(
                message="Active subscription required to view reminders",
                data={"subscription": None},
                status_code=status.HTTP_403_FORBIDDEN,
            )

        filter_type = request.query_params.get("filter", "all")

        allowed_filters = [
            "all",
            "upcoming",
            "this_week",
            "shared",
            "private",
            "completed",
        ]

        if filter_type not in allowed_filters:
            return error_response(
                message="Invalid filter",
                data={
                    "allowed_filters": allowed_filters,
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        visible_qs = get_visible_reminders_queryset(request.user, family)
        filtered_qs = apply_filter(visible_qs, filter_type)

        serializer = ReminderSerializer(
            filtered_qs,
            many=True,
            context={
                "request": request,
                "family": family,
            },
        )

        return success_response(
            message="Reminders retrieved successfully",
            data={
                "filter": filter_type,
                "stats": reminder_stats(visible_qs),
                "reminders": serializer.data,
            },
        )

    def post(self, request):
        membership = get_active_membership(request.user)

        if not membership:
            return error_response(
                message="Active family membership not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        family = membership.family
        subscription = get_active_subscription_for_family(family)

        if not subscription:
            return error_response(
                message="Active subscription required to create reminders",
                data={"subscription": None},
                status_code=status.HTTP_403_FORBIDDEN,
            )

        serializer = ReminderSerializer(
            data=request.data,
            context={
                "request": request,
                "family": family,
            },
        )

        if not serializer.is_valid():
            return error_response(
                message="Validation error",
                data=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        reminder = serializer.save()

        return success_response(
            message="Reminder created successfully",
            data={
                "reminder": ReminderSerializer(
                    reminder,
                    context={
                        "request": request,
                        "family": family,
                    },
                ).data,
            },
            status_code=status.HTTP_201_CREATED,
        )


class ReminderDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, request, reminder_id):
        membership = get_active_membership(request.user)

        if not membership:
            return None, None, "membership_not_found"

        family = membership.family
        visible_qs = get_visible_reminders_queryset(request.user, family)

        reminder = visible_qs.filter(id=reminder_id).first()

        if not reminder:
            return None, family, "not_found"

        return reminder, family, None

    def patch(self, request, reminder_id):
        reminder, family, error = self.get_object(request, reminder_id)

        if error == "membership_not_found":
            return error_response(
                message="Active family membership not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        if error == "not_found":
            return error_response(
                message="Reminder not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        subscription = get_active_subscription_for_family(family)

        if not subscription:
            return error_response(
                message="Active subscription required to update reminders",
                data={"subscription": None},
                status_code=status.HTTP_403_FORBIDDEN,
            )

        if not can_manage_reminder(request.user, reminder):
            return error_response(
                message="You do not have permission to update this reminder",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        serializer = ReminderSerializer(
            reminder,
            data=request.data,
            partial=True,
            context={
                "request": request,
                "family": family,
            },
        )

        if not serializer.is_valid():
            return error_response(
                message="Validation error",
                data=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        reminder = serializer.save()

        return success_response(
            message="Reminder updated successfully",
            data={
                "reminder": ReminderSerializer(
                    reminder,
                    context={
                        "request": request,
                        "family": family,
                    },
                ).data,
            },
        )

    def delete(self, request, reminder_id):
        reminder, family, error = self.get_object(request, reminder_id)

        if error == "membership_not_found":
            return error_response(
                message="Active family membership not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        if error == "not_found":
            return error_response(
                message="Reminder not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        subscription = get_active_subscription_for_family(family)

        if not subscription:
            return error_response(
                message="Active subscription required to delete reminders",
                data={"subscription": None},
                status_code=status.HTTP_403_FORBIDDEN,
            )

        if not can_manage_reminder(request.user, reminder):
            return error_response(
                message="You do not have permission to delete this reminder",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        deleted_reminder = {
            "id": reminder.id,
            "title": reminder.title,
        }

        reminder.delete()

        return success_response(
            message="Reminder deleted successfully",
            data={
                "deleted_reminder": deleted_reminder,
            },
        )


class ReminderOwnerListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        membership = get_active_membership(request.user)

        if not membership:
            return error_response(
                message="Active family membership not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        family = membership.family
        subscription = get_active_subscription_for_family(family)

        if not subscription:
            return error_response(
                message="Active subscription required to view reminder owners",
                data={"subscription": None},
                status_code=status.HTTP_403_FORBIDDEN,
            )

        active_memberships = family.memberships.filter(
            status=FamilyMembership.Status.ACTIVE,
        ).select_related("user").order_by("id")

        owners = [
            {
                "id": None,
                "full_name": "Family",
                "label": "Family",
                "type": "family",
            }
        ]

        for item in active_memberships:
            user = item.user
            owners.append({
                "id": user.id,
                "full_name": user.full_name,
                "label": "You" if user.id == request.user.id else user.full_name,
                "type": "member",
                "relation": item.relation,
                "relation_display": item.get_relation_display(),
            })

        return success_response(
            message="Reminder owners retrieved successfully",
            data={
                "owners": owners,
            },
        )