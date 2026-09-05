"""Pull new results and medications from the EHR into the dashboard.

    python manage.py sync_ehr

Run this on a schedule (Task Scheduler / cron) alongside send_due_alerts. Each
pass fills in any investigation whose report has been finalised since the last
run, and emails the team when that completes a patient's workup or their
restaging — through the same code path a manually entered result uses.

By default it only touches patients with something still outstanding. Use --all
to re-read every patient.
"""

from django.core.management.base import BaseCommand
from django.db.models import Q

from ehr import source, sync
from patients.models import Investigation, Patient


class Command(BaseCommand):
    help = "Read the EHR and fill in any investigation results that are now final."

    def add_arguments(self, parser):
        parser.add_argument(
            "--all", action="store_true",
            help="Re-read every patient, not just those with outstanding results.",
        )
        parser.add_argument(
            "--mrn", help="Sync one patient by MRN.",
        )

    def handle(self, *args, **options):
        patients = self._patients(options)
        if not patients:
            self.stdout.write("No patients to sync.")
            return

        try:
            done = sync.sync_all(patients)
        except source.EHRUnavailable as exc:
            self.stderr.write(self.style.ERROR(f"EHR unavailable: {exc}"))
            return

        changed = notified = 0
        for patient, outcome in done:
            if outcome.anything_happened:
                changed += 1
                flag = "  [team emailed]" if outcome.notified else ""
                self.stdout.write(f"{patient.mrn} {patient.name}: {outcome.summary()}{flag}")
            if outcome.notified:
                notified += 1
            for code in outcome.unmatched:
                self.stdout.write(
                    self.style.WARNING(
                        f"  {patient.mrn}: EHR holds '{code}', which is not on this "
                        f"patient's checklist — not added"
                    )
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Synced {len(done)} patient(s); {changed} changed; {notified} team email(s) sent."
            )
        )

    def _patients(self, options):
        if options["mrn"]:
            return list(Patient.objects.filter(mrn=options["mrn"]))
        if options["all"]:
            return list(Patient.objects.all())
        # Patients with something outstanding: a result still to come, an
        # operation booked (whose medications must be current for the peri-op
        # check), or no EHR read at all yet.
        waiting_on_results = Q(
            investigations__status__in=[
                Investigation.Status.PLANNED,
                Investigation.Status.ORDERED,
            ]
        )
        booked_for_surgery = Q(surgery_bookings__performed=False)
        never_read = Q(ehr_synced_at__isnull=True)
        return list(
            Patient.objects.filter(
                waiting_on_results | booked_for_surgery | never_read
            ).distinct()
        )
