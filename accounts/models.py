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

    def __str__(self):
        name = self.get_full_name() or self.username
        return f"{name} ({self.get_role_display() or 'no role'})"
