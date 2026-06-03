from django.conf import settings
from django.db import models
from django.utils import timezone

from authentication.models import Family


class Reminder(models.Model):
    class Visibility(models.TextChoices):
        SHARED = "shared", "Shared"
        PRIVATE = "private", "Private"

    class Recurring(models.TextChoices):
        ONE_TIME = "one_time", "One time"
        DAILY = "daily", "Daily"
        WEEKLY = "weekly", "Weekly"
        MONTHLY = "monthly", "Monthly"
        YEARLY = "yearly", "Yearly"

    family = models.ForeignKey(
        Family,
        on_delete=models.CASCADE,
        related_name="reminders",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_reminders",
    )

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="owned_reminders",
        null=True,
        blank=True,
        help_text="Null means Family reminder",
    )

    title = models.CharField(max_length=255)
    reminder_date = models.DateField()
    reminder_time = models.TimeField()

    visibility = models.CharField(
        max_length=20,
        choices=Visibility.choices,
        default=Visibility.SHARED,
    )

    recurring = models.CharField(
        max_length=20,
        choices=Recurring.choices,
        default=Recurring.ONE_TIME,
    )

    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["is_completed", "reminder_date", "reminder_time"]

    def __str__(self):
        return self.title

    @property
    def is_overdue(self):
        if self.is_completed:
            return False

        reminder_datetime = timezone.datetime.combine(
            self.reminder_date,
            self.reminder_time,
        )

        reminder_datetime = timezone.make_aware(
            reminder_datetime,
            timezone.get_current_timezone(),
        )

        return reminder_datetime < timezone.now()