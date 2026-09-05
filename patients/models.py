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

    # Stages that only apply to certain specialties (all others apply everywhere)
    SPECIALTY_RESTRICTED_STAGES = {
        Stage.TNT: {Specialty.COLORECTAL},
        Stage.WATCH_WAIT: {Specialty.COLORECTAL},
    }

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

    # --- Clinical summary (filled by the fellow; these feed the MDC slides) ---
    sex = models.CharField(max_length=6, choices=[("F", "Female"), ("M", "Male")], blank=True)
    comorbidities = models.TextField(
        blank=True,
        help_text="Background line for the slide, e.g. 'HTN, DM, non-smoker, PS 0-1'.",
    )
    family_history = models.TextField(blank=True)
    genetic_testing = models.CharField(
        max_length=120, blank=True,
        help_text="e.g. 'Pending', 'Negative', 'BRCA1 positive'. Shown at the top of every slide.",
    )
    clinical_stage = models.CharField(
        max_length=60, blank=True, help_text="Clinical stage, e.g. 'cT4N+', 'T3N2'.",
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

    # ------------------------------------------------------------------
    # Workup progress — the checklist the whole team watches
    # ------------------------------------------------------------------
    def workup_progress(self):
        """(ready_count, total_count) across this patient's required investigations."""
        required = [i for i in self.investigations.all() if i.required]
        ready = [i for i in required if i.status == Investigation.Status.READY]
        return len(ready), len(required)

    @property
    def workup_ready(self):
        """True when every required investigation has a result back.

        This is what decides whether a patient can be presented at MDC.
        A patient with no checklist yet is not ready.
        """
        ready, total = self.workup_progress()
        return total > 0 and ready == total

    @property
    def outstanding_investigations(self):
        return [
            i for i in self.investigations.all()
            if i.required and i.status != Investigation.Status.READY
        ]

    @property
    def active_treatment(self):
        """The running NACT / TNT course, if any."""
        return next((c for c in self.treatment_courses.all() if c.active), None)

    @property
    def needs_postop_mdc(self):
        """Post-op patients must go back to MDC for their post-op plan."""
        if self.stage != self.Stage.POSTOP:
            return False
        return not self.mdc_listings.filter(is_postop=True).exists()

    @classmethod
    def stages_for_specialties(cls, specialties):
        """Stage choices relevant to a set of specialties.

        Restricted stages (e.g. TNT, Watch & wait — rectal only) are dropped
        unless one of the given specialties allows them.
        """
        specialties = set(specialties)
        options = []
        for value, label in cls.Stage.choices:
            allowed = cls.SPECIALTY_RESTRICTED_STAGES.get(value)
            if allowed is None or (allowed & specialties):
                options.append((value, label))
        return options


class Investigation(models.Model):
    """One item of a patient's workup — ordered, then resulted.

    The whole team watches these: a patient can only be presented at MDC once
    every ``required`` investigation has come back.
    """

    class Kind(models.TextChoices):
        # Endoscopy / tissue
        COLONOSCOPY = "COLONOSCOPY", "Colonoscopy"
        SIGMOIDOSCOPY = "SIGMOIDOSCOPY", "Sigmoidoscopy"
        GASTROSCOPY = "GASTROSCOPY", "Gastroscopy / OGD"
        PATHOLOGY = "PATHOLOGY", "Pathology"
        FNA = "FNA", "FNA / core biopsy"
        # Imaging
        MAMMOGRAM = "MAMMOGRAM", "Mammogram"
        BREAST_US = "BREAST_US", "Breast ultrasound"
        NECK_US = "NECK_US", "Neck ultrasound"
        CAP_CT = "CAP_CT", "CAP CT"
        PELVIC_MRI = "PELVIC_MRI", "Pelvic MRI"
        ABDOMEN_MRI = "ABDOMEN_MRI", "Abdomen MRI"
        BREAST_MRI = "BREAST_MRI", "Breast MRI"
        LOCAL_MRI = "LOCAL_MRI", "MRI of primary site"
        PET_CT = "PET_CT", "PET scan"
        BONE_SCAN = "BONE_SCAN", "Bone scan"
        # Labs
        CEA = "CEA", "CEA"
        TUMOR_MARKERS = "TUMOR_MARKERS", "Tumour markers"
        THYROID_FUNCTION = "THYROID_FUNCTION", "Thyroid function"
        GENETICS = "GENETICS", "Genetic testing"
        # Fitness
        ECHO = "ECHO", "Echocardiogram"
        PFT = "PFT", "Pulmonary function tests"

    class Status(models.TextChoices):
        PLANNED = "PLANNED", "Planned"
        ORDERED = "ORDERED", "Ordered"
        READY = "READY", "Result ready"

    class Purpose(models.TextChoices):
        BASELINE = "BASELINE", "Baseline workup"
        RESTAGING = "RESTAGING", "Restaging"

    patient = models.ForeignKey(
        Patient, on_delete=models.CASCADE, related_name="investigations"
    )
    kind = models.CharField(max_length=24, choices=Kind.choices)
    purpose = models.CharField(
        max_length=12, choices=Purpose.choices, default=Purpose.BASELINE
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PLANNED)
    required = models.BooleanField(
        default=True, help_text="Required items gate MDC presentation."
    )
    ordered_on = models.DateField(null=True, blank=True)
    resulted_on = models.DateField(null=True, blank=True)
    result_text = models.TextField(
        blank=True, help_text="The report text, as it will appear on the MDC slide."
    )
    # Set when a suggestion came from the guideline brain rather than a person.
    suggested_by_ai = models.BooleanField(default=False)
    rationale = models.TextField(
        blank=True, help_text="Why this was requested (guideline citation, if AI-suggested)."
    )

    class Meta:
        ordering = ["purpose", "kind"]
        constraints = [
            models.UniqueConstraint(
                fields=["patient", "kind", "purpose"],
                name="unique_investigation_per_patient_purpose",
            )
        ]

    def __str__(self):
        return f"{self.patient.name} — {self.get_kind_display()} ({self.get_status_display()})"

    def mark_ready(self, result_text, on=None):
        """Record a result. Kept here so every caller sets the same three fields."""
        self.result_text = result_text
        self.status = self.Status.READY
        self.resulted_on = on or date.today()
        self.save(update_fields=["result_text", "status", "resulted_on"])


class TreatmentCourse(models.Model):
    """A course of NACT or TNT that the team follows between MDC decisions.

    Patients stay on the team's list while this runs. Two alerts come off it:
    one before the last cycle (so restaging is ordered) and one when the
    restaging reports land (so the team reviews before the next clinic).
    """

    class Kind(models.TextChoices):
        NACT = "NACT", "Neoadjuvant chemotherapy"
        TNT = "TNT", "Total neoadjuvant therapy (rectal)"

    patient = models.ForeignKey(
        Patient, on_delete=models.CASCADE, related_name="treatment_courses"
    )
    kind = models.CharField(max_length=6, choices=Kind.choices)
    regimen = models.CharField(max_length=120, help_text="e.g. 'XELOX x 6', 'AC-T'.")
    total_cycles = models.PositiveSmallIntegerField()
    completed_cycles = models.PositiveSmallIntegerField(default=0)
    start_date = models.DateField()
    next_cycle_date = models.DateField(null=True, blank=True)
    active = models.BooleanField(default=True)

    # Alert bookkeeping — so each email goes out exactly once.
    restaging_alert_sent_on = models.DateField(null=True, blank=True)
    results_alert_sent_on = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.patient.name} — {self.get_kind_display()} ({self.regimen})"

    @property
    def cycles_remaining(self):
        return max(self.total_cycles - self.completed_cycles, 0)

    @property
    def on_last_cycle(self):
        """True from the penultimate cycle onwards — the point to order restaging."""
        return self.active and self.cycles_remaining <= 1

    @property
    def restaging_investigations(self):
        return self.patient.investigations.filter(
            purpose=Investigation.Purpose.RESTAGING
        )

    @property
    def restaging_ready(self):
        """True once restaging has been ordered and every report is back."""
        items = list(self.restaging_investigations)
        return bool(items) and all(i.status == Investigation.Status.READY for i in items)


class SurgeryBooking(models.Model):
    """A patient placed on the team's surgery schedule by the coordinator."""

    patient = models.ForeignKey(
        Patient, on_delete=models.CASCADE, related_name="surgery_bookings"
    )
    planned_date = models.DateField()
    procedure = models.CharField(max_length=200, help_text="e.g. 'Open APR', 'Right hemicolectomy'.")
    listed_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="surgeries_listed",
    )
    performed = models.BooleanField(default=False)
    performed_on = models.DateField(null=True, blank=True)
    final_pathology = models.TextField(
        blank=True, help_text="Final histopathology — carried onto the post-op MDC slide."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["planned_date"]

    def __str__(self):
        return f"{self.patient.name} — {self.procedure} ({self.planned_date})"
