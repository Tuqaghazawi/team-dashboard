from datetime import date

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from patients.models import Patient
from teams.models import MDC, Team

from .models import MDCListing, suggested_mdc_for


class MDCMeetingDateTests(TestCase):
    """The 'next meeting date' calculation behind the pre-filled date."""

    def test_next_meeting_date_finds_the_coming_weekday(self):
        # Sarcoma meets on Sunday (weekday 6).
        sarcoma = MDC.objects.create(name="Sarcoma", meeting_weekday=6)
        # Thu 2026-08-06 -> the coming Sunday is 2026-08-09.
        self.assertEqual(
            sarcoma.next_meeting_date(on_or_after=date(2026, 8, 6)),
            date(2026, 8, 9),
        )

    def test_next_meeting_date_returns_today_when_today_is_meeting_day(self):
        breast = MDC.objects.create(name="Breast", meeting_weekday=2)
        wednesday = date(2026, 8, 5)
        self.assertEqual(breast.next_meeting_date(on_or_after=wednesday), wednesday)

    def test_mdc_without_a_fixed_day_has_no_next_meeting(self):
        ad_hoc = MDC.objects.create(name="Ad hoc", meeting_weekday=None)
        self.assertIsNone(ad_hoc.next_meeting_date())


class TriageSuggestionTests(TestCase):
    """Which MDC a specialty is steered towards."""

    def setUp(self):
        self.breast = MDC.objects.create(name="Breast", meeting_weekday=2)
        self.gi = MDC.objects.create(name="Gastrointestinal (GI)", meeting_weekday=0)

    def test_specialty_maps_to_its_usual_mdc(self):
        self.assertEqual(suggested_mdc_for("BREAST"), self.breast)
        self.assertEqual(suggested_mdc_for("COLORECTAL"), self.gi)
        self.assertEqual(suggested_mdc_for("HPB"), self.gi)

    def test_general_surgical_oncology_gets_no_suggestion(self):
        # Deliberate: these cases vary, so the coordinator must choose.
        self.assertIsNone(suggested_mdc_for("GENERAL"))


class AddListingViewTests(TestCase):
    def setUp(self):
        self.breast_mdc = MDC.objects.create(name="Breast", meeting_weekday=2)
        self.team = Team.objects.create(consultant="Dr. Alawneh", specialty="Thyroid and breast")
        self.other_team = Team.objects.create(consultant="Dr. Mureb", specialty="Colorectal cancer")

        self.patient = Patient.objects.create(
            name="Test Patient", mrn="99001", date_of_birth=date(1970, 1, 1),
            diagnosis="Breast carcinoma", specialty="BREAST", team=self.team,
        )
        self.coordinator = User.objects.create_user(
            username="coord", password="pw", role=User.Role.TEAM_COORDINATOR, team=self.team,
        )
        self.fellow = User.objects.create_user(
            username="fell", password="pw", role=User.Role.FELLOW, team=self.team,
        )
        self.url = reverse("mdc_add_listing", args=[self.patient.pk])

    def test_coordinator_can_add_a_patient_to_an_mdc_list(self):
        self.client.force_login(self.coordinator)
        response = self.client.post(
            self.url, {"mdc": self.breast_mdc.pk, "meeting_date": "2026-08-05"}
        )
        self.assertRedirects(response, reverse("patient_detail", args=[self.patient.pk]))
        listing = MDCListing.objects.get()
        self.assertEqual(listing.patient, self.patient)
        self.assertEqual(listing.mdc, self.breast_mdc)
        self.assertEqual(listing.meeting_date, date(2026, 8, 5))
        self.assertFalse(listing.presented)

    def test_form_presuggests_the_breast_mdc_and_its_next_meeting(self):
        self.client.force_login(self.coordinator)
        form = self.client.get(self.url).context["form"]
        self.assertEqual(form.fields["mdc"].initial, self.breast_mdc.pk)
        self.assertEqual(
            form.fields["meeting_date"].initial, self.breast_mdc.next_meeting_date()
        )

    def test_the_same_patient_cannot_be_listed_twice_for_one_meeting(self):
        MDCListing.objects.create(
            patient=self.patient, mdc=self.breast_mdc, meeting_date=date(2026, 8, 5)
        )
        self.client.force_login(self.coordinator)
        response = self.client.post(
            self.url, {"mdc": self.breast_mdc.pk, "meeting_date": "2026-08-05"}
        )
        self.assertEqual(response.status_code, 200)  # redisplayed with an error
        self.assertContains(response, "already on the Breast MDC list")
        self.assertEqual(MDCListing.objects.count(), 1)

    def test_a_fellow_may_not_add_patients_to_an_mdc_list(self):
        self.client.force_login(self.fellow)
        response = self.client.post(
            self.url, {"mdc": self.breast_mdc.pk, "meeting_date": "2026-08-05"}
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(MDCListing.objects.count(), 0)

    def test_a_coordinator_cannot_add_another_teams_patient(self):
        outsider = Patient.objects.create(
            name="Other Team Patient", mrn="99002", date_of_birth=date(1965, 5, 5),
            diagnosis="Rectal cancer", specialty="COLORECTAL", team=self.other_team,
        )
        self.client.force_login(self.coordinator)
        response = self.client.post(
            reverse("mdc_add_listing", args=[outsider.pk]),
            {"mdc": self.breast_mdc.pk, "meeting_date": "2026-08-05"},
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(MDCListing.objects.count(), 0)

    def test_logged_out_users_are_sent_to_the_login_page(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])
