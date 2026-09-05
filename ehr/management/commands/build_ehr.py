"""Build the synthetic EHR that the dashboard reads from.

    python manage.py build_ehr

Creates data/synthetic/ehr.sqlite3 with results and medication orders for every
patient currently in the dashboard, keyed by their own MRN — which is what a
real integration keys on.

Deliberately leaves some results PENDING, so the workup checklist has something
to wait for and the "all results are back" email has a moment to fire.

Synthetic data only. This command invents patient data and must never be pointed
at anything real.
"""

import random
import sqlite3
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from ehr.source import database_path
from patients.models import Investigation, Patient
from patients.workup import BASELINE_WORKUP, RESTAGING_WORKUP

K = Investigation.Kind

REPORTS = {
    K.COLONOSCOPY: "Malignant-looking mass at 10-13 cm from the anal verge; scope passed to caecum.",
    K.SIGMOIDOSCOPY: "Obstructing mass at 8 cm from the anal verge; stent inserted.",
    K.GASTROSCOPY: "Ulcerated mass at the gastro-oesophageal junction, 5 cm in length.",
    K.PATHOLOGY: "Moderately differentiated adenocarcinoma. No lymphovascular invasion identified.",
    K.FNA: "Papillary thyroid carcinoma (Bethesda VI).",
    K.MAMMOGRAM: "Spiculated mass in the upper outer quadrant, 2.8 cm, with pleomorphic calcifications.",
    K.BREAST_US: "Irregular hypoechoic mass 2.6 cm; two morphologically abnormal axillary nodes.",
    K.NECK_US: "Hypoechoic nodule 2.1 cm right lobe, microcalcifications, TIRADS 5.",
    K.CAP_CT: "No distant metastasis. No enlarged intrathoracic lymph nodes. Liver appears normal.",
    K.PELVIC_MRI: "T3N2 rectal cancer 8.6 cm from the anal verge. Mesorectal fascia intact. EMVI negative.",
    K.ABDOMEN_MRI: "No definite hepatic metastasis. Two benign hepatic cysts, segments 4 and 6.",
    K.BREAST_MRI: "Unifocal enhancing mass 2.9 cm. No contralateral disease.",
    K.LOCAL_MRI: "Deep soft-tissue mass 9 cm in the posterior thigh, abutting the femur.",
    K.PET_CT: "Hypermetabolic primary lesion. No distant hypermetabolic disease.",
    K.BONE_SCAN: "No scintigraphic evidence of skeletal metastasis.",
    K.CEA: "2.4 ng/mL",
    K.TUMOR_MARKERS: "CA 19-9: 38 U/mL",
    K.THYROID_FUNCTION: "TSH 1.8 mIU/L. Euthyroid.",
    K.GENETICS: "No pathogenic or likely pathogenic variant identified.",
    K.ECHO: "EF 60%. No regional wall motion abnormality.",
    K.PFT: "FEV1 82% predicted. FEV1/FVC 0.74.",
}

RESTAGING_REPORTS = {
    K.CAP_CT: "Interval partial response. No new lesions. No distant metastasis.",
    K.PELVIC_MRI: "Partial response; tumour now 4.1 cm. Mesorectal fascia remains clear.",
    K.ABDOMEN_MRI: "No hepatic metastasis. Previously noted lesions represent focal fatty change.",
    K.CEA: "1.6 ng/mL (down from 2.4)",
    K.MAMMOGRAM: "Interval reduction in mass size, now 1.4 cm.",
    K.BREAST_US: "Residual hypoechoic area 1.3 cm. Axillary nodes now normal in morphology.",
    K.PET_CT: "Marked reduction in metabolic activity at the primary site.",
    K.LOCAL_MRI: "Mass reduced to 6 cm. Femoral cortex intact.",
    K.NECK_US: "No residual nodule identified.",
}

# Drug names must match the guideline rule table in ai/pharmacy so the check has
# something to act on. A mix of hold, discontinue and continue.
DRUGS = [
    ("Warfarin", "Anticoagulant", 1),
    ("Clopidogrel", "Antiplatelet", 1),
    ("Aspirin", "Antiplatelet", 0),
    ("Enoxaparin", "Anticoagulant", 1),
    ("Ibuprofen", "NSAID", 0),
    ("Naproxen", "NSAID", 0),
    ("Metformin", "Antidiabetic", 0),
    ("Spironolactone", "Diuretic", 0),
    ("Furosemide", "Diuretic", 0),
    ("Enalapril", "ACE inhibitor", 0),
    ("Bisoprolol", "Beta blocker", 0),
    ("Amlodipine", "Calcium channel blocker", 0),
    ("Simvastatin", "Statin", 0),
    ("Levothyroxine", "Thyroid hormone", 0),
]

SCHEMA = """
CREATE TABLE ehr_patients (mrn TEXT PRIMARY KEY, name TEXT, date_of_birth TEXT);

CREATE TABLE ehr_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mrn TEXT NOT NULL,
    test_code TEXT NOT NULL,
    purpose TEXT NOT NULL,
    status TEXT NOT NULL,
    resulted_on TEXT,
    report TEXT
);

CREATE TABLE ehr_medications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mrn TEXT NOT NULL,
    drug_name TEXT NOT NULL,
    drug_class TEXT,
    high_alert INTEGER DEFAULT 0,
    status TEXT NOT NULL,
    started_on TEXT
);

CREATE INDEX idx_results_mrn ON ehr_results (mrn);
CREATE INDEX idx_meds_mrn ON ehr_medications (mrn);
"""


class Command(BaseCommand):
    help = "Build the synthetic EHR (results + medications) for the current patients."

    def add_arguments(self, parser):
        parser.add_argument(
            "--pending",
            type=float,
            default=0.25,
            help="Fraction of baseline results left PENDING (default 0.25).",
        )

    def handle(self, *args, **options):
        random.seed(11)
        path = database_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            path.unlink()

        connection = sqlite3.connect(path)
        connection.executescript(SCHEMA)

        patients = list(Patient.objects.all())
        results = medications = 0
        for patient in patients:
            connection.execute(
                "INSERT INTO ehr_patients VALUES (?, ?, ?)",
                (patient.mrn, patient.name, patient.date_of_birth.isoformat()),
            )
            results += self._results(connection, patient, options["pending"])
            medications += self._medications(connection, patient)

        connection.commit()
        connection.close()

        self.stdout.write(self.style.SUCCESS(f"Built {path}"))
        self.stdout.write(
            f"  {len(patients)} patients, {results} results, {medications} medication orders"
        )
        self.stdout.write("  Run 'python manage.py sync_ehr' to pull them into the dashboard.")

    def _results(self, connection, patient, pending_fraction):
        today = timezone.localdate()
        written = 0

        baseline = BASELINE_WORKUP.get(patient.specialty, BASELINE_WORKUP["GENERAL"])
        for kind in baseline:
            pending = random.random() < pending_fraction
            connection.execute(
                "INSERT INTO ehr_results (mrn, test_code, purpose, status, resulted_on, report)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    patient.mrn, kind, Investigation.Purpose.BASELINE,
                    "PENDING" if pending else "FINAL",
                    None if pending else (today - timedelta(days=random.randint(2, 30))).isoformat(),
                    None if pending else REPORTS.get(kind, "Reported."),
                ),
            )
            written += 1

        # Restaging exists in the EHR only for patients who have had treatment.
        if patient.treatment_courses.exists():
            restaging = RESTAGING_WORKUP.get(patient.specialty, RESTAGING_WORKUP["GENERAL"])
            for kind in restaging:
                connection.execute(
                    "INSERT INTO ehr_results (mrn, test_code, purpose, status, resulted_on, report)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        patient.mrn, kind, Investigation.Purpose.RESTAGING, "FINAL",
                        (today - timedelta(days=random.randint(1, 10))).isoformat(),
                        RESTAGING_REPORTS.get(kind, "Interval partial response."),
                    ),
                )
                written += 1
        return written

    def _medications(self, connection, patient):
        today = timezone.localdate()
        chosen = random.sample(DRUGS, random.randint(2, 5))
        for drug_name, drug_class, high_alert in chosen:
            connection.execute(
                "INSERT INTO ehr_medications (mrn, drug_name, drug_class, high_alert, status, started_on)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    patient.mrn, drug_name, drug_class, high_alert, "active",
                    (today - timedelta(days=random.randint(30, 700))).isoformat(),
                ),
            )
        return len(chosen)
