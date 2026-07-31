from datetime import timedelta

from django.db import models
from django.utils import timezone


class MDC(models.Model):
    """A multidisciplinary conference (tumor board) — e.g. Breast, GI, Sarcoma, Thyroid."""

    class Weekday(models.IntegerChoices):
        MONDAY = 0, "Monday"
        TUESDAY = 1, "Tuesday"
        WEDNESDAY = 2, "Wednesday"
        THURSDAY = 3, "Thursday"
        FRIDAY = 4, "Friday"
        SATURDAY = 5, "Saturday"
        SUNDAY = 6, "Sunday"

    name = models.CharField(max_length=50, unique=True)
    meeting_weekday = models.IntegerField(
        choices=Weekday.choices,
        null=True,
        blank=True,
        help_text="The day of the week this MDC meets, used to suggest the next meeting date.",
    )

    class Meta:
        verbose_name = "MDC"
        verbose_name_plural = "MDCs"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def next_meeting_date(self, on_or_after=None):
        """The date of this MDC's next meeting, or None if it has no fixed day."""
        if self.meeting_weekday is None:
            return None
        start = on_or_after or timezone.localdate()
        return start + timedelta(days=(self.meeting_weekday - start.weekday()) % 7)

    def suggested_listing_date(self):
        """The meeting to list a new patient for: next week's, not this week's.

        Coordinators prepare a list a week ahead, so we skip the coming seven
        days entirely. This always lands 7-13 days out, whichever day the
        board meets.
        """
        if self.meeting_weekday is None:
            return None
        return self.next_meeting_date(on_or_after=timezone.localdate() + timedelta(days=7))


class Team(models.Model):
    """A consultant-led surgical team that patients are assigned to."""

    consultant = models.CharField(max_length=100, help_text="The consultant who leads this team.")
    specialty = models.CharField(max_length=100, help_text="e.g. 'Thyroid and breast', 'Colorectal cancer'.")

    class Meta:
        ordering = ["consultant"]

    def __str__(self):
        return f"{self.consultant} — {self.specialty}"
