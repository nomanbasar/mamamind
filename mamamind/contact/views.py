from django.core.mail import send_mail
from django.conf import settings

from rest_framework import status
from rest_framework.exceptions import NotAuthenticated, PermissionDenied
from rest_framework.generics import (
    CreateAPIView,
    ListAPIView,
    RetrieveUpdateDestroyAPIView,
)
from rest_framework.response import Response
from rest_framework.permissions import AllowAny

from .models import ContactMessage
from .permissions import IsAdminOnly
from .serializers import (
    ContactMessageCreateSerializer,
    ContactMessageAdminSerializer,
)


ENQUIRY_TYPES = [
    {
        "key": "general",
        "label": "General",
    },
    {
        "key": "billing",
        "label": "Billing",
    },
    {
        "key": "features",
        "label": "Features",
    },
    {
        "key": "privacy",
        "label": "Privacy",
    },
    {
        "key": "getting_started",
        "label": "Getting Started",
    },
    {
        "key": "support",
        "label": "Support",
    },
]


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


class ContactMessageCreateView(CreateAPIView):
    permission_classes = [AllowAny]
    serializer_class = ContactMessageCreateSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)

        if not serializer.is_valid():
            return error_response(
                message="Validation error",
                data=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        contact_message = serializer.save()

        try:
            send_mail(
                subject=f"New Mamamind Contact Message: {contact_message.subject}",
                message=(
                    f"Enquiry Type: {contact_message.get_enquiry_type_display()}\n"
                    f"Name: {contact_message.name}\n"
                    f"Email: {contact_message.email}\n"
                    f"Subject: {contact_message.subject}\n\n"
                    f"Message:\n{contact_message.message}"
                ),
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                recipient_list=[
                    getattr(settings, "CONTACT_RECEIVER_EMAIL", getattr(settings, "DEFAULT_FROM_EMAIL", ""))
                ],
                fail_silently=True,
            )
        except Exception:
            pass

        return success_response(
            message="Message sent successfully. We'll get back to you within 1 business day.",
            data={
                "contact_message": ContactMessageCreateSerializer(contact_message).data,
            },
            status_code=status.HTTP_201_CREATED,
        )


class ContactMessageListView(CustomPermissionResponseMixin, ListAPIView):
    permission_classes = [IsAdminOnly]
    serializer_class = ContactMessageAdminSerializer

    def get_queryset(self):
        queryset = ContactMessage.objects.all()

        status_filter = self.request.query_params.get("status")
        enquiry_type = self.request.query_params.get("enquiry_type")
        search = self.request.query_params.get("search")

        if status_filter:
            queryset = queryset.filter(status=status_filter)

        if enquiry_type:
            queryset = queryset.filter(enquiry_type=enquiry_type)

        if search:
            queryset = queryset.filter(
                name__icontains=search
            ) | queryset.filter(
                email__icontains=search
            ) | queryset.filter(
                subject__icontains=search
            )

        return queryset.order_by("-id")

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)

        return success_response(
            message="Contact messages retrieved successfully",
            data={
                "count": queryset.count(),
                "enquiry_types": ENQUIRY_TYPES,
                "statuses": [
                    {
                        "key": "new",
                        "label": "New",
                    },
                    {
                        "key": "in_progress",
                        "label": "In Progress",
                    },
                    {
                        "key": "resolved",
                        "label": "Resolved",
                    },
                ],
                "messages": serializer.data,
            },
        )


class ContactMessageDetailView(CustomPermissionResponseMixin, RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminOnly]
    serializer_class = ContactMessageAdminSerializer
    queryset = ContactMessage.objects.all()
    lookup_field = "id"

    def retrieve(self, request, *args, **kwargs):
        contact_message = self.get_object()

        return success_response(
            message="Contact message retrieved successfully",
            data={
                "contact_message": ContactMessageAdminSerializer(contact_message).data,
            },
        )

    def update(self, request, *args, **kwargs):
        contact_message = self.get_object()
        partial = kwargs.pop("partial", False)

        serializer = self.get_serializer(
            contact_message,
            data=request.data,
            partial=partial,
        )

        if not serializer.is_valid():
            return error_response(
                message="Validation error",
                data=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        contact_message = serializer.save()

        return success_response(
            message="Contact message updated successfully",
            data={
                "contact_message": ContactMessageAdminSerializer(contact_message).data,
            },
        )

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        contact_message = self.get_object()
        contact_message.delete()

        return success_response(
            message="Contact message deleted successfully",
            data={},
        )