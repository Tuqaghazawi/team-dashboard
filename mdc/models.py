from django.db import models


class MDCListing(models.Model):
    """A patient placed on a specific MDC's meeting list for discussion."""

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
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["meeting_date", "patient__name"]

    def __str__(self):
        return f"{self.patient.name} — {self.mdc.name} ({self.meeting_date})"
