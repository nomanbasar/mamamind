from django.contrib.auth import authenticate
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
import secrets
from .models import User, Family, FamilyMembership, OTP


class RegisterSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=255)
    email = serializers.EmailField()
    whatsapp_number = serializers.CharField(max_length=30)
    password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True, min_length=8)

    def validate_email(self, value):
        value = value.lower()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Email already exists")
        return value

    def validate_whatsapp_number(self, value):
        if User.objects.filter(whatsapp_number=value).exists():
            raise serializers.ValidationError("WhatsApp number already exists")
        return value

    def validate(self, attrs):
        if attrs["password"] != attrs["confirm_password"]:
            raise serializers.ValidationError({
                "confirm_password": ["Passwords do not match"]
            })
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        password = validated_data.pop("password")
        validated_data.pop("confirm_password")

        user = User.objects.create_user(
            email=validated_data["email"],
            password=password,
            full_name=validated_data["full_name"],
            whatsapp_number=validated_data["whatsapp_number"],
            role=User.Role.FAMILY_OWNER,
            is_email_verified=False,
        )

        family = Family.objects.create(
            name=f"{user.full_name}'s Family",
            owner=user,
        )

        FamilyMembership.objects.create(
            family=family,
            user=user,
            relation=FamilyMembership.Relation.OWNER,
            status=FamilyMembership.Status.ACTIVE,
            accepted_at=timezone.now(),
        )

        otp = OTP.create_otp(user=user, purpose=OTP.Purpose.EMAIL_VERIFY)

        send_mail(
            subject="Mamamind Email Verification OTP",
            message=f"Your Mamamind verification OTP is: {otp.otp_code}",
            from_email=None,
            recipient_list=[user.email],
            fail_silently=False,
        )

        return user


class VerifyEmailOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp_code = serializers.CharField(max_length=6)


class ResendOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = attrs["email"].lower()
        password = attrs["password"]

        user_obj = User.objects.filter(email=email).first()

        if user_obj and user_obj.role == User.Role.FAMILY_MEMBER:
            pending_membership = user_obj.family_memberships.filter(
                status=FamilyMembership.Status.PENDING
            ).first()

            if pending_membership and not user_obj.has_usable_password():
                raise serializers.ValidationError(
                    "Please accept your family invite and set your password first."
                )

        user = authenticate(email=email, password=password)

        if not user:
            raise serializers.ValidationError("Invalid credentials")

        if not user.is_active:
            raise serializers.ValidationError("Account is inactive")

        if not user.is_email_verified:
            raise serializers.ValidationError("Email is not verified. Please verify OTP first.")

        attrs["user"] = user
        return attrs


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()


class VerifyForgotPasswordOTPSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False)
    email_address = serializers.EmailField(required=False)
    otp_code = serializers.CharField(max_length=6)

    def validate(self, attrs):
        email = attrs.get("email") or attrs.get("email_address")

        if not email:
            raise serializers.ValidationError({
                "email": ["This field is required."]
            })

        attrs["email"] = email.lower()
        return attrs


class ResetPasswordSerializer(serializers.Serializer):
    new_password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True, min_length=8)

    def validate(self, attrs):
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError({
                "confirm_password": ["Passwords do not match"]
            })
        return attrs


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True, min_length=8)

    def validate(self, attrs):
        user = self.context["request"].user

        if not user.check_password(attrs["current_password"]):
            raise serializers.ValidationError({
                "current_password": ["Current password is incorrect"]
            })

        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError({
                "confirm_password": ["Passwords do not match"]
            })

        if attrs["current_password"] == attrs["new_password"]:
            raise serializers.ValidationError({
                "new_password": ["New password cannot be same as current password"]
            })

        return attrs


class InviteFamilyMemberSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=255)
    whatsapp_number = serializers.CharField(max_length=30)
    relation = serializers.ChoiceField(choices=[
        FamilyMembership.Relation.PARTNER,
        FamilyMembership.Relation.CHILD,
        FamilyMembership.Relation.PARENT,
        FamilyMembership.Relation.CAREGIVER,
        FamilyMembership.Relation.OTHER,
    ])

    def validate_whatsapp_number(self, value):
        if User.objects.filter(whatsapp_number=value).exists():
            raise serializers.ValidationError("WhatsApp number already exists")
        return value

    @transaction.atomic
    def create(self, validated_data):
        owner = self.context["request"].user

        owner_membership = owner.family_memberships.filter(
            relation=FamilyMembership.Relation.OWNER,
            status=FamilyMembership.Status.ACTIVE,
        ).select_related("family").first()

        if not owner_membership:
            raise serializers.ValidationError("Family owner profile not found")

        clean_number = (
            validated_data["whatsapp_number"]
            .replace("+", "")
            .replace(" ", "")
            .replace("-", "")
        )

        random_part = secrets.token_urlsafe(8).replace("-", "").replace("_", "").lower()

        temporary_email = f"{clean_number}.{random_part}@mamamind.local"

        member_user = User.objects.create_user(
            email=temporary_email,
            password=None,
            full_name=validated_data["full_name"],
            whatsapp_number=validated_data["whatsapp_number"],
            role=User.Role.FAMILY_MEMBER,
            is_email_verified=False,
        )

        member_user.set_unusable_password()
        member_user.save(update_fields=["password"])

        membership = FamilyMembership.objects.create(
            family=owner_membership.family,
            user=member_user,
            relation=validated_data["relation"],
            status=FamilyMembership.Status.PENDING,
        )

        membership.generate_invite_token()

        return membership



class AcceptInviteSerializer(serializers.Serializer):
    invite_token = serializers.CharField()
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True, min_length=8)

    def validate(self, attrs):
        invite_token = attrs.get("invite_token")
        email = attrs.get("email").lower()
        password = attrs.get("password")
        confirm_password = attrs.get("confirm_password")

        if password != confirm_password:
            raise serializers.ValidationError({
                "confirm_password": ["Passwords do not match"]
            })

        membership = FamilyMembership.objects.filter(
            invite_token=invite_token,
            status=FamilyMembership.Status.PENDING,
        ).select_related("user", "family").first()

        if not membership:
            raise serializers.ValidationError({
                "invite_token": ["Invalid invite token"]
            })

        if membership.is_invite_expired():
            raise serializers.ValidationError({
                "invite_token": ["Invite token expired"]
            })

        if User.objects.filter(email=email).exclude(id=membership.user.id).exists():
            raise serializers.ValidationError({
                "email": ["Email already exists"]
            })

        attrs["email"] = email
        attrs["membership"] = membership
        return attrs
    


class UserProfileSerializer(serializers.ModelSerializer):
    profile_image = serializers.ImageField(required=False, allow_null=True)
    profile_image_url = serializers.SerializerMethodField()
    family = serializers.SerializerMethodField()
    subscription = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "full_name",
            "email",
            "whatsapp_number",
            "role",
            "is_email_verified",
            "profile_image",
            "profile_image_url",
            "family",
            "subscription",
        ]
        read_only_fields = [
            "id",
            "email",
            "role",
            "is_email_verified",
            "profile_image_url",
            "family",
            "subscription",
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)

        if instance.profile_image:
            data["profile_image"] = instance.profile_image.url
        else:
            data["profile_image"] = None

        return data

    def get_profile_image_url(self, obj):
        request = self.context.get("request")

        if obj.profile_image:
            if request:
                return request.build_absolute_uri(obj.profile_image.url)
            return obj.profile_image.url

        return None

    def get_family(self, obj):
        membership = obj.family_memberships.filter(
            status=FamilyMembership.Status.ACTIVE
        ).select_related("family").first()

        if not membership:
            return None

        return {
            "id": membership.family.id,
            "name": membership.family.name,
            "relation": membership.relation,
            "relation_display": membership.get_relation_display(),
            "member_status": membership.status,
            "member_status_display": membership.get_status_display(),
        }

    def get_subscription(self, obj):
        try:
            from subscriptions.models import UserSubscription
        except Exception:
            return None

        membership = obj.family_memberships.filter(
            status=FamilyMembership.Status.ACTIVE
        ).select_related("family", "family__owner").first()

        if not membership:
            return None

        subscription = UserSubscription.objects.filter(
            user=membership.family.owner,
            status=UserSubscription.Status.ACTIVE,
        ).select_related("plan").order_by("-id").first()

        if not subscription:
            return None

        return {
            "id": subscription.id,
            "status": subscription.status,
            "plan": {
                "id": subscription.plan.id,
                "name": subscription.plan.name,
                "code": subscription.plan.code,
                "price": str(subscription.plan.price),
                "currency": subscription.plan.currency,
                "billing_cycle": subscription.plan.billing_cycle,
                "member_limit": subscription.plan.member_limit,
            }
        }

