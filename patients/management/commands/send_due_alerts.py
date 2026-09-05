"""Send the time-based alerts. Run this once a day from Task Scheduler / cron:

    python manage.py send_due_alerts
"""

from django.core.management.base import BaseCommand

from patients.flow import check_postop_mdc_due, check_restaging_due


class Command(BaseCommand):
    help = "Email teams about restaging due before the last cycle, and post-op MDC re-discussions."

    def handle(self, *args, **options):
        courses = check_restaging_due()
        for course in courses:
            self.stdout.write(
                self.style.SUCCESS(f"Restaging alert sent for {course.patient.name}")
            )

        patients = check_postop_mdc_due()
        for patient in patients:
            self.stdout.write(
                self.style.SUCCESS(f"Post-op MDC reminder sent for {patient.name}")
            )

        if not courses and not patients:
            self.stdout.write("Nothing due.")
