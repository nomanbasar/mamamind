from django.core.mail import send_mail
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from .models import User, OTP, Family, FamilyMembership
from subscriptions.models import UserSubscription
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.db.models import Q
from reminders.models import Reminder

from .serializers import (
    RegisterSerializer,
    VerifyEmailOTPSerializer,
    ResendOTPSerializer,
    LoginSerializer,
    ForgotPasswordSerializer,
    VerifyForgotPasswordOTPSerializer,
    ResetPasswordSerializer,
    ChangePasswordSerializer,
    InviteFamilyMemberSerializer,
    AcceptInviteSerializer,
    UserProfileSerializer,
    CheckWhatsAppSerializer
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


def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)

    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    }


def user_data(user):
    membership = user.family_memberships.select_related("family").first()

    data = {
        "id": user.id,
        "full_name": user.full_name,
        "email": user.email if not user.email.endswith("@mamamind.local") else None,
        "whatsapp_number": user.whatsapp_number,
        "role": user.role,
        "is_email_verified": user.is_email_verified,
    }

    if membership:
        data["family"] = {
            "id": membership.family.id,
            "name": membership.family.name,
            "relation": membership.relation,
            "member_status": membership.status,
        }

    return data


def get_owner_family_membership(user):
    return user.family_memberships.filter(
        relation=FamilyMembership.Relation.OWNER,
        status=FamilyMembership.Status.ACTIVE,
    ).select_related("family").first()


def get_user_family_membership(user):
    return user.family_memberships.filter(
        status=FamilyMembership.Status.ACTIVE,
    ).select_related("family").first()


def check_whatsapp_status(whatsapp_number, request=None):
    """Return user info + tokens if user is ready to login"""
    user = User.objects.filter(whatsapp_number=whatsapp_number).first()

    if not user:
        return {
            "exists": False,
            "in_family": False,
            "message": "This WhatsApp number is available."
        }

    membership = user.family_memberships.select_related("family").first()

    base_data = {
        "exists": True,
        "in_family": bool(membership),
        "family_name": membership.family.name if membership else None,
        "role": user.role,
        "status": membership.status if membership else "no_membership",
        "status_display": membership.get_status_display() if membership else None,
    }

    
    can_login = (
        user.has_usable_password() and 
        user.is_active and 
        user.is_email_verified
    )

    if can_login:
        tokens = get_tokens_for_user(user)
        base_data.update({
            "requires_login": False,
            "can_auto_login": True,
            "tokens": tokens,                   
            "message": f"User found in {membership.family.name if membership else 'system'}."
        })
    else:
        base_data.update({
            "requires_login": True,
            "can_auto_login": False,
            "tokens": None,
            "message": "User exists but needs to complete setup or login manually."
        })

    return base_data


def get_active_user_subscription(user):
    return UserSubscription.objects.filter(
        user=user,
        status=UserSubscription.Status.ACTIVE,
    ).select_related("plan").order_by("-id").first()


def get_family_usage(family, plan=None):
    active_count = family.memberships.filter(
        status=FamilyMembership.Status.ACTIVE,
    ).count()

    pending_count = family.memberships.filter(
        status=FamilyMembership.Status.PENDING,
    ).count()

    used = active_count + pending_count
    limit = plan.member_limit if plan else 1

    return {
        "used": used,
        "limit": limit,
        "active_count": active_count,
        "pending_count": pending_count,
        "remaining": max(limit - used, 0),
        "is_limit_reached": used >= limit,
    }


def public_email(user):
    if user.email and user.email.endswith("@mamamind.local"):
        return None
    return user.email


def get_accept_invite_api_url(request):
    return request.build_absolute_uri("/api/auth/family/accept-invite/")

def family_member_item(membership):
    user = membership.user

    return {
        "membership_id": membership.id,
        "user_id": user.id,
        "full_name": user.full_name,
        "email": public_email(user),
        "whatsapp_number": user.whatsapp_number,
        "role": user.role,
        "relation": membership.relation,
        "relation_display": membership.get_relation_display(),
        "status": membership.status,
        "status_display": membership.get_status_display(),
        "joined_at": membership.accepted_at,
        "invited_at": membership.created_at,
        "invite_expires_at": membership.invite_expires_at,
        "can_edit": membership.relation != FamilyMembership.Relation.OWNER,
        "can_remove": membership.relation != FamilyMembership.Relation.OWNER,
    }


def get_family_payload(family, subscription=None):
    plan = subscription.plan if subscription else None
    usage = get_family_usage(family, plan)

    active_memberships = family.memberships.filter(
        status=FamilyMembership.Status.ACTIVE,
    ).select_related("user").order_by("id")

    pending_memberships = family.memberships.filter(
        status=FamilyMembership.Status.PENDING,
    ).select_related("user").order_by("-id")

    return {
        "plan": {
            "id": plan.id if plan else None,
            "name": plan.name if plan else "No Active Plan",
            "code": plan.code if plan else None,
            "member_limit": plan.member_limit if plan else 1,
        },
        "usage": usage,
        "active_members": [
            family_member_item(membership)
            for membership in active_memberships
        ],
        "pending_invites": [
            {
                **family_member_item(membership),
                "invite_token": membership.invite_token,
                "accept_invite_api": "/api/auth/family/accept-invite/",
                "whatsapp_message": (
                    f"You have been invited to join {family.name} on Mamamind. "
                    f"Your invite token is: {membership.invite_token}"
                ),
            }
            for membership in pending_memberships
        ],
    }



class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)

        if not serializer.is_valid():
            return error_response("Validation error", serializer.errors)

        user = serializer.save()

        return success_response(
            message="Registration successful. OTP sent to email.",
            data={
                "user_id": user.id,
                "email": user.email,
                "role": user.role,
                "is_email_verified": user.is_email_verified,
            },
            status_code=status.HTTP_201_CREATED,
        )


class VerifyEmailOTPView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VerifyEmailOTPSerializer(data=request.data)

        if not serializer.is_valid():
            return error_response("Validation error", serializer.errors)

        email = serializer.validated_data["email"].lower()
        otp_code = serializer.validated_data["otp_code"]

        user = User.objects.filter(email=email).first()

        if not user:
            return error_response("User not found", status_code=status.HTTP_404_NOT_FOUND)

        if user.is_email_verified:
            return error_response("Email already verified")

        otp = OTP.objects.filter(
            user=user,
            purpose=OTP.Purpose.EMAIL_VERIFY,
            is_used=False,
        ).order_by("-created_at").first()

        if not otp:
            return error_response("OTP not found. Please request a new OTP.")

        if otp.is_expired():
            return error_response("OTP expired. Please request a new OTP.")

        if otp.attempts >= otp.max_attempts:
            return error_response("Maximum OTP attempts exceeded. Please request a new OTP.")

        if otp.otp_code != otp_code:
            otp.attempts += 1
            otp.save(update_fields=["attempts"])
            return error_response("Invalid OTP")

        otp.is_verified = True
        otp.is_used = True
        otp.save(update_fields=["is_verified", "is_used"])

        user.is_email_verified = True
        user.save(update_fields=["is_email_verified"])

        return success_response(
            message="Email verified successfully",
            data={
                "user": user_data(user),
                "tokens": get_tokens_for_user(user),
            },
        )


class ResendEmailOTPView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ResendOTPSerializer(data=request.data)

        if not serializer.is_valid():
            return error_response("Validation error", serializer.errors)

        email = serializer.validated_data["email"].lower()
        user = User.objects.filter(email=email).first()

        if not user:
            return error_response("User not found", status_code=status.HTTP_404_NOT_FOUND)

        if user.is_email_verified:
            return error_response("Email already verified")

        otp = OTP.create_otp(user=user, purpose=OTP.Purpose.EMAIL_VERIFY)

        send_mail(
            subject="Mamamind Email Verification OTP",
            message=f"Your Mamamind verification OTP is: {otp.otp_code}",
            from_email=None,
            recipient_list=[user.email],
            fail_silently=False,
        )

        return success_response(
            message="OTP resent successfully",
            data={
                "email": user.email,
                "purpose": OTP.Purpose.EMAIL_VERIFY,
            },
        )


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)

        if not serializer.is_valid():
            non_field_errors = serializer.errors.get("non_field_errors")

            if non_field_errors:
                return error_response(str(non_field_errors[0]))

            return error_response("Validation error", serializer.errors)

        user = serializer.validated_data["user"]

        return success_response(
            message="Login successful",
            data={
                "user": user_data(user),
                "tokens": get_tokens_for_user(user),
            },
        )


class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)

        if not serializer.is_valid():
            return error_response("Validation error", serializer.errors)

        email = serializer.validated_data["email"].lower()
        user = User.objects.filter(email=email).first()

        if not user:
            return error_response("User not found", status_code=status.HTTP_404_NOT_FOUND)

        otp = OTP.create_otp(user=user, purpose=OTP.Purpose.PASSWORD_RESET)

        send_mail(
            subject="Mamamind Password Reset OTP",
            message=f"Your Mamamind password reset OTP is: {otp.otp_code}",
            from_email=None,
            recipient_list=[user.email],
            fail_silently=False,
        )

        return success_response(
            message="Password reset OTP sent successfully",
            data={"email": user.email},
        )


class ResendForgotPasswordOTPView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ResendOTPSerializer(data=request.data)

        if not serializer.is_valid():
            return error_response("Validation error", serializer.errors)

        email = serializer.validated_data["email"].lower()
        user = User.objects.filter(email=email).first()

        if not user:
            return error_response("User not found", status_code=status.HTTP_404_NOT_FOUND)

        otp = OTP.create_otp(user=user, purpose=OTP.Purpose.PASSWORD_RESET)

        send_mail(
            subject="Mamamind Password Reset OTP",
            message=f"Your Mamamind password reset OTP is: {otp.otp_code}",
            from_email=None,
            recipient_list=[user.email],
            fail_silently=False,
        )

        return success_response(
            message="Forgot password OTP resent successfully",
            data={
                "email": user.email,
                "purpose": OTP.Purpose.PASSWORD_RESET,
            },
        )


class VerifyForgotPasswordOTPView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VerifyForgotPasswordOTPSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "message": "Validation error",
                    "data": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        email = serializer.validated_data["email"]
        otp_code = serializer.validated_data["otp_code"]

        user = User.objects.filter(email=email).first()

        if not user:
            return Response(
                {
                    "success": False,
                    "message": "User not found",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        otp = OTP.objects.filter(
            user=user,
            email=email,
            purpose=OTP.Purpose.PASSWORD_RESET,
            is_used=False,
        ).order_by("-created_at").first()

        if not otp:
            return Response(
                {
                    "success": False,
                    "message": "OTP not found",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if otp.is_verified:
            return Response(
                {
                    "success": False,
                    "message": "OTP already verified",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if otp.is_expired():
            return Response(
                {
                    "success": False,
                    "message": "OTP expired",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if otp.attempts >= otp.max_attempts:
            return Response(
                {
                    "success": False,
                    "message": "OTP attempt limit exceeded",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        otp.attempts += 1

        if otp.otp_code != otp_code:
            otp.save(update_fields=["attempts"])
            return Response(
                {
                    "success": False,
                    "message": "Invalid OTP",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        otp.is_verified = True
        otp.save(update_fields=["attempts", "is_verified"])

        refresh = RefreshToken.for_user(user)

        if user.is_superuser or user.role == User.Role.ADMIN:
            role = "admin"
        elif user.role == User.Role.FAMILY_OWNER:
            role = "family_owner"
        elif user.role == User.Role.FAMILY_MEMBER:
            role = "family_member"
        else:
            role = "user"

        return Response(
            {
                "success": True,
                "message": "OTP verified",
                "data": {
                    "tokens": {
                        "access": str(refresh.access_token),
                        "refresh": str(refresh),
                    },
                    "user": {
                        "email": user.email,
                        "full_name": user.full_name,
                        "role": role,
                    },
                },
            },
            status=status.HTTP_200_OK,
        )


class ResetPasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)

        if not serializer.is_valid():
            return error_response(
                message="Validation error",
                data=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        user = request.user

        otp = OTP.objects.filter(
            user=user,
            purpose=OTP.Purpose.PASSWORD_RESET,
            is_verified=True,
            is_used=False,
        ).order_by("-created_at").first()

        if not otp:
            return error_response(
                message="OTP verification required before resetting password",
                data={},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        if otp.is_expired():
            return error_response(
                message="Reset session expired",
                data={},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])

        otp.is_used = True
        otp.save(update_fields=["is_used"])

        refresh = RefreshToken.for_user(user)

        if user.is_superuser or user.role == User.Role.ADMIN:
            account_type = "admin"
        elif user.role == User.Role.FAMILY_OWNER:
            account_type = "family_owner"
        elif user.role == User.Role.FAMILY_MEMBER:
            account_type = "family_member"
        else:
            account_type = "user"

        return error_response(
            message="",
            data={},
        ) if False else Response(
            {
                "success": True,
                "message": "Password reset successfully",
                "data": {
                    "user": {
                        "id": user.id,
                        "email": user.email,
                        "full_name": user.full_name,
                        "profile_image": None,
                        "account_type": account_type,
                    },
                    "tokens": {
                        "access": str(refresh.access_token),
                        "refresh": str(refresh),
                    },
                },
            },
            status=status.HTTP_200_OK,
        )


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data,
            context={"request": request},
        )

        if not serializer.is_valid():
            return error_response("Validation error", serializer.errors)

        user = request.user
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])

        return success_response(
            message="Password changed successfully",
            data={
                "user": user_data(user),
                "tokens": get_tokens_for_user(user),
            },
        )


class UserProfileView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        serializer = UserProfileSerializer(
            request.user,
            context={"request": request},
        )

        return success_response(
            message="Profile retrieved successfully",
            data={
                "user": serializer.data,
            },
            status_code=status.HTTP_200_OK,
        )

    def patch(self, request):
        serializer = UserProfileSerializer(
            request.user,
            data=request.data,
            partial=True,
            context={"request": request},
        )

        if not serializer.is_valid():
            return error_response(
                message="Validation error",
                data=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        serializer.save()

        return success_response(
            message="Profile updated successfully",
            data={
                "user": serializer.data,
            },
            status_code=status.HTTP_200_OK,
        )
    

    

class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get("refresh")

        if not refresh_token:
            return error_response("Refresh token is required")

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except Exception:
            return error_response("Invalid refresh token")

        return success_response(
            message="Logout successful",
            data={},
        )



class CheckWhatsAppView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = CheckWhatsAppSerializer(data=request.data)

        if not serializer.is_valid():
            return error_response(
                message="Validation error",
                data=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST
            )

        whatsapp_number = serializer.validated_data["whatsapp_number"]

        status_data = check_whatsapp_status(whatsapp_number, request)

        return success_response(
            message="WhatsApp number checked successfully",
            data=status_data,
            status_code=status.HTTP_200_OK
        )


class InviteFamilyMemberView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.role != User.Role.FAMILY_OWNER:
            return error_response(
                message="Only family owner can invite members",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        owner_membership = get_owner_family_membership(request.user)

        if not owner_membership:
            return error_response(
                message="Family owner profile not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        subscription = get_active_user_subscription(request.user)

        if not subscription:
            return error_response(
                message="Active subscription required to invite family members",
                data={"subscription": None},
                status_code=status.HTTP_403_FORBIDDEN,
            )

        usage = get_family_usage(owner_membership.family, subscription.plan)

        if usage["is_limit_reached"]:
            return error_response(
                message="Your current plan member limit has been reached. Please upgrade your plan.",
                data={
                    "usage": usage,
                    "plan": {
                        "id": subscription.plan.id,
                        "name": subscription.plan.name,
                        "code": subscription.plan.code,
                        "member_limit": subscription.plan.member_limit,
                    },
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        serializer = InviteFamilyMemberSerializer(
            data=request.data,
            context={"request": request},
        )

        if not serializer.is_valid():
            return error_response(
                message="Validation error",
                data=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        membership = serializer.save()

        updated_usage = get_family_usage(owner_membership.family, subscription.plan)

        return success_response(
            message="Family member invited successfully",
            data={
                "invite": {
                    "membership_id": membership.id,
                    "user_id": membership.user.id,
                    "full_name": membership.user.full_name,
                    "email": public_email(membership.user),
                    "whatsapp_number": membership.user.whatsapp_number,
                    "role": membership.user.role,
                    "relation": membership.relation,
                    "relation_display": membership.get_relation_display(),
                    "status": membership.status,
                    "status_display": membership.get_status_display(),
                    "invite_token": membership.invite_token,
                    "invite_expires_at": membership.invite_expires_at,
                    "accept_invite_api": get_accept_invite_api_url(request),
                    "whatsapp_message": (
                        f"You have been invited to join {owner_membership.family.name} on Mamamind. "
                        f"Your invite token is: {membership.invite_token}"
                    ),
                },
                "usage": updated_usage,
            },
            status_code=status.HTTP_201_CREATED,
        )


class AcceptInviteView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = AcceptInviteSerializer(data=request.data)

        if not serializer.is_valid():
            return error_response(
                message="Validation error",
                data=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        membership = serializer.validated_data["membership"]
        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]

        user = membership.user

        user.email = email
        user.set_password(password)
        user.is_email_verified = True
        user.is_active = True
        user.save(update_fields=[
            "email",
            "password",
            "is_email_verified",
            "is_active",
        ])

        membership.status = FamilyMembership.Status.ACTIVE
        membership.accepted_at = timezone.now()
        membership.invite_token = None
        membership.invite_expires_at = None
        membership.save(update_fields=[
            "status",
            "accepted_at",
            "invite_token",
            "invite_expires_at",
        ])

        return success_response(
            message="Invite accepted successfully. Account activated.",
            data={
                "user": user_data(user),
                "tokens": get_tokens_for_user(user),
            },
            status_code=status.HTTP_200_OK,
        )  


class FamilyMemberListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        membership = get_user_family_membership(request.user)

        if not membership:
            return error_response(
                message="Family not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        family = membership.family
        owner = family.owner
        subscription = get_active_user_subscription(owner)

        return success_response(
            message="Family members retrieved successfully",
            data=get_family_payload(family, subscription),
        )


class FamilyMemberUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, membership_id):
        if request.user.role != User.Role.FAMILY_OWNER:
            return error_response(
                message="Only family owner can update members",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        owner_membership = get_owner_family_membership(request.user)

        if not owner_membership:
            return error_response(
                message="Family owner profile not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        membership = FamilyMembership.objects.filter(
            id=membership_id,
            family=owner_membership.family,
            status=FamilyMembership.Status.ACTIVE,
        ).select_related("user").first()

        if not membership:
            return error_response(
                message="Active family member not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        if membership.relation == FamilyMembership.Relation.OWNER:
            return error_response(
                message="Owner profile cannot be edited from family members section",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        full_name = request.data.get("full_name")
        whatsapp_number = request.data.get("whatsapp_number")
        relation = request.data.get("relation")

        allowed_relations = [
            FamilyMembership.Relation.PARTNER,
            FamilyMembership.Relation.CHILD,
            FamilyMembership.Relation.PARENT,
            FamilyMembership.Relation.CAREGIVER,
            FamilyMembership.Relation.OTHER,
        ]

        if relation and relation not in allowed_relations:
            return error_response(
                message="Validation error",
                data={"relation": ["Invalid relation"]},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        if whatsapp_number:
            exists = User.objects.filter(
                whatsapp_number=whatsapp_number,
            ).exclude(id=membership.user.id).exists()

            if exists:
                return error_response(
                    message="Validation error",
                    data={"whatsapp_number": ["WhatsApp number already exists"]},
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

        user_update_fields = []

        if full_name:
            membership.user.full_name = full_name
            user_update_fields.append("full_name")

        if whatsapp_number:
            membership.user.whatsapp_number = whatsapp_number
            user_update_fields.append("whatsapp_number")

        if user_update_fields:
            membership.user.save(update_fields=user_update_fields)

        if relation:
            membership.relation = relation
            membership.save(update_fields=["relation"])

        return success_response(
            message="Family member updated successfully",
            data={
                "member": family_member_item(membership),
            },
        )


class RemoveFamilyMemberView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, membership_id):
        if request.user.role != User.Role.FAMILY_OWNER:
            return error_response(
                message="Only family owner can remove members",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        owner_membership = get_owner_family_membership(request.user)

        if not owner_membership:
            return error_response(
                message="Family owner profile not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        membership = FamilyMembership.objects.filter(
            id=membership_id,
            family=owner_membership.family,
            status=FamilyMembership.Status.ACTIVE,
        ).select_related("user").first()

        if not membership:
            return error_response(
                message="Active family member not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        if membership.relation == FamilyMembership.Relation.OWNER:
            return error_response(
                message="Family owner cannot be removed",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        removed_member = {
            "membership_id": membership.id,
            "user_id": membership.user.id,
            "full_name": membership.user.full_name,
            "whatsapp_number": membership.user.whatsapp_number,
            "status": "removed",
        }

        member_user = membership.user

        membership.delete()

        member_user.is_active = False
        member_user.save(update_fields=["is_active"])

        subscription = get_active_user_subscription(request.user)
        usage = get_family_usage(
            owner_membership.family,
            subscription.plan if subscription else None,
        )

        return success_response(
            message="Family member removed successfully",
            data={
                "removed_member": removed_member,
                "usage": usage,
            },
        )


class ResendFamilyInviteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, membership_id):
        if request.user.role != User.Role.FAMILY_OWNER:
            return error_response(
                message="Only family owner can resend invites",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        owner_membership = get_owner_family_membership(request.user)

        if not owner_membership:
            return error_response(
                message="Family owner profile not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        membership = FamilyMembership.objects.filter(
            id=membership_id,
            family=owner_membership.family,
            status=FamilyMembership.Status.PENDING,
        ).select_related("user").first()

        if not membership:
            return error_response(
                message="Pending invite not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        membership.generate_invite_token()

        return success_response(
            message="Invite resent successfully",
            data={
                "invite": {
                    "membership_id": membership.id,
                    "full_name": membership.user.full_name,
                    "email": public_email(membership.user),
                    "whatsapp_number": membership.user.whatsapp_number,
                    "relation": membership.relation,
                    "relation_display": membership.get_relation_display(),
                    "status": membership.status,
                    "status_display": membership.get_status_display(),
                    "invite_token": membership.invite_token,
                    "invite_expires_at": membership.invite_expires_at,
                    "accept_invite_api": get_accept_invite_api_url(request),
                    "whatsapp_message": (
                        f"You have been invited to join {owner_membership.family.name} on Mamamind. "
                        f"Your invite token is: {membership.invite_token}"
                    ),
                }
            },
        )


class CancelFamilyInviteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, membership_id):
        if request.user.role != User.Role.FAMILY_OWNER:
            return error_response(
                message="Only family owner can cancel invites",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        owner_membership = get_owner_family_membership(request.user)

        if not owner_membership:
            return error_response(
                message="Family owner profile not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        membership = FamilyMembership.objects.filter(
            id=membership_id,
            family=owner_membership.family,
            status=FamilyMembership.Status.PENDING,
        ).select_related("user").first()

        if not membership:
            return error_response(
                message="Pending invite not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        cancelled_invite = {
            "membership_id": membership.id,
            "user_id": membership.user.id,
            "full_name": membership.user.full_name,
            "whatsapp_number": membership.user.whatsapp_number,
            "status": "removed",
        }

        invited_user = membership.user

        membership.delete()

        invited_user.is_active = False
        invited_user.save(update_fields=["is_active"])

        subscription = get_active_user_subscription(request.user)
        usage = get_family_usage(
            owner_membership.family,
            subscription.plan if subscription else None,
        )

        return success_response(
            message="Invite cancelled successfully",
            data={
                "cancelled_invite": cancelled_invite,
                "usage": usage,
            },
        )
    


def dashboard_member_initials(full_name):
    if not full_name:
        return ""

    parts = full_name.strip().split()

    if len(parts) == 1:
        return parts[0][:2].upper()

    return f"{parts[0][0]}{parts[-1][0]}".upper()


def dashboard_member_item(membership, request=None):
    user = membership.user

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
        "membership_id": membership.id,
        "user_id": user.id,
        "full_name": user.full_name,
        "email": public_email(user),
        "whatsapp_number": user.whatsapp_number,
        "role": user.role,
        "relation": membership.relation,
        "relation_display": membership.get_relation_display(),
        "status": membership.status,
        "status_display": membership.get_status_display(),
        "initials": dashboard_member_initials(user.full_name),
        "profile_image": profile_image,
        "profile_image_url": profile_image_url,
        "joined_at": membership.accepted_at,
        "invited_at": membership.created_at,
    }


def dashboard_reminder_item(reminder):
    if not reminder:
        return None

    return {
        "id": reminder.id,
        "title": reminder.title,
        "owner_id": reminder.owner.id if reminder.owner else None,
        "owner_name": reminder.owner.full_name if reminder.owner else "Family",
        "date": reminder.reminder_date,
        "time": reminder.reminder_time,
        "visibility": reminder.visibility,
        "visibility_display": reminder.get_visibility_display(),
        "recurring": reminder.recurring,
        "recurring_display": reminder.get_recurring_display(),
        "is_completed": reminder.is_completed,
        "is_overdue": reminder.is_overdue,
    }


def dashboard_visible_reminders(user, family):
    reminders = Reminder.objects.filter(
        family=family,
    ).select_related(
        "owner",
        "created_by",
        "family",
    )

    if family.owner_id == user.id:
        return reminders

    return reminders.filter(
        Q(visibility=Reminder.Visibility.SHARED)
        | Q(owner=user)
        | Q(created_by=user)
    )


class DashboardOverviewView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        membership = get_user_family_membership(request.user)

        if not membership:
            return error_response(
                message="Family not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        family = membership.family
        owner = family.owner

        subscription = get_active_user_subscription(owner)

        if not subscription:
            return error_response(
                message="Active subscription required to view dashboard",
                data={
                    "active_plan": None,
                },
                status_code=status.HTTP_403_FORBIDDEN,
            )

        active_memberships = family.memberships.filter(
            status=FamilyMembership.Status.ACTIVE,
        ).select_related("user").order_by("id")

        pending_memberships = family.memberships.filter(
            status=FamilyMembership.Status.PENDING,
        ).select_related("user").order_by("-id")

        usage = get_family_usage(family, subscription.plan)

        visible_reminders = dashboard_visible_reminders(request.user, family)

        now = timezone.localtime()
        today = now.date()

        upcoming_reminders_qs = visible_reminders.filter(
            is_completed=False,
        ).filter(
            Q(reminder_date__gt=today)
            | Q(reminder_date=today, reminder_time__gte=now.time())
        ).order_by("reminder_date", "reminder_time")

        next_reminder = upcoming_reminders_qs.first()

        active_plan = {
            "id": subscription.id,
            "name": subscription.plan.name,
            "code": subscription.plan.code,
            "price": str(subscription.plan.price),
            "currency": subscription.plan.currency,
            "billing_cycle": subscription.plan.billing_cycle,
            "member_limit": subscription.plan.member_limit,
            "status": subscription.status,
            "status_display": subscription.get_status_display(),
            "renews_at": subscription.current_period_end.date() if subscription.current_period_end else None,
            "current_period_start": subscription.current_period_start,
            "current_period_end": subscription.current_period_end,
        }

        family_members = {
            "connected": active_memberships.count(),
            "pending_invites": pending_memberships.count(),
            "member_limit": subscription.plan.member_limit,
            "used": usage["used"],
            "remaining": usage["remaining"],
            "is_limit_reached": usage["is_limit_reached"],
        }

        upcoming_reminders = [
            dashboard_reminder_item(reminder)
            for reminder in upcoming_reminders_qs[:4]
        ]

        members = [
            dashboard_member_item(item, request)
            for item in active_memberships
        ]

        pending_invites = [
            dashboard_member_item(item, request)
            for item in pending_memberships
        ]

        return success_response(
            message="Dashboard overview retrieved successfully",
            data={
                "active_plan": active_plan,
                "family_members": family_members,
                "next_reminder": dashboard_reminder_item(next_reminder),
                "upcoming_reminders": upcoming_reminders,
                "members": members,
                "pending_invites": pending_invites,
            },
            status_code=status.HTTP_200_OK,
        )

