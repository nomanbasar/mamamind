from rest_framework import serializers

from authentication.models import FamilyMembership
from .models import Reminder


class ReminderSerializer(serializers.ModelSerializer):
    owner_id = serializers.IntegerField(required=False, allow_null=True)

    owner_name = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    visibility_display = serializers.CharField(source="get_visibility_display", read_only=True)
    recurring_display = serializers.CharField(source="get_recurring_display", read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)

    class Meta:
        model = Reminder
        fields = [
            "id",
            "title",
            "owner_id",
            "owner_name",
            "created_by_name",
            "reminder_date",
            "reminder_time",
            "visibility",
            "visibility_display",
            "recurring",
            "recurring_display",
            "is_completed",
            "completed_at",
            "is_overdue",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "owner_name",
            "created_by_name",
            "visibility_display",
            "recurring_display",
            "completed_at",
            "is_overdue",
            "created_at",
            "updated_at",
        ]

    def get_owner_name(self, obj):
        if obj.owner:
            return obj.owner.full_name
        return "Family"

    def get_created_by_name(self, obj):
        return obj.created_by.full_name

    def validate(self, attrs):
        request = self.context["request"]
        family = self.context["family"]

        owner_id = attrs.get("owner_id", None)
        visibility = attrs.get("visibility", getattr(self.instance, "visibility", Reminder.Visibility.SHARED))

        if visibility == Reminder.Visibility.PRIVATE and owner_id is None:
            raise serializers.ValidationError({
                "owner_id": ["Private reminder must have an owner."]
            })

        if owner_id is not None:
            is_family_member = family.memberships.filter(
                user_id=owner_id,
                status=FamilyMembership.Status.ACTIVE,
            ).exists()

            if not is_family_member:
                raise serializers.ValidationError({
                    "owner_id": ["Selected owner is not an active member of your family."]
                })

        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        family = self.context["family"]

        owner_id = validated_data.pop("owner_id", None)

        return Reminder.objects.create(
            family=family,
            created_by=request.user,
            owner_id=owner_id,
            **validated_data,
        )

    def update(self, instance, validated_data):
        owner_id = validated_data.pop("owner_id", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if "owner_id" in self.initial_data:
            instance.owner_id = owner_id

        instance.save()
        return instance


class ReminderOwnerSerializer(serializers.Serializer):
    id = serializers.IntegerField(allow_null=True)
    full_name = serializers.CharField()
    label = serializers.CharField()
    type = serializers.CharField()