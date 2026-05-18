from django.contrib.auth import authenticate
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

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
    email = serializers.EmailField()
    whatsapp_number = serializers.CharField(max_length=30)
    relation = serializers.ChoiceField(choices=[
        FamilyMembership.Relation.PARTNER,
        FamilyMembership.Relation.CHILD,
        FamilyMembership.Relation.PARENT,
        FamilyMembership.Relation.CAREGIVER,
        FamilyMembership.Relation.OTHER,
    ])

    def validate_email(self, value):
        value = value.lower()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Email already exists")
        return value

    def validate_whatsapp_number(self, value):
        if User.objects.filter(whatsapp_number=value).exists():
            raise serializers.ValidationError("WhatsApp number already exists")
        return value

    @transaction.atomic
    def create(self, validated_data):
        owner = self.context["request"].user

        membership = owner.family_memberships.filter(
            relation=FamilyMembership.Relation.OWNER,
            status=FamilyMembership.Status.ACTIVE,
        ).select_related("family").first()

        if not membership:
            raise serializers.ValidationError("Family owner profile not found")

        member_user = User.objects.create_user(
            email=validated_data["email"],
            password=None,
            full_name=validated_data["full_name"],
            whatsapp_number=validated_data["whatsapp_number"],
            role=User.Role.FAMILY_MEMBER,
            is_email_verified=True,
        )

        member_membership = FamilyMembership.objects.create(
            family=membership.family,
            user=member_user,
            relation=validated_data["relation"],
            status=FamilyMembership.Status.PENDING,
        )

        member_membership.generate_invite_token()

        invite_link = f"http://127.0.0.1:3000/accept-invite/{member_membership.invite_token}"

        send_mail(
            subject="Mamamind Family Invitation",
            message=(
                f"You have been invited to join {membership.family.name} on Mamamind.\n\n"
                f"Accept invite: {invite_link}"
            ),
            from_email=None,
            recipient_list=[member_user.email],
            fail_silently=False,
        )

        return member_membership


class AcceptInviteSerializer(serializers.Serializer):
    invite_token = serializers.CharField()
    password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True, min_length=8)

    def validate(self, attrs):
        if attrs["password"] != attrs["confirm_password"]:
            raise serializers.ValidationError({
                "confirm_password": ["Passwords do not match"]
            })
        return attrs