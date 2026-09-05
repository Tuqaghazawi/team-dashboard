from django.db import models

# Which MDC a patient's specialty normally goes to. "General surgical oncology" is
# deliberately absent: those cases vary (some are sarcoma), so the coordinator chooses.
SPECIALTY_TO_MDC_NAME = {
    "BREAST": "Breast",
    "THYROID": "Thyroid",
    "SARCOMA": "Sarcoma",
    "HPB": "Gastrointestinal (GI)",
    "UPPER_GI": "Gastrointestinal (GI)",
    "COLORECTAL": "Gastrointestinal (GI)",
}


def suggested_mdc_for(specialty):
    """The MDC a patient of this specialty usually goes to, or None if it must be chosen."""
    from teams.models import MDC

    name = SPECIALTY_TO_MDC_NAME.get(specialty)
    return MDC.objects.filter(name=name).first() if name else None


class MDCListing(models.Model):
    """A patient placed on a specific MDC's meeting list for discussion."""

    class Decision(models.TextChoices):
        SURGERY = "SURGERY", "Surgery"
        NACT = "NACT", "Neoadjuvant chemotherapy"
        TNT = "TNT", "Total neoadjuvant therapy (rectal)"
        REFER_MEDICAL = "REFER_MEDICAL", "Refer to medical oncology"
        MORE_WORKUP = "MORE_WORKUP", "Further workup needed"
        SURVEILLANCE = "SURVEILLANCE", "Surveillance"
        WATCH_WAIT = "WATCH_WAIT", "Watch & wait"
        PALLIATIVE = "PALLIATIVE", "Best supportive / palliative care"

    # Where a patient goes once each decision is recorded.
    DECISION_TO_STAGE = {
        Decision.SURGERY: "SURGERY",
        Decision.NACT: "NACT",
        Decision.TNT: "TNT",
        Decision.REFER_MEDICAL: "REFERRED",
        Decision.MORE_WORKUP: "WORKUP",
        Decision.SURVEILLANCE: "SURVEILLANCE",
        Decision.WATCH_WAIT: "WATCH_WAIT",
        Decision.PALLIATIVE: "REFERRED",
    }

    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.CASCADE,
        related_name="mdc_listings",
    )
    mdc = models.ForeignKey(
        "teams.MDC",
        on_delete=models.PROTECT,
        related_name="listings",
    )
    meeting_date = models.DateField(help_text="The MDC meeting this patient is listed for.")
    presented = models.BooleanField(default=False, help_text="Has this patient been discussed yet?")
    decision = models.TextField(blank=True, help_text="MDC decision / notes (filled after discussion).")
    decision_category = models.CharField(
        max_length=16,
        choices=Decision.choices,
        blank=True,
        help_text="The structured outcome — this is what moves the patient on.",
    )
    decided_on = models.DateField(null=True, blank=True)
    is_postop = models.BooleanField(
        default=False,
        help_text="This listing is the post-operative re-discussion, not the initial one.",
    )
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["meeting_date", "patient__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["patient", "mdc", "meeting_date"],
                name="unique_patient_per_mdc_meeting",
            )
        ]

    def __str__(self):
        return f"{self.patient.name} — {self.mdc.name} ({self.meeting_date})"


class GuidelineSuggestion(models.Model):
    """A cached answer from the guideline brain, for one patient.

    Stored rather than re-asked on every page load, and kept as a *suggestion*:
    it is displayed distinctly from recorded clinical fact, it never changes the
    patient record, and it carries the citations that go into the slide notes.
    """

    class Kind(models.TextChoices):
        WORKUP = "WORKUP", "Suggested workup"
        DECISION = "DECISION", "Suggested decision"

    patient = models.ForeignKey(
        "patients.Patient", on_delete=models.CASCADE, related_name="guideline_suggestions"
    )
    kind = models.CharField(max_length=10, choices=Kind.choices)
    question = models.TextField()
    answer = models.TextField()
    citations = models.TextField(blank=True, help_text="One source label per line.")
    requested_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_kind_display()} — {self.patient.name}"

    @property
    def citation_list(self):
        return [c for c in self.citations.splitlines() if c.strip()]

    def as_slide_note(self):
        """The evidence block written into a slide's notes field."""
        lines = [f"{self.get_kind_display()} (guideline brain — for discussion only)", ""]
        lines.append(self.answer)
        if self.citation_list:
            lines.extend(["", "Sources:"])
            lines.extend(f"  - {c}" for c in self.citation_list)
        return "\n".join(lines)
