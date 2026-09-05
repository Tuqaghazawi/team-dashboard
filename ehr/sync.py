"""Pulling a patient's results and medications out of the EHR.

Two rules shape this:

* **The EHR is the source, the checklist is the plan.** A result is only taken
  for an investigation the team actually asked for. The EHR holding a report the
  team never requested does not silently add it to the workup — it is reported
  back as unmatched, for a person to decide about.

* **Finalised results only.** A pending or preliminary report is left alone, so
  "all results are back" never becomes true on the strength of a report nobody
  has signed.

Filling the last outstanding result fires the same team notification the manual
path fires, through ``patients.flow`` — there is one code path for "the workup is
complete", regardless of how the result arrived.
"""

import logging

from django.utils import timezone

from patients import flow
from patients.models import Investigation, Medication

from . import source

logger = logging.getLogger(__name__)

# The EHR's test codes, mapped onto the dashboard's investigation kinds. A real
# integration needs exactly this table; keeping it explicit means an unknown code
# is reported rather than guessed at.
TEST_CODE_MAP = {kind.value: kind.value for kind in Investigation.Kind}

FINAL_STATUSES = {"FINAL", "final", "F"}


class SyncResult:
    """What one sync did, so the UI and the command can both report it."""

    def __init__(self):
        self.results_filled = []
        self.still_pending = []
        self.unmatched = []
        self.medications_synced = 0
        self.notified = False

    @property
    def anything_happened(self):
        return bool(self.results_filled) or self.medications_synced

    def summary(self):
        parts = []
        if self.results_filled:
            parts.append(f"{len(self.results_filled)} result(s) received")
        if self.still_pending:
            parts.append(f"{len(self.still_pending)} still pending at the lab")
        if self.medications_synced:
            parts.append(f"{self.medications_synced} medication(s) updated")
        if self.unmatched:
            parts.append(f"{len(self.unmatched)} report(s) not on the checklist")
        return "; ".join(parts) or "nothing new"


def sync_patient(patient, pull_medications=True):
    """Read the EHR for one patient and apply what is new. Raises EHRUnavailable."""
    outcome = SyncResult()

    _sync_results(patient, outcome)
    if pull_medications:
        outcome.medications_synced = _sync_medications(patient)

    patient.ehr_synced_at = timezone.now()
    patient.save(update_fields=["ehr_synced_at"])
    return outcome


def _sync_results(patient, outcome):
    rows = source.results_for(patient.mrn)

    # The checklist, keyed the way the EHR rows arrive.
    wanted = {
        (item.kind, item.purpose): item
        for item in patient.investigations.all()
    }

    for row in rows:
        kind = TEST_CODE_MAP.get(row["test_code"])
        purpose = row["purpose"]
        if kind is None:
            outcome.unmatched.append(row["test_code"])
            continue

        item = wanted.get((kind, purpose))
        if item is None:
            # A report the team never requested. Surfaced, never auto-added.
            outcome.unmatched.append(f"{row['test_code']} ({purpose.lower()})")
            continue

        if row["status"] not in FINAL_STATUSES:
            if item.status != Investigation.Status.READY:
                item.status = Investigation.Status.ORDERED
                item.save(update_fields=["status"])
                outcome.still_pending.append(item.get_kind_display())
            continue

        if item.status == Investigation.Status.READY:
            continue  # already have it; never overwrite a recorded result

        item.mark_ready(row["report"], on=_as_date(row["resulted_on"]))
        outcome.results_filled.append(item)

        # Same notification path as a manually entered result.
        if flow.on_result_recorded(item):
            outcome.notified = True


def _sync_medications(patient):
    rows = source.medications_for(patient.mrn)
    seen = set()

    for row in rows:
        Medication.objects.update_or_create(
            patient=patient,
            drug_name=row["drug_name"],
            defaults={
                "drug_class": row["drug_class"] or "",
                "high_alert": bool(row["high_alert"]),
                "active": row["status"] == "active",
                "started_on": _as_date(row["started_on"]),
            },
        )
        seen.add(row["drug_name"])

    # A drug the EHR no longer lists has been stopped; mark it rather than
    # deleting it, so the record of what was checked survives.
    patient.medications.exclude(drug_name__in=seen).update(active=False)
    return len(rows)


def sync_all(patients):
    """Sync many patients, skipping any that fail. Returns [(patient, outcome)]."""
    done = []
    for patient in patients:
        try:
            done.append((patient, sync_patient(patient)))
        except source.EHRUnavailable:
            raise
        except Exception:
            logger.exception("EHR sync failed for %s", patient)
    return done


def _as_date(value):
    if not value:
        return None
    from datetime import date, datetime

    if isinstance(value, date):
        return value
    return datetime.strptime(value, "%Y-%m-%d").date()
