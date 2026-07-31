from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """A person who logs into the dashboard.

    Built on top of Django's standard user (username, password, name, email),
    with one addition: a ``role`` that decides what this person can see and do.
    """

    class Role(models.TextChoices):
        # Stored value (in the database)   # Human-friendly label (shown in the app)
        PREP_COORDINATOR = "PREP_COORDINATOR", "Prep-clinic coordinator"
        CHAIRMAN = "CHAIRMAN", "Chairman"
        TEAM_COORDINATOR = "TEAM_COORDINATOR", "Team nurse coordinator"
        FELLOW = "FELLOW", "Fellow"
        CONSULTANT = "CONSULTANT", "Consultant"
        MDC_COORDINATOR = "MDC_COORDINATOR", "MDC coordinator"

    role = models.CharField(
        max_length=32,
        choices=Role.choices,
        blank=True,
        help_text="Controls what this user can see and do in the dashboard.",
    )

    team = models.ForeignKey(
        "teams.Team",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="members",
        help_text="The team this user belongs to (fellows, team coordinators, consultants).",
    )

    mdc = models.ForeignKey(
        "teams.MDC",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="coordinators",
        help_text="For MDC coordinators: which MDC they run.",
    )

    def __str__(self):
        name = self.get_full_name() or self.username
        return f"{name} ({self.get_role_display() or 'no role'})"

    @property
    def can_see_all_patients(self):
        """Chairman and prep-clinic coordinator (and superusers) see every patient."""
        return self.is_superuser or self.role in {
            self.Role.CHAIRMAN,
            self.Role.PREP_COORDINATOR,
        }

    @property
    def is_team_scoped(self):
        """These roles see only their own team's patients."""
        return self.role in {
            self.Role.CONSULTANT,
            self.Role.FELLOW,
            self.Role.TEAM_COORDINATOR,
        }
