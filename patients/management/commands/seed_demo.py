"""Build a full synthetic demo: users for every role, and patients at every stage.

    python manage.py seed_demo

Synthetic data only — no real patient ever goes near this command. Re-running it
tops the data back up without duplicating anything.
"""

import random
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import User
from mdc.models import MDCListing, suggested_mdc_for
from patients.categories import week_range
from patients.models import Investigation, Patient, SurgeryBooking, TreatmentCourse
from patients.workup import create_baseline_workup, create_restaging_workup
from teams.models import MDC, FellowAssignment, Team

DEMO_PASSWORD = "demo1234"

MDC_DAYS = {"Breast": 2, "Gastrointestinal (GI)": 1, "Sarcoma": 6, "Thyroid": 3}

TEAMS = [
    ("Dr. Mahmoud Al-Masri", "General surgical oncology"),
    ("Dr. Faiez Daoud", "General surgical oncology"),
    ("Dr. Mohd Basem Hamdan", "Thyroid and breast"),
    ("Dr. Mohammed Al-Qaisi", "Thyroid and breast"),
    ("Dr. Fade Alawneh", "Thyroid and breast"),
    ("Dr. Ali Al-Ebous", "Thyroid and breast"),
    ("Dr. Ali Dabous", "HPB and general surgical oncology"),
    ("Dr. Bilal Baker", "HPB and upper GI"),
    ("Dr. Motaz Makhamreh", "HPB and upper GI"),
    ("Dr. Basem Jalabneh", "Colorectal cancer"),
    ("Dr. Amro Mureb", "Colorectal cancer"),
]

# Synthetic reports, written to read like the decks the teams actually present.
RESULTS = {
    "COLONOSCOPY": "Malignant-looking mass at 10-13 cm from the anal verge; scope passed.",
    "SIGMOIDOSCOPY": "Obstructing mass at 8 cm from the anal verge.",
    "GASTROSCOPY": "Ulcerated mass at the gastro-oesophageal junction, 5 cm in length.",
    "PATHOLOGY": "Moderately differentiated adenocarcinoma.",
    "FNA": "Papillary thyroid carcinoma (Bethesda VI).",
    "MAMMOGRAM": "Spiculated mass in the upper outer quadrant, 2.8 cm, with calcifications.",
    "BREAST_US": "Irregular hypoechoic mass 2.6 cm; two abnormal axillary nodes.",
    "NECK_US": "Hypoechoic nodule 2.1 cm in the right lobe, microcalcifications, TIRADS 5.",
    "CAP_CT": "No distant metastasis. No enlarged intrathoracic lymph nodes.",
    "PELVIC_MRI": "T3N2 rectal cancer 8.6 cm from the anal verge. Mesorectal fascia intact.",
    "ABDOMEN_MRI": "No definite hepatic metastasis. Two benign hepatic cysts.",
    "BREAST_MRI": "Unifocal enhancing mass 2.9 cm, no contralateral disease.",
    "LOCAL_MRI": "Deep soft-tissue mass 9 cm in the posterior thigh, abutting the femur.",
    "PET_CT": "Hypermetabolic primary. No distant hypermetabolic disease.",
    "BONE_SCAN": "No scintigraphic evidence of skeletal metastasis.",
    "CEA": "2.4",
    "TUMOR_MARKERS": "CA 19-9: 38",
    "THYROID_FUNCTION": "TSH 1.8, euthyroid.",
    "GENETICS": "No pathogenic variant identified.",
    "ECHO": "EF 60%, no regional wall motion abnormality.",
    "PFT": "FEV1 82% predicted.",
}

CASES = [
    # (name, mrn, dob, diagnosis, specialty, sex, comorbidities, stage, genetics, target_stage)
    ("Layla Haddad", "310401", date(1968, 3, 14), "Right breast cancer", "BREAST", "F",
     "HTN, DM, post-menopausal, non-smoker", "cT2N+", "Negative", "REGISTERED"),
    ("Nadia Suleiman", "310402", date(1975, 8, 2), "Left breast cancer", "BREAST", "F",
     "medically free, PS 0", "cT2N0", "Pending", "WORKUP"),
    ("Rania Odeh", "310403", date(1959, 11, 21), "Right breast cancer", "BREAST", "F",
     "hypothyroid, obese, PS 1", "cT4N+", "BRCA1 positive", "MDC_READY"),
    ("Samir Khoury", "310404", date(1953, 5, 30), "Low rectal cancer", "COLORECTAL", "M",
     "HTN, ex-smoker, PS 0-1", "T3N2", "Negative", "MDC_READY"),
    ("Hana Barakat", "310405", date(1962, 1, 9), "Sigmoid colon cancer", "COLORECTAL", "F",
     "medically free, PS 0", "T3N1", "Not indicated", "TNT"),
    ("Yousef Nabulsi", "310406", date(1948, 7, 18), "Mid rectal cancer", "COLORECTAL", "M",
     "DM, IHD, PS 1", "T3N2", "Negative", "TNT"),
    ("Maha Zaid", "310407", date(1971, 4, 4), "Left breast cancer", "BREAST", "F",
     "asthma, pre-menopausal, non-smoker", "cT3N+", "Negative", "NACT"),
    ("Omar Tarawneh", "310408", date(1966, 9, 27), "Papillary thyroid carcinoma", "THYROID", "M",
     "medically free, PS 0", "cT2N1a", "Not indicated", "SURGERY"),
    ("Dina Masalha", "310409", date(1957, 12, 12), "Pancreatic head mass", "HPB", "F",
     "DM, PS 1", "cT2N0", "Pending", "SURGERY"),
    ("Khalil Rashid", "310410", date(1944, 6, 6), "Gastric cancer", "UPPER_GI", "M",
     "COPD, ex-smoker, PS 1", "cT3N1", "Negative", "POSTOP"),
    ("Amal Zawahreh", "310411", date(1980, 2, 17), "Soft tissue sarcoma, thigh", "SARCOMA", "F",
     "medically free, PS 0", "T2bN0", "Not indicated", "POSTOP"),
    ("Fadi Qasem", "310412", date(1955, 10, 8), "Ascending colon cancer", "COLORECTAL", "M",
     "HTN, PS 0", "T3N0", "Negative", "WORKUP"),
]


class Command(BaseCommand):
    help = "Create synthetic teams, MDCs, users and patients across every pathway stage."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete the demo patients first and rebuild them from scratch.",
        )

    def handle(self, *args, **options):
        random.seed(7)
        if options["reset"]:
            mrns = [case[1] for case in CASES]
            deleted, _ = Patient.objects.filter(mrn__in=mrns).delete()
            self.stdout.write(f"Reset: removed {deleted} demo rows")
        self.teams = self._teams()
        self.mdcs = self._mdcs()
        self._users()
        self._patients()
        self.stdout.write(self.style.SUCCESS("\nDemo data ready."))
        self.stdout.write(f"All demo logins use the password: {DEMO_PASSWORD}")

    # --- reference data ---

    def _teams(self):
        teams = {}
        for consultant, specialty in TEAMS:
            team, _ = Team.objects.get_or_create(
                consultant=consultant, defaults={"specialty": specialty}
            )
            teams[consultant] = team
        self.stdout.write(f"Teams: {len(teams)}")
        return teams

    def _mdcs(self):
        mdcs = {}
        for name, weekday in MDC_DAYS.items():
            mdc, _ = MDC.objects.get_or_create(
                name=name, defaults={"meeting_weekday": weekday}
            )
            if mdc.meeting_weekday is None:
                mdc.meeting_weekday = weekday
                mdc.save(update_fields=["meeting_weekday"])
            mdcs[name] = mdc
        self.stdout.write(f"MDCs: {', '.join(mdcs)}")
        return mdcs

    def _users(self):
        colorectal = self.teams["Dr. Amro Mureb"]
        breast = self.teams["Dr. Fade Alawneh"]

        people = [
            ("prep1", "Rana", "Prep clinic", User.Role.PREP_COORDINATOR, None, None),
            ("chair1", "Prof.", "Chairman", User.Role.CHAIRMAN, None, None),
            ("coord1", "Demo", "Coordinator", User.Role.TEAM_COORDINATOR, breast, None),
            ("coord2", "Suha", "Coordinator", User.Role.TEAM_COORDINATOR, colorectal, None),
            ("cons1", "Fade", "Alawneh", User.Role.CONSULTANT, breast, None),
            ("cons2", "Amro", "Mureb", User.Role.CONSULTANT, colorectal, None),
            ("fellow1", "Tuqa", "Fellow", User.Role.FELLOW, None, None),
            ("fellow2", "Yara", "Fellow", User.Role.FELLOW, None, None),
            ("mdc1", "Breast", "MDC coordinator", User.Role.MDC_COORDINATOR, None, self.mdcs["Breast"]),
        ]
        for username, first, last, role, team, mdc in people:
            user, _ = User.objects.get_or_create(username=username)
            user.first_name, user.last_name = first, last
            user.role, user.team, user.mdc = role, team, mdc
            # Demo addresses only — the console email backend prints, it does not send.
            user.email = f"{username}@example.test"
            user.set_password(DEMO_PASSWORD)
            user.save()

        # Fellows get a rotation, which is what grants them team access.
        start, end = FellowAssignment.current_quarter()
        for username, team in (("fellow1", colorectal), ("fellow2", breast)):
            FellowAssignment.objects.get_or_create(
                fellow=User.objects.get(username=username),
                team=team,
                start_date=start,
                defaults={"end_date": end},
            )
        self.stdout.write(f"Users: {len(people)} (rotation {start} to {end})")

    # --- patients ---

    def _patients(self):
        team_for = {
            "BREAST": "Dr. Fade Alawneh",
            "THYROID": "Dr. Mohd Basem Hamdan",
            "COLORECTAL": "Dr. Amro Mureb",
            "HPB": "Dr. Ali Dabous",
            "UPPER_GI": "Dr. Bilal Baker",
            "SARCOMA": "Dr. Mahmoud Al-Masri",
        }
        made = 0
        for (name, mrn, dob, diagnosis, specialty, sex,
             comorbidities, stage, genetics, target) in CASES:
            if Patient.objects.filter(mrn=mrn).exists():
                continue
            patient = Patient.objects.create(
                name=name, mrn=mrn, date_of_birth=dob, diagnosis=diagnosis,
                specialty=specialty, team=self.teams[team_for[specialty]],
                sex=sex, comorbidities=comorbidities, clinical_stage=stage,
                genetic_testing=genetics, stage=Patient.Stage.REGISTERED,
            )
            self._advance(patient, target)
            made += 1
        self.stdout.write(f"Patients created: {made}")

    def _advance(self, patient, target):
        """Walk a patient forward to the stage the demo wants them at."""
        if target == "REGISTERED":
            return

        create_baseline_workup(patient)
        patient.stage = Patient.Stage.WORKUP
        patient.save(update_fields=["stage"])

        if target == "WORKUP":
            # Partly done, so the checklist shows real progress.
            self._fill_results(patient, fraction=0.5)
            return

        self._fill_results(patient, fraction=1.0)

        if target == "MDC_READY":
            self._list_for_mdc(patient)
            patient.stage = Patient.Stage.MDC
            patient.save(update_fields=["stage"])
            return

        listing = self._list_for_mdc(patient, weeks_ahead=-1, presented=True)

        if target in ("NACT", "TNT"):
            kind = TreatmentCourse.Kind.TNT if target == "TNT" else TreatmentCourse.Kind.NACT
            listing.decision_category = (
                MDCListing.Decision.TNT if target == "TNT" else MDCListing.Decision.NACT
            )
            listing.decision = f"For {kind}"
            listing.decided_on = listing.meeting_date
            listing.save()
            total = 6 if target == "TNT" else 4
            course = TreatmentCourse.objects.create(
                patient=patient, kind=kind,
                regimen="XELOX x 6" if target == "TNT" else "AC-T",
                total_cycles=total, completed_cycles=total - 1,
                start_date=timezone.localdate() - timedelta(days=90),
                next_cycle_date=timezone.localdate() + timedelta(days=14),
            )
            patient.stage = getattr(Patient.Stage, target)
            patient.save(update_fields=["stage"])
            # On the last cycle: restaging is open but not yet resulted.
            create_restaging_workup(patient)
            course.restaging_alert_sent_on = timezone.localdate() - timedelta(days=3)
            course.save(update_fields=["restaging_alert_sent_on"])
            return

        if target in ("SURGERY", "POSTOP"):
            listing.decision_category = MDCListing.Decision.SURGERY
            listing.decision = "For surgery"
            listing.decided_on = listing.meeting_date
            listing.save()
            procedure = {
                "THYROID": "Total thyroidectomy + central neck dissection",
                "HPB": "Whipple procedure",
                "UPPER_GI": "Total gastrectomy",
                "SARCOMA": "Wide local excision, posterior thigh",
                "COLORECTAL": "Right hemicolectomy",
                "BREAST": "Modified radical mastectomy",
            }[patient.specialty]
            booking = SurgeryBooking.objects.create(
                patient=patient, procedure=procedure,
                planned_date=timezone.localdate() + timedelta(days=10),
            )
            patient.stage = Patient.Stage.SURGERY
            patient.save(update_fields=["stage"])

            if target == "POSTOP":
                booking.performed = True
                booking.performed_on = timezone.localdate() - timedelta(days=12)
                booking.planned_date = booking.performed_on
                booking.final_pathology = (
                    "ypT2N1a, negative margins, 2 of 14 nodes positive, +LVI."
                )
                booking.save()
                patient.stage = Patient.Stage.POSTOP
                patient.save(update_fields=["stage"])

    def _fill_results(self, patient, fraction):
        items = list(patient.investigations.filter(purpose=Investigation.Purpose.BASELINE))
        cutoff = max(1, int(len(items) * fraction))
        for i, item in enumerate(items):
            if i < cutoff:
                item.mark_ready(
                    RESULTS.get(item.kind, "Reported."),
                    on=timezone.localdate() - timedelta(days=random.randint(2, 25)),
                )
            else:
                item.status = Investigation.Status.ORDERED
                item.ordered_on = timezone.localdate() - timedelta(days=random.randint(3, 20))
                item.save(update_fields=["status", "ordered_on"])

    def _list_for_mdc(self, patient, weeks_ahead=1, presented=False):
        """List the patient on that MDC's meeting inside the target week.

        The meeting has to land in the week the demo is aiming at, so the
        dashboard's "next week" bucket actually shows somebody.
        """
        mdc = suggested_mdc_for(patient.specialty) or self.mdcs["Sarcoma"]
        start, _end = week_range(weeks_ahead)
        meeting = mdc.next_meeting_date(on_or_after=start) or start
        listing, _ = MDCListing.objects.get_or_create(
            patient=patient, mdc=mdc, meeting_date=meeting,
            defaults={"presented": presented},
        )
        return listing
