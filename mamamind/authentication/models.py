import secrets
from datetime import timedelta

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required")

        email = self.normalize_email(email)
        user = self.model(email=email, username=email, **extra_fields)

        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()

        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("role", User.Role.ADMIN)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_email_verified", True)

        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    class Role(models.TextChoices):
        FAMILY_OWNER = "family_owner", "Family Owner"
        FAMILY_MEMBER = "family_member", "Family Member"
        ADMIN = "admin", "Admin"

    full_name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    whatsapp_number = models.CharField(max_length=30, unique=True, null=True, blank=True)
    role = models.CharField(max_length=30, choices=Role.choices, default=Role.FAMILY_OWNER)
    is_email_verified = models.BooleanField(default=False)
    profile_image = models.ImageField(upload_to="profile_images/",null=True,blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    objects = UserManager()

    def __str__(self):
        return self.email


class Family(models.Model):
    name = models.CharField(max_length=255)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="owned_families")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class FamilyMembership(models.Model):
    class Relation(models.TextChoices):
        OWNER = "owner", "Owner"
        PARTNER = "partner", "Partner"
        CHILD = "child", "Child"
        PARENT = "parent", "Parent"
        CAREGIVER = "caregiver", "Caregiver"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PENDING = "pending", "Pending"
        REMOVED = "removed", "Removed"

    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="family_memberships")
    relation = models.CharField(max_length=30, choices=Relation.choices)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.PENDING)

    invite_token = models.CharField(max_length=255, null=True, blank=True, unique=True)
    invite_expires_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("family", "user")

    def generate_invite_token(self):
        self.invite_token = secrets.token_urlsafe(48)
        self.invite_expires_at = timezone.now() + timedelta(days=7)
        self.save(update_fields=["invite_token", "invite_expires_at"])

    def is_invite_expired(self):
        return self.invite_expires_at and timezone.now() > self.invite_expires_at

    def __str__(self):
        return f"{self.user.email} - {self.family.name}"


class OTP(models.Model):
    class Purpose(models.TextChoices):
        EMAIL_VERIFY = "email_verify", "Email Verify"
        PASSWORD_RESET = "password_reset", "Password Reset"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="otps")
    email = models.EmailField()
    otp_code = models.CharField(max_length=6)
    purpose = models.CharField(max_length=30, choices=Purpose.choices)

    is_verified = models.BooleanField(default=False)
    is_used = models.BooleanField(default=False)

    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=5)

    reset_token = models.CharField(max_length=255, null=True, blank=True, unique=True)
    reset_token_expires_at = models.DateTimeField(null=True, blank=True)

    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    @staticmethod
    def generate_code():
        return str(secrets.randbelow(900000) + 100000)

    @classmethod
    def create_otp(cls, user, purpose):
        return cls.objects.create(
            user=user,
            email=user.email,
            otp_code=cls.generate_code(),
            purpose=purpose,
            expires_at=timezone.now() + timedelta(minutes=10),
        )

    def is_expired(self):
        return timezone.now() > self.expires_at

    def generate_reset_token(self):
        self.reset_token = secrets.token_urlsafe(48)
        self.reset_token_expires_at = timezone.now() + timedelta(minutes=15)
        self.save(update_fields=["reset_token", "reset_token_expires_at"])

    def is_reset_token_expired(self):
        return self.reset_token_expires_at and timezone.now() > self.reset_token_expires_at

    def __str__(self):
        return f"{self.email} - {self.purpose}"