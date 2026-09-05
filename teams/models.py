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


class FellowAssignment(models.Model):
    """A fellow attached to a team for one rotation.

    Rotations run in three-month blocks (Jan-Mar, Apr-Jun, Jul-Sep, Oct-Dec).
    The team's nurse coordinator sets these at the start of each block; an
    assignment is what lets a fellow see that team's dashboard.
    """

    fellow = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="rotations"
    )
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="rotations")
    start_date = models.DateField()
    end_date = models.DateField()
    assigned_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="rotations_assigned",
    )

    class Meta:
        ordering = ["-start_date", "fellow__username"]
        constraints = [
            models.UniqueConstraint(
                fields=["fellow", "team", "start_date"],
                name="unique_fellow_team_rotation",
            )
        ]

    def __str__(self):
        return f"{self.fellow} — {self.team.consultant} ({self.start_date} to {self.end_date})"

    @property
    def is_current(self):
        today = timezone.localdate()
        return self.start_date <= today <= self.end_date

    @staticmethod
    def current_quarter(on=None):
        """(start, end) of the three-month rotation block containing ``on``."""
        today = on or timezone.localdate()
        first_month = 1 + 3 * ((today.month - 1) // 3)
        start = today.replace(month=first_month, day=1)
        last_month = first_month + 2
        if last_month == 12:
            end = today.replace(month=12, day=31)
        else:
            end = today.replace(month=last_month + 1, day=1) - timedelta(days=1)
        return start, end

    @classmethod
    def teams_for(cls, user, on=None):
        """Team ids this fellow is currently rotating through."""
        today = on or timezone.localdate()
        return list(
            cls.objects.filter(
                fellow=user, start_date__lte=today, end_date__gte=today
            ).values_list("team_id", flat=True)
        )
