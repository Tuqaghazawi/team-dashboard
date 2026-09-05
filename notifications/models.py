from django.db import models
from django.utils import timezone


class Notification(models.Model):
    """One message to one person about one patient.

    Every notification is also an email. We keep the row so the dashboard can
    show an inbox, and so we can prove an alert went out (and never send it
    twice) without depending on the mail server.
    """

    class Kind(models.TextChoices):
        NEW_PATIENT = "NEW_PATIENT", "New patient registered to your team"
        MDC_LISTED = "MDC_LISTED", "Patient listed for MDC"
        WORKUP_READY = "WORKUP_READY", "Workup complete — ready for MDC"
        DECISION = "DECISION", "MDC decision recorded"
        RESTAGING_DUE = "RESTAGING_DUE", "Last cycle approaching — order restaging"
        RESTAGING_READY = "RESTAGING_READY", "Restaging reports ready for review"
        POSTOP_MDC_DUE = "POSTOP_MDC_DUE", "Post-op patient needs re-discussion"
        SURGERY_LISTED = "SURGERY_LISTED", "Patient added to the surgery schedule"

    recipient = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="notifications"
    )
    patient = models.ForeignKey(
        "patients.Patient", on_delete=models.CASCADE, related_name="notifications"
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    subject = models.CharField(max_length=200)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)
    emailed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_kind_display()} -> {self.recipient} ({self.patient.name})"

    @property
    def is_read(self):
        return self.read_at is not None

    def mark_read(self):
        if self.read_at is None:
            self.read_at = timezone.now()
            self.save(update_fields=["read_at"])
