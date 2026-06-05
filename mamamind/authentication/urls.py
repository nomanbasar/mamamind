from django.urls import path

from .views import (
    RegisterView,
    VerifyEmailOTPView,
    ResendEmailOTPView,
    LoginView,
    ForgotPasswordView,
    ResendForgotPasswordOTPView,
    VerifyForgotPasswordOTPView,
    ResetPasswordView,
    ChangePasswordView,
    LogoutView,
    InviteFamilyMemberView,
    AcceptInviteView,
    FamilyMemberListView,
    FamilyMemberUpdateView,
    RemoveFamilyMemberView,
    ResendFamilyInviteView,
    CancelFamilyInviteView,
    UserProfileView,
    CheckWhatsAppView
)

urlpatterns = [
    path("register/", RegisterView.as_view()),
    path("verify-otp/", VerifyEmailOTPView.as_view()),
    path("resend-otp/", ResendEmailOTPView.as_view()),

    path("login/", LoginView.as_view()),
    path("logout/", LogoutView.as_view()),

    path("profile/", UserProfileView.as_view()),

    path("forgot-password/", ForgotPasswordView.as_view()),
    path("resend-forgot-password-otp/", ResendForgotPasswordOTPView.as_view()),
    path("verify-forgot-password-otp/", VerifyForgotPasswordOTPView.as_view()),
    path("reset-password/", ResetPasswordView.as_view()),

    path("change-password/", ChangePasswordView.as_view()),

    path("family/invite-member/", InviteFamilyMemberView.as_view()),
    path("family/accept-invite/", AcceptInviteView.as_view()),

    path("family/members/", FamilyMemberListView.as_view()),
    path("family/members/<int:membership_id>/", FamilyMemberUpdateView.as_view()),
    path("family/members/<int:membership_id>/remove/", RemoveFamilyMemberView.as_view()),

    path("family/invites/<int:membership_id>/resend/", ResendFamilyInviteView.as_view()),
    path("family/invites/<int:membership_id>/cancel/", CancelFamilyInviteView.as_view()),

    path("check-whatsapp/", CheckWhatsAppView.as_view()),
]