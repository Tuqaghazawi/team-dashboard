from django.db import models


class MDC(models.Model):
    """A multidisciplinary conference (tumor board) — e.g. Breast, GI, Sarcoma, Thyroid."""

    name = models.CharField(max_length=50, unique=True)

    class Meta:
        verbose_name = "MDC"
        verbose_name_plural = "MDCs"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Team(models.Model):
    """A consultant-led surgical team that patients are assigned to."""

    consultant = models.CharField(max_length=100, help_text="The consultant who leads this team.")
    specialty = models.CharField(max_length=100, help_text="e.g. 'Thyroid and breast', 'Colorectal cancer'.")

    class Meta:
        ordering = ["consultant"]

    def __str__(self):
        return f"{self.consultant} — {self.specialty}"
