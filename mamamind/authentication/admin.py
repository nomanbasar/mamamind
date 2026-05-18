from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User, Family, FamilyMembership, OTP


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    model = User
    list_display = (
        "id",
        "email",
        "full_name",
        "whatsapp_number",
        "role",
        "is_email_verified",
        "is_staff",
    )
    list_filter = ("role", "is_email_verified", "is_staff")
    search_fields = ("email", "full_name", "whatsapp_number")
    ordering = ("-id",)

    fieldsets = (
        (None, {"fields": ("email", "username", "password")}),
        ("Personal Info", {"fields": ("full_name", "whatsapp_number")}),
        ("Role & Verification", {"fields": ("role", "is_email_verified")}),
        ("Permissions", {"fields": (
            "is_active",
            "is_staff",
            "is_superuser",
            "groups",
            "user_permissions",
        )}),
        ("Important Dates", {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": (
                "email",
                "full_name",
                "whatsapp_number",
                "role",
                "password1",
                "password2",
            ),
        }),
    )


@admin.register(Family)
class FamilyAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "owner", "created_at")
    search_fields = ("name", "owner__email")


@admin.register(FamilyMembership)
class FamilyMembershipAdmin(admin.ModelAdmin):
    list_display = ("id", "family", "user", "relation", "status", "created_at")
    list_filter = ("relation", "status")
    search_fields = ("family__name", "user__email", "user__full_name")


@admin.register(OTP)
class OTPAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "email",
        "purpose",
        "otp_code",
        "is_verified",
        "is_used",
        "expires_at",
        "created_at",
    )
    list_filter = ("purpose", "is_verified", "is_used")
    search_fields = ("email",)