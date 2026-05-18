from rest_framework import serializers

from .models import ContactMessage


class ContactMessageCreateSerializer(serializers.ModelSerializer):
    enquiry_type_display = serializers.CharField(
        source="get_enquiry_type_display",
        read_only=True,
    )

    class Meta:
        model = ContactMessage
        fields = [
            "id",
            "enquiry_type",
            "enquiry_type_display",
            "name",
            "email",
            "subject",
            "message",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "enquiry_type_display",
            "created_at",
        ]


class ContactMessageAdminSerializer(serializers.ModelSerializer):
    enquiry_type_display = serializers.CharField(
        source="get_enquiry_type_display",
        read_only=True,
    )
    status_display = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )

    class Meta:
        model = ContactMessage
        fields = [
            "id",
            "enquiry_type",
            "enquiry_type_display",
            "name",
            "email",
            "subject",
            "message",
            "status",
            "status_display",
            "admin_note",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "enquiry_type_display",
            "status_display",
            "created_at",
            "updated_at",
        ]