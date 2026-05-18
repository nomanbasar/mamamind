from django.db import models


class ContactMessage(models.Model):
    class EnquiryType(models.TextChoices):
        GENERAL = "general", "General"
        BILLING = "billing", "Billing"
        FEATURES = "features", "Features"
        PRIVACY = "privacy", "Privacy"
        GETTING_STARTED = "getting_started", "Getting Started"
        SUPPORT = "support", "Support"

    class Status(models.TextChoices):
        NEW = "new", "New"
        IN_PROGRESS = "in_progress", "In Progress"
        RESOLVED = "resolved", "Resolved"

    enquiry_type = models.CharField(
        max_length=50,
        choices=EnquiryType.choices,
        default=EnquiryType.GENERAL,
    )
    name = models.CharField(max_length=255)
    email = models.EmailField()
    subject = models.CharField(max_length=255)
    message = models.TextField()

    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.NEW,
    )

    admin_note = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return f"{self.name} - {self.subject}"