from rest_framework import status
from rest_framework.exceptions import NotAuthenticated, PermissionDenied
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.response import Response

from .models import FAQ
from .permissions import IsAdminOrReadOnly
from .serializers import FAQSerializer, FAQPublicSerializer


FAQ_CATEGORIES = [
    {
        "key": "all",
        "label": "All",
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


class FAQListCreateView(CustomPermissionResponseMixin, ListCreateAPIView):
    permission_classes = [IsAdminOrReadOnly]

    def get_serializer_class(self):
        if self.request.method == "GET":
            return FAQPublicSerializer

        return FAQSerializer

    def get_queryset(self):
        queryset = FAQ.objects.all()

        if self.request.method == "GET":
            queryset = queryset.filter(is_active=True)

        category = self.request.query_params.get("category", "all")

        if category and category != "all":
            valid_categories = [
                FAQ.Category.BILLING,
                FAQ.Category.FEATURES,
                FAQ.Category.PRIVACY,
                FAQ.Category.GETTING_STARTED,
            ]

            if category not in valid_categories:
                return FAQ.objects.none()

            queryset = queryset.filter(category=category)

        return queryset.order_by("-id")

    def list(self, request, *args, **kwargs):
        category = request.query_params.get("category", "all")
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)

        return success_response(
            message="FAQ list retrieved successfully",
            data={
                "category": category,
                "count": queryset.count(),
                "categories": FAQ_CATEGORIES,
                "faqs": serializer.data,
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

        faq = serializer.save()

        return success_response(
            message="FAQ created successfully",
            data={
                "faq": FAQSerializer(faq).data,
            },
            status_code=status.HTTP_201_CREATED,
        )


class FAQDetailView(CustomPermissionResponseMixin, RetrieveUpdateDestroyAPIView):
    queryset = FAQ.objects.all()
    serializer_class = FAQSerializer
    permission_classes = [IsAdminOrReadOnly]
    lookup_field = "id"

    def retrieve(self, request, *args, **kwargs):
        faq = self.get_object()

        if not faq.is_active:
            return error_response(
                message="FAQ not found",
                data={},
                status_code=status.HTTP_404_NOT_FOUND,
            )

        return success_response(
            message="FAQ retrieved successfully",
            data={
                "faq": FAQPublicSerializer(faq).data,
            },
        )

    def update(self, request, *args, **kwargs):
        faq = self.get_object()
        partial = kwargs.pop("partial", False)

        serializer = self.get_serializer(
            faq,
            data=request.data,
            partial=partial,
        )

        if not serializer.is_valid():
            return error_response(
                message="Validation error",
                data=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        faq = serializer.save()

        return success_response(
            message="FAQ updated successfully",
            data={
                "faq": FAQSerializer(faq).data,
            },
        )

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        faq = self.get_object()
        faq.delete()

        return success_response(
            message="FAQ deleted successfully",
            data={},
        )