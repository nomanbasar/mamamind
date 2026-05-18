from django.core.mail import send_mail
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User, OTP, FamilyMembership
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
        "email": user.email,
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
            return error_response("Validation error", serializer.errors)

        email = serializer.validated_data["email"].lower()
        otp_code = serializer.validated_data["otp_code"]

        user = User.objects.filter(email=email).first()

        if not user:
            return error_response("User not found", status_code=status.HTTP_404_NOT_FOUND)

        otp = OTP.objects.filter(
            user=user,
            purpose=OTP.Purpose.PASSWORD_RESET,
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
        otp.save(update_fields=["is_verified"])

        otp.generate_reset_token()

        return success_response(
            message="OTP verified successfully",
            data={
                "email": user.email,
                "reset_token": otp.reset_token,
            },
        )


class ResetPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)

        if not serializer.is_valid():
            return error_response("Validation error", serializer.errors)

        reset_token = serializer.validated_data["reset_token"]
        new_password = serializer.validated_data["new_password"]

        otp = OTP.objects.filter(
            purpose=OTP.Purpose.PASSWORD_RESET,
            reset_token=reset_token,
            is_verified=True,
            is_used=False,
        ).select_related("user").first()

        if not otp:
            return error_response("Invalid reset token")

        if otp.is_reset_token_expired():
            return error_response("Reset token expired")

        user = otp.user
        user.set_password(new_password)
        user.save(update_fields=["password"])

        otp.is_used = True
        otp.save(update_fields=["is_used"])

        return success_response(
            message="Password reset successfully",
            data={
                "user": user_data(user),
                "tokens": get_tokens_for_user(user),
            },
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


class InviteFamilyMemberView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.role != User.Role.FAMILY_OWNER:
            return error_response(
                message="Only family owner can invite members",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        serializer = InviteFamilyMemberSerializer(
            data=request.data,
            context={"request": request},
        )

        if not serializer.is_valid():
            return error_response("Validation error", serializer.errors)

        membership = serializer.save()

        return success_response(
            message="Family member invited successfully",
            data={
                "member_id": membership.user.id,
                "full_name": membership.user.full_name,
                "email": membership.user.email,
                "whatsapp_number": membership.user.whatsapp_number,
                "role": membership.user.role,
                "relation": membership.relation,
                "status": membership.status,
                "invite_token": membership.invite_token,
                "invite_link": f"http://127.0.0.1:3000/accept-invite/{membership.invite_token}",
            },
            status_code=status.HTTP_201_CREATED,
        )


class AcceptInviteView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = AcceptInviteSerializer(data=request.data)

        if not serializer.is_valid():
            return error_response("Validation error", serializer.errors)

        invite_token = serializer.validated_data["invite_token"]
        password = serializer.validated_data["password"]

        membership = FamilyMembership.objects.filter(
            invite_token=invite_token,
            status=FamilyMembership.Status.PENDING,
        ).select_related("user", "family").first()

        if not membership:
            return error_response("Invalid invite token")

        if membership.is_invite_expired():
            return error_response("Invite token expired")

        user = membership.user
        user.set_password(password)
        user.is_email_verified = True
        user.save(update_fields=["password", "is_email_verified"])

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
        )