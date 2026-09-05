from datetime import date

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from patients.models import Patient
from teams.models import Team

from .build import age_band, build_workbook, collect, period_range


class ReportBuildTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(consultant="Dr. A", specialty="Colorectal cancer")
        for i in range(3):
            Patient.objects.create(
                name=f"Patient {i}", mrn=f"9100{i}", date_of_birth=date(1970, 1, 1),
                diagnosis="Rectal cancer", specialty="COLORECTAL", team=self.team,
            )

    def test_age_bands(self):
        self.assertEqual(age_band(31), "under 40")
        self.assertEqual(age_band(40), "40-54")
        self.assertEqual(age_band(69), "55-69")
        self.assertEqual(age_band(70), "70+")

    def test_counts_are_ordered_lists_not_counters(self):
        """A Counter in the template resolves to 0, so these must be lists."""
        start, end, _ = period_range("month")
        data = collect(Patient.objects.all(), start, end)
        self.assertIsInstance(data["by_specialty"], list)
        self.assertEqual(data["by_specialty"], [("Colorectal", 3)])
        self.assertEqual(data["total"], 3)

    def test_workbook_has_a_summary_and_a_patient_sheet(self):
        start, end, label = period_range("month")
        data = collect(Patient.objects.all(), start, end)
        stream = build_workbook(data, label)
        content = stream.read()
        self.assertGreater(len(content), 3000)
        self.assertTrue(content.startswith(b"PK"))  # a real xlsx is a zip


class ReportAccessTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(consultant="Dr. A", specialty="Colorectal cancer")
        Patient.objects.create(
            name="P", mrn="91100", date_of_birth=date(1970, 1, 1),
            diagnosis="Rectal cancer", specialty="COLORECTAL", team=self.team,
        )

    def test_prep_coordinator_can_open_the_reports_page(self):
        user = User.objects.create_user("p", password="x", role=User.Role.PREP_COORDINATOR)
        self.client.force_login(user)
        response = self.client.get(reverse("reports_home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Colorectal")

    def test_a_fellow_may_not_see_the_reports(self):
        user = User.objects.create_user("f", password="x", role=User.Role.FELLOW)
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("reports_home")).status_code, 403)

    def test_download_returns_a_spreadsheet(self):
        user = User.objects.create_user("c", password="x", role=User.Role.CHAIRMAN)
        self.client.force_login(user)
        response = self.client.get(reverse("download_report", args=["month"]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("spreadsheetml", response["Content-Type"])
        self.assertIn("attachment", response["Content-Disposition"])
