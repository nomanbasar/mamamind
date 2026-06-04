from decimal import Decimal
from datetime import datetime, timezone as dt_timezone

import stripe
from django.conf import settings
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from rest_framework import status
from rest_framework.exceptions import NotAuthenticated, PermissionDenied
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import SubscriptionPlan, UserSubscription
from .permissions import IsAdminUserRole
from .serializers import (
    SubscriptionPlanSerializer,
    PublicSubscriptionPlanSerializer,
    UserSubscriptionSerializer,
    CheckoutSerializer,
    CancelSubscriptionSerializer,
    UserSubscriptionInvoiceSerializer
)


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


class CustomPermissionResponseMixin:
    def permission_denied(self, request, message=None, code=None):
        if not request.user or not request.user.is_authenticated:
            raise NotAuthenticated(
                detail={
                    "success": False,
                    "message": "Authentication credentials were not provided.",
                    "data": {},
                }
            )

        raise PermissionDenied(
            detail={
                "success": False,
                "message": "You do not have permission to perform this action.",
                "data": {},
            }
        )


def get_active_subscription(user):
    return UserSubscription.objects.filter(
        user=user,
        status=UserSubscription.Status.ACTIVE,
    ).select_related("plan").order_by("-id").first()


def unix_to_datetime(value):
    if not value:
        return None

    return datetime.fromtimestamp(value, tz=dt_timezone.utc)

def stripe_value(obj, key, default=None):
    """
    Stripe object and normal dict both support korar jonno safe getter.
    StripeObject e .get() kaj nao korte pare, tai obj[key] try kora hocche.
    """
    try:
        if isinstance(obj, dict):
            return obj.get(key, default)

        return obj[key]
    except Exception:
        return default


def get_subscription_period_from_stripe_subscription(stripe_subscription):
    # Old Stripe API support
    current_period_start = stripe_value(stripe_subscription, "current_period_start")
    current_period_end = stripe_value(stripe_subscription, "current_period_end")

    if current_period_start and current_period_end:
        return current_period_start, current_period_end

    # New Stripe API support: items.data[0].current_period_start/end
    items = stripe_value(stripe_subscription, "items", {})
    item_data = stripe_value(items, "data", [])

    if item_data and len(item_data) > 0:
        first_item = item_data[0]

        current_period_start = stripe_value(first_item, "current_period_start")
        current_period_end = stripe_value(first_item, "current_period_end")

        if current_period_start and current_period_end:
            return current_period_start, current_period_end

    return None, None


def activate_user_subscription_from_stripe_session(session):
    from django.contrib.auth import get_user_model

    metadata = stripe_value(session, "metadata", {})

    user_id = stripe_value(metadata, "user_id")
    plan_id = stripe_value(metadata, "plan_id")

    if not user_id or not plan_id:
        raise ValueError("Stripe session metadata missing user_id or plan_id")

    User = get_user_model()
    user = User.objects.get(id=user_id)
    plan = SubscriptionPlan.objects.get(id=plan_id)

    stripe_customer_id = stripe_value(session, "customer")
    stripe_subscription_id = stripe_value(session, "subscription")
    stripe_checkout_session_id = stripe_value(session, "id")

    current_period_start = None
    current_period_end = None

    if stripe_subscription_id and settings.STRIPE_SECRET_KEY:
        stripe.api_key = settings.STRIPE_SECRET_KEY
        stripe_subscription = stripe.Subscription.retrieve(
            stripe_subscription_id,
            expand=["items.data"],
        )

        period_start, period_end = get_subscription_period_from_stripe_subscription(
            stripe_subscription
        )

        current_period_start = unix_to_datetime(period_start)
        current_period_end = unix_to_datetime(period_end)

    UserSubscription.objects.filter(
        user=user,
        status=UserSubscription.Status.ACTIVE,
    ).update(
        status=UserSubscription.Status.CANCELLED,
        cancelled_at=timezone.now(),
    )

    subscription, created = UserSubscription.objects.update_or_create(
        stripe_checkout_session_id=stripe_checkout_session_id,
        defaults={
            "user": user,
            "plan": plan,
            "status": UserSubscription.Status.ACTIVE,
            "stripe_customer_id": stripe_customer_id,
            "stripe_subscription_id": stripe_subscription_id,
            "current_period_start": current_period_start,
            "current_period_end": current_period_end,
            "cancel_at_period_end": False,
        },
    )

    return subscription

class AdminSubscriptionPlanListCreateView(CustomPermissionResponseMixin, ListCreateAPIView):
    permission_classes = [IsAdminUserRole]
    serializer_class = SubscriptionPlanSerializer

    def get_queryset(self):
        queryset = SubscriptionPlan.objects.all()

        is_active = self.request.query_params.get("is_active")
        search = self.request.query_params.get("search")

        if is_active in ["true", "false"]:
            queryset = queryset.filter(is_active=is_active == "true")

        if search:
            queryset = queryset.filter(name__icontains=search) | queryset.filter(code__icontains=search)

        return queryset.order_by("price", "id")

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)

        return success_response(
            message="Subscription plans retrieved successfully",
            data={
                "count": queryset.count(),
                "plans": serializer.data,
            },
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)

        if not serializer.is_valid():
            return error_response(
                message="Validation error",
                data=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        plan = serializer.save()

        return success_response(
            message="Subscription plan created successfully",
            data={
                "plan": SubscriptionPlanSerializer(plan).data,
            },
            status_code=status.HTTP_201_CREATED,
        )


class AdminSubscriptionPlanDetailView(CustomPermissionResponseMixin, RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminUserRole]
    serializer_class = SubscriptionPlanSerializer
    queryset = SubscriptionPlan.objects.all()
    lookup_field = "id"

    def retrieve(self, request, *args, **kwargs):
        plan = self.get_object()

        return success_response(
            message="Subscription plan retrieved successfully",
            data={
                "plan": SubscriptionPlanSerializer(plan).data,
            },
        )

    def update(self, request, *args, **kwargs):
        plan = self.get_object()
        partial = kwargs.pop("partial", False)

        serializer = self.get_serializer(
            plan,
            data=request.data,
            partial=partial,
        )

        if not serializer.is_valid():
            return error_response(
                message="Validation error",
                data=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        plan = serializer.save()

        return success_response(
            message="Subscription plan updated successfully",
            data={
                "plan": SubscriptionPlanSerializer(plan).data,
            },
        )

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        plan = self.get_object()
        plan.is_active = False
        plan.save(update_fields=["is_active"])

        return success_response(
            message="Subscription plan deactivated successfully",
            data={
                "plan": SubscriptionPlanSerializer(plan).data,
            },
        )


class PublicSubscriptionPlanListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        plans = SubscriptionPlan.objects.filter(is_active=True).order_by("price", "id")

        current_subscription = None
        if request.user and request.user.is_authenticated:
            current_subscription = get_active_subscription(request.user)

        serializer = PublicSubscriptionPlanSerializer(
            plans,
            many=True,
            context={
                "current_subscription": current_subscription,
            },
        )

        return success_response(
            message="Subscription plans retrieved successfully",
            data={
                "count": plans.count(),
                "plans": serializer.data,
            },
        )


class CurrentSubscriptionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        subscription = get_active_subscription(request.user)

        if not subscription:
            return success_response(
                message="No active subscription found",
                data={
                    "subscription": None,
                },
            )

        return success_response(
            message="Current subscription retrieved successfully",
            data={
                "subscription": UserSubscriptionSerializer(subscription).data,
            },
        )


class SubscriptionHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        subscriptions = UserSubscription.objects.filter(
            user=request.user,
        ).select_related("plan").order_by("-id")

        return success_response(
            message="Subscription history retrieved successfully",
            data={
                "count": subscriptions.count(),
                "subscriptions": UserSubscriptionSerializer(subscriptions, many=True).data,
            },
        )


class StripeCheckoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CheckoutSerializer(
            data=request.data,
            context={},
        )

        if not serializer.is_valid():
            return error_response(
                message="Validation error",
                data=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        plan = serializer.context["plan"]

        if not settings.STRIPE_SECRET_KEY:
            return error_response(
                message="Stripe secret key is not configured",
                data={},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        stripe.api_key = settings.STRIPE_SECRET_KEY

        try:
            unit_amount = int(plan.price * Decimal("100"))

            checkout_session = stripe.checkout.Session.create(
                mode="subscription",
                customer_email=request.user.email,
                line_items=[
                    {
                        "price_data": {
                            "currency": plan.currency.lower(),
                            "unit_amount": unit_amount,
                            "recurring": {
                                "interval": "month" if plan.billing_cycle == "monthly" else "year",
                            },
                            "product_data": {
                                "name": plan.name,
                                "description": plan.description or "",
                            },
                        },
                        "quantity": 1,
                    }
                ],
                success_url=settings.STRIPE_SUCCESS_URL + "?session_id={CHECKOUT_SESSION_ID}",
                cancel_url=settings.STRIPE_CANCEL_URL,
                metadata={
                    "user_id": str(request.user.id),
                    "plan_id": str(plan.id),
                },
                subscription_data={
                    "metadata": {
                        "user_id": str(request.user.id),
                        "plan_id": str(plan.id),
                    }
                },
            )

            return success_response(
                message="Stripe checkout session created successfully",
                data={
                    "checkout_url": checkout_session.url,
                    "session_id": checkout_session.id,
                    "plan": PublicSubscriptionPlanSerializer(plan).data,
                },
                status_code=status.HTTP_201_CREATED,
            )

        except Exception as error:
            return error_response(
                message="Stripe checkout session creation failed",
                data={
                    "error": str(error),
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )


@method_decorator(csrf_exempt, name="dispatch")
class StripeWebhookView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        payload = request.body
        sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")
        endpoint_secret = settings.STRIPE_WEBHOOK_SECRET

        try:
            if endpoint_secret:
                stripe.api_key = settings.STRIPE_SECRET_KEY

                event = stripe.Webhook.construct_event(
                    payload=payload,
                    sig_header=sig_header,
                    secret=endpoint_secret,
                )
            else:
                event = request.data

        except Exception as error:
            return error_response(
                message="Invalid Stripe webhook payload",
                data={
                    "error": str(error),
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        event_type = stripe_value(event, "type")
        event_data = stripe_value(event, "data", {})
        event_object = stripe_value(event_data, "object", {})

        if event_type == "checkout.session.completed":
            try:
                subscription = activate_user_subscription_from_stripe_session(event_object)

                return success_response(
                    message="Subscription activated successfully",
                    data={
                        "subscription": UserSubscriptionSerializer(subscription).data,
                    },
                )

            except Exception as error:
                return error_response(
                    message="Subscription activation failed",
                    data={
                        "error": str(error),
                    },
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

        if event_type == "customer.subscription.deleted":
            try:
                stripe_subscription_id = stripe_value(event_object, "id")

                if stripe_subscription_id:
                    UserSubscription.objects.filter(
                        stripe_subscription_id=stripe_subscription_id,
                    ).update(
                        status=UserSubscription.Status.CANCELLED,
                        cancelled_at=timezone.now(),
                        cancel_at_period_end=False,
                    )

            except Exception:
                pass

        return success_response(
            message="Stripe webhook received successfully",
            data={
                "event_type": event_type,
            },
        )


class StripePaymentSuccessView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        session_id = request.query_params.get("session_id")

        if not session_id:
            return error_response(
                message="Stripe session id is required",
                data={},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        try:
            stripe.api_key = settings.STRIPE_SECRET_KEY

            session = stripe.checkout.Session.retrieve(session_id)
            subscription = activate_user_subscription_from_stripe_session(session)

            return success_response(
                message="Payment completed successfully. Subscription activated.",
                data={
                    "session_id": session_id,
                    "subscription": UserSubscriptionSerializer(subscription).data,
                    "next_step": "Call GET /api/subscriptions/current/ with user token to verify active subscription.",
                },
            )

        except Exception as error:
            return error_response(
                message="Payment success received but subscription activation failed",
                data={
                    "session_id": session_id,
                    "error": str(error),
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )

class StripePaymentCancelView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return error_response(
            message="Payment was cancelled.",
            data={},
            status_code=status.HTTP_400_BAD_REQUEST,
        )



class CancelSubscriptionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CancelSubscriptionSerializer(data=request.data)

        if not serializer.is_valid():
            return error_response(
                message="Validation error",
                data=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        subscription = get_active_subscription(request.user)

        if not subscription:
            return error_response(
                message="No active subscription found",
                data={},
                status_code=status.HTTP_404_NOT_FOUND,
            )

        if subscription.stripe_subscription_id and settings.STRIPE_SECRET_KEY:
            try:
                stripe.api_key = settings.STRIPE_SECRET_KEY
                stripe.Subscription.modify(
                    subscription.stripe_subscription_id,
                    cancel_at_period_end=True,
                )

                subscription.cancel_at_period_end = True
                subscription.save(update_fields=["cancel_at_period_end"])

                return success_response(
                    message="Subscription cancellation scheduled successfully",
                    data={
                        "subscription": UserSubscriptionSerializer(subscription).data,
                    },
                )

            except Exception as error:
                return error_response(
                    message="Stripe subscription cancellation failed",
                    data={
                        "error": str(error),
                    },
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

        subscription.status = UserSubscription.Status.CANCELLED
        subscription.cancelled_at = timezone.now()
        subscription.save(update_fields=["status", "cancelled_at"])

        return success_response(
            message="Subscription cancelled successfully",
            data={
                "subscription": UserSubscriptionSerializer(subscription).data,
            },
        )
    


class UserSubscriptionInvoiceHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        subscriptions = UserSubscription.objects.filter(
            user=request.user
        ).select_related("plan").order_by("-created_at", "-id")

        serializer = UserSubscriptionInvoiceSerializer(
            subscriptions,
            many=True,
            context={"request": request}
        )

        return success_response(
            message="Invoice history retrieved successfully",
            data={
                "invoices": serializer.data
            },
            status_code=status.HTTP_200_OK,
        )