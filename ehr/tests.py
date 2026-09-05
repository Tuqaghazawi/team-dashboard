"""Tests for the EHR sync.

Each test builds its own throwaway EHR file and points EHR_DATABASE at it, so
nothing here depends on the synthetic demo database.
"""

import sqlite3
import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from django.core import mail
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from ehr import source, sync
from notifications.models import Notification
from patients.models import Investigation, Medication, Patient, TreatmentCourse
from teams.models import Team

SCHEMA = """
CREATE TABLE ehr_patients (mrn TEXT PRIMARY KEY, name TEXT, date_of_birth TEXT);
CREATE TABLE ehr_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT, mrn TEXT, test_code TEXT, purpose TEXT,
    status TEXT, resulted_on TEXT, report TEXT);
CREATE TABLE ehr_medications (
    id INTEGER PRIMARY KEY AUTOINCREMENT, mrn TEXT, drug_name TEXT, drug_class TEXT,
    high_alert INTEGER, status TEXT, started_on TEXT);
"""


class EHRTestCase(TestCase):
    """Base class that gives each test its own EHR file."""

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.path = Path(self._dir.name) / "ehr.sqlite3"
        self.connection = sqlite3.connect(self.path)
        # Cleanups run last-registered-first, so this closes before the
        # TemporaryDirectory is removed — Windows will not delete an open file.
        self.addCleanup(self.connection.close)
        self.connection.executescript(SCHEMA)
        self.connection.commit()

        patcher = mock.patch.dict("os.environ", {"EHR_DATABASE": str(self.path)})
        patcher.start()
        self.addCleanup(patcher.stop)

        self.team = Team.objects.create(consultant="Dr. Test", specialty="Colorectal cancer")
        User.objects.create_user(
            "c1", email="c1@example.test", password="x",
            role=User.Role.TEAM_COORDINATOR, team=self.team,
        )
        self.patient = Patient.objects.create(
            name="Test Patient", mrn="970001", date_of_birth=date(1960, 1, 1),
            diagnosis="Rectal cancer", specialty="COLORECTAL", team=self.team,
        )
        self.connection.execute(
            "INSERT INTO ehr_patients VALUES (?, ?, ?)",
            (self.patient.mrn, self.patient.name, "1960-01-01"),
        )
        self.connection.commit()
        mail.outbox = []

    def add_result(self, test_code, status="FINAL", report="Reported.",
                   purpose=Investigation.Purpose.BASELINE, mrn=None):
        self.connection.execute(
            "INSERT INTO ehr_results (mrn, test_code, purpose, status, resulted_on, report)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (mrn or self.patient.mrn, test_code, purpose, status,
             date(2026, 8, 1).isoformat(), report),
        )
        self.connection.commit()

    def add_medication(self, drug_name, drug_class="", status="active", high_alert=0):
        self.connection.execute(
            "INSERT INTO ehr_medications (mrn, drug_name, drug_class, high_alert, status, started_on)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (self.patient.mrn, drug_name, drug_class, high_alert, status, "2025-01-01"),
        )
        self.connection.commit()

    def checklist(self, *kinds, purpose=Investigation.Purpose.BASELINE):
        return [
            Investigation.objects.create(patient=self.patient, kind=kind, purpose=purpose)
            for kind in kinds
        ]


class ResultSyncTests(EHRTestCase):
    def test_a_final_result_fills_the_matching_checklist_item(self):
        item, = self.checklist(Investigation.Kind.CAP_CT)
        self.add_result(Investigation.Kind.CAP_CT, report="No distant metastasis.")

        outcome = sync.sync_patient(self.patient)

        item.refresh_from_db()
        self.assertEqual(item.status, Investigation.Status.READY)
        self.assertEqual(item.result_text, "No distant metastasis.")
        self.assertEqual(len(outcome.results_filled), 1)

    def test_a_pending_result_is_not_taken(self):
        item, = self.checklist(Investigation.Kind.CAP_CT)
        self.add_result(Investigation.Kind.CAP_CT, status="PENDING", report=None)

        outcome = sync.sync_patient(self.patient)

        item.refresh_from_db()
        self.assertNotEqual(item.status, Investigation.Status.READY)
        self.assertEqual(item.status, Investigation.Status.ORDERED)
        self.assertEqual(outcome.results_filled, [])
        self.assertEqual(len(outcome.still_pending), 1)

    def test_a_report_not_on_the_checklist_is_reported_not_added(self):
        self.checklist(Investigation.Kind.CAP_CT)
        self.add_result(Investigation.Kind.PET_CT, report="Hypermetabolic.")

        outcome = sync.sync_patient(self.patient)

        self.assertEqual(self.patient.investigations.count(), 1)
        self.assertEqual(len(outcome.unmatched), 1)
        self.assertIn("PET_CT", outcome.unmatched[0])

    def test_an_existing_result_is_never_overwritten(self):
        item, = self.checklist(Investigation.Kind.CAP_CT)
        item.mark_ready("Entered by the fellow.")
        self.add_result(Investigation.Kind.CAP_CT, report="Different EHR text.")

        sync.sync_patient(self.patient)

        item.refresh_from_db()
        self.assertEqual(item.result_text, "Entered by the fellow.")

    def test_baseline_and_restaging_are_matched_separately(self):
        baseline, = self.checklist(Investigation.Kind.CAP_CT)
        restaging, = self.checklist(
            Investigation.Kind.CAP_CT, purpose=Investigation.Purpose.RESTAGING
        )
        self.add_result(Investigation.Kind.CAP_CT, report="Baseline scan.")
        self.add_result(
            Investigation.Kind.CAP_CT, report="Restaging scan.",
            purpose=Investigation.Purpose.RESTAGING,
        )

        sync.sync_patient(self.patient)

        baseline.refresh_from_db()
        restaging.refresh_from_db()
        self.assertEqual(baseline.result_text, "Baseline scan.")
        self.assertEqual(restaging.result_text, "Restaging scan.")

    def test_the_sync_timestamp_is_recorded(self):
        self.assertIsNone(self.patient.ehr_synced_at)
        sync.sync_patient(self.patient)
        self.patient.refresh_from_db()
        self.assertIsNotNone(self.patient.ehr_synced_at)


class SyncNotificationTests(EHRTestCase):
    def test_the_team_is_emailed_when_the_last_result_arrives(self):
        self.checklist(Investigation.Kind.CAP_CT, Investigation.Kind.PELVIC_MRI)
        self.add_result(Investigation.Kind.CAP_CT)
        self.add_result(Investigation.Kind.PELVIC_MRI)

        outcome = sync.sync_patient(self.patient)

        self.assertTrue(outcome.notified)
        self.assertTrue(
            Notification.objects.filter(kind=Notification.Kind.WORKUP_READY).exists()
        )
        self.assertEqual(len(mail.outbox), 1)

    def test_no_email_while_anything_is_still_outstanding(self):
        self.checklist(Investigation.Kind.CAP_CT, Investigation.Kind.PELVIC_MRI)
        self.add_result(Investigation.Kind.CAP_CT)
        self.add_result(Investigation.Kind.PELVIC_MRI, status="PENDING", report=None)

        outcome = sync.sync_patient(self.patient)

        self.assertFalse(outcome.notified)
        self.assertEqual(mail.outbox, [])

    def test_running_the_sync_again_does_not_re_announce(self):
        """A polling job must not email the team once per pass."""
        self.checklist(Investigation.Kind.CAP_CT)
        self.add_result(Investigation.Kind.CAP_CT)

        sync.sync_patient(self.patient)
        self.assertEqual(len(mail.outbox), 1)

        sync.sync_patient(self.patient)
        sync.sync_patient(self.patient)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            Notification.objects.filter(kind=Notification.Kind.WORKUP_READY).count(), 1
        )

    def test_restaging_completion_emails_the_team(self):
        TreatmentCourse.objects.create(
            patient=self.patient, kind=TreatmentCourse.Kind.TNT,
            regimen="XELOX x 6", total_cycles=6, completed_cycles=6,
            start_date=timezone.localdate() - timedelta(days=90),
        )
        self.checklist(
            Investigation.Kind.CAP_CT, Investigation.Kind.PELVIC_MRI,
            purpose=Investigation.Purpose.RESTAGING,
        )
        self.add_result(
            Investigation.Kind.CAP_CT, report="Partial response.",
            purpose=Investigation.Purpose.RESTAGING,
        )
        self.add_result(
            Investigation.Kind.PELVIC_MRI, report="Tumour now 4 cm.",
            purpose=Investigation.Purpose.RESTAGING,
        )

        sync.sync_patient(self.patient)

        self.assertTrue(
            Notification.objects.filter(kind=Notification.Kind.RESTAGING_READY).exists()
        )


class MedicationSyncTests(EHRTestCase):
    def test_active_medications_are_pulled_onto_the_patient(self):
        self.add_medication("Warfarin", "Vitamin K antagonists", high_alert=1)
        self.add_medication("Amlodipine", "Calcium channel blocker")

        sync.sync_patient(self.patient)

        self.assertEqual(self.patient.medications.filter(active=True).count(), 2)
        warfarin = Medication.objects.get(drug_name="Warfarin")
        self.assertTrue(warfarin.high_alert)

    def test_a_drug_dropped_from_the_ehr_is_marked_stopped_not_deleted(self):
        self.add_medication("Warfarin", "Vitamin K antagonists")
        sync.sync_patient(self.patient)

        self.connection.execute("DELETE FROM ehr_medications WHERE drug_name = 'Warfarin'")
        self.connection.commit()
        sync.sync_patient(self.patient)

        warfarin = Medication.objects.get(drug_name="Warfarin")
        self.assertFalse(warfarin.active)

    def test_a_stopped_order_syncs_as_inactive(self):
        self.add_medication("Warfarin", "Vitamin K antagonists", status="stopped")
        sync.sync_patient(self.patient)
        self.assertFalse(Medication.objects.get(drug_name="Warfarin").active)

    def test_syncing_twice_does_not_duplicate_a_drug(self):
        self.add_medication("Warfarin", "Vitamin K antagonists")
        sync.sync_patient(self.patient)
        sync.sync_patient(self.patient)
        self.assertEqual(Medication.objects.filter(drug_name="Warfarin").count(), 1)


class EHRUnavailableTests(TestCase):
    def test_a_missing_ehr_raises_rather_than_failing_silently(self):
        with mock.patch.dict("os.environ", {"EHR_DATABASE": "/nonexistent/ehr.sqlite3"}):
            with self.assertRaises(source.EHRUnavailable):
                source.results_for("123")

    def test_the_patient_page_survives_an_unreachable_ehr(self):
        team = Team.objects.create(consultant="Dr. Test", specialty="Colorectal cancer")
        patient = Patient.objects.create(
            name="P", mrn="970099", date_of_birth=date(1960, 1, 1),
            diagnosis="Rectal cancer", specialty="COLORECTAL", team=team,
        )
        user = User.objects.create_user(
            "f1", password="x", role=User.Role.CONSULTANT, team=team
        )
        self.client.force_login(user)
        with mock.patch.dict("os.environ", {"EHR_DATABASE": "/nonexistent/ehr.sqlite3"}):
            response = self.client.post(
                f"/patients/{patient.pk}/ehr/sync/", follow=True
            )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "could not be reached")
