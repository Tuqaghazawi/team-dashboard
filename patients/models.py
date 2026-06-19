from datetime import date

from django.db import models

from teams.models import Team


class Patient(models.Model):
    """One patient and where they are in the surgical-oncology journey."""

    class Specialty(models.TextChoices):
        GENERAL = "GENERAL", "General surgical oncology"
        BREAST = "BREAST", "Breast"
        THYROID = "THYROID", "Thyroid"
        HPB = "HPB", "HPB"
        UPPER_GI = "UPPER_GI", "Upper GI"
        COLORECTAL = "COLORECTAL", "Colorectal"
        SARCOMA = "SARCOMA", "Sarcoma"

    class Stage(models.TextChoices):
        REGISTERED = "REGISTERED", "Registered (prep clinic)"
        CLINIC = "CLINIC", "Consultant clinic"
        WORKUP = "WORKUP", "Workup in progress"
        MDC = "MDC", "Awaiting / at MDC"
        SURGERY = "SURGERY", "Planned for surgery"
        NACT = "NACT", "On NACT"
        TNT = "TNT", "On TNT (rectal)"
        RESTAGING = "RESTAGING", "Restaging (awaiting results)"
        REFERRED = "REFERRED", "Referred to medical team"
        POSTOP = "POSTOP", "Post-op follow-up"
        SURVEILLANCE = "SURVEILLANCE", "Surveillance"
        WATCH_WAIT = "WATCH_WAIT", "Watch & wait"

    # --- Registration details (entered by the prep-clinic coordinator) ---
    name = models.CharField(max_length=120)
    mrn = models.CharField("MRN", max_length=20, unique=True, help_text="Medical Record Number — must be unique.")
    date_of_birth = models.DateField()
    diagnosis = models.CharField(max_length=200)
    specialty = models.CharField(max_length=20, choices=Specialty.choices)

    # --- The link to a team (one team has many patients) ---
    team = models.ForeignKey(
        Team,
        on_delete=models.PROTECT,
        related_name="patients",
        help_text="The team this patient is assigned to.",
    )

    # --- Where the patient is in the journey ---
    stage = models.CharField(max_length=20, choices=Stage.choices, default=Stage.REGISTERED)

    # --- Follow-up tracking (Watch & wait and restaging) ---
    watch_wait_start = models.DateField(
        "Watch & wait start", null=True, blank=True,
        help_text="Date watch-and-wait began (W&W patients only).",
    )
    next_review_date = models.DateField(
        null=True, blank=True,
        help_text="Expected date of next investigations / results check (restaging or W&W).",
    )

    # --- Bookkeeping ---
    registered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-registered_at"]

    def __str__(self):
        return f"{self.name} (MRN {self.mrn})"

    @property
    def age(self):
        """Age in whole years, calculated from the date of birth."""
        today = date.today()
        return today.year - self.date_of_birth.year - (
            (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
        )

    def journey(self):
        """The patient's progress as an ordered list of timeline phases.

        Each item is {"label": ..., "status": "done" | "current" | "upcoming"}.
        Branch stages (NACT/TNT/Restaging/Referred) collapse into the "Treatment"
        phase, and Surveillance/Watch & wait into "Follow-up".
        """
        phases = [
            ("Registered", [self.Stage.REGISTERED]),
            ("Consultant clinic", [self.Stage.CLINIC]),
            ("Workup", [self.Stage.WORKUP]),
            ("MDC", [self.Stage.MDC]),
            ("Treatment", [self.Stage.NACT, self.Stage.TNT, self.Stage.RESTAGING, self.Stage.REFERRED]),
            ("Surgery", [self.Stage.SURGERY]),
            ("Post-op", [self.Stage.POSTOP]),
            ("Follow-up", [self.Stage.SURVEILLANCE, self.Stage.WATCH_WAIT]),
        ]
        current_index = 0
        for i, (label, stages) in enumerate(phases):
            if self.stage in stages:
                current_index = i
                break

        timeline = []
        for i, (label, stages) in enumerate(phases):
            if i < current_index:
                status = "done"
            elif i == current_index:
                status = "current"
            else:
                status = "upcoming"
            timeline.append({"label": label, "status": status})
        return timeline
