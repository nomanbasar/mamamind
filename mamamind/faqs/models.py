from django.db import models


class FAQ(models.Model):
    class Category(models.TextChoices):
        BILLING = "billing", "Billing"
        FEATURES = "features", "Features"
        PRIVACY = "privacy", "Privacy"
        GETTING_STARTED = "getting_started", "Getting Started"

    question = models.CharField(max_length=255)
    answer = models.TextField()
    category = models.CharField(
        max_length=50,
        choices=Category.choices,
        default=Category.GETTING_STARTED,
    )
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return self.question