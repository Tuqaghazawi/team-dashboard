from datetime import date
from unittest.mock import patch

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
        self.assertIsNone(ad_hoc.suggested_listing_date())

    def test_suggested_listing_date_skips_this_weeks_meeting(self):
        breast = MDC.objects.create(name="Breast", meeting_weekday=2)  # Wednesday
        # Listing on Monday 3 Aug must not land on Wednesday 5 Aug (2 days away);
        # it should be the following week's Wednesday, 12 Aug.
        with patch("teams.models.timezone.localdate", return_value=date(2026, 8, 3)):
            self.assertEqual(breast.suggested_listing_date(), date(2026, 8, 12))

    def test_suggested_listing_date_is_always_at_least_a_week_ahead(self):
        sarcoma = MDC.objects.create(name="Sarcoma", meeting_weekday=6)  # Sunday
        # Thursday 6 Aug -> not the Sunday 3 days away, but the one after.
        with patch("teams.models.timezone.localdate", return_value=date(2026, 8, 6)):
            suggested = sarcoma.suggested_listing_date()
        self.assertEqual(suggested, date(2026, 8, 16))
        self.assertGreaterEqual((suggested - date(2026, 8, 6)).days, 7)


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
            form.fields["meeting_date"].initial, self.breast_mdc.suggested_listing_date()
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


class SlideDeckTests(TestCase):
    """The generated deck must carry the fields the room asks for."""

    def setUp(self):
        from patients.models import Investigation, Patient

        self.team = Team.objects.create(consultant="Dr. Amro Mureb", specialty="Colorectal cancer")
        self.mdc = MDC.objects.create(name="Gastrointestinal (GI)", meeting_weekday=1)
        self.patient = Patient.objects.create(
            name="Test Case", mrn="920001", date_of_birth=date(1955, 3, 2),
            diagnosis="Mid rectal cancer", specialty="COLORECTAL", team=self.team,
            sex="M", comorbidities="DM, PS 1", clinical_stage="T3N2",
            genetic_testing="Negative",
        )
        Investigation.objects.create(
            patient=self.patient, kind=Investigation.Kind.PELVIC_MRI,
            status=Investigation.Status.READY, result_text="T3N2, mesorectal fascia intact.",
        )
        self.listing = MDCListing.objects.create(
            patient=self.patient, mdc=self.mdc, meeting_date=date(2026, 9, 8),
            decision="For TNT", decision_category=MDCListing.Decision.TNT,
        )

    def _slide_text(self, stream):
        import re
        import zipfile
        from io import BytesIO

        archive = zipfile.ZipFile(BytesIO(stream.read()))
        names = [n for n in archive.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)]
        return "\n".join(
            " ".join(re.findall(r"<a:t>(.*?)</a:t>", archive.read(n).decode("utf8")))
            for n in sorted(names)
        )

    def test_mdc_deck_carries_name_mrn_genetics_results_and_decision(self):
        from mdc import slides

        text = self._slide_text(
            slides.build_mdc_deck(
                self.mdc.name, date(2026, 9, 8), [self.listing], presenter="Dr. Amro Mureb"
            )
        )
        self.assertIn("Test Case", text)
        self.assertIn("920001", text)
        self.assertIn("Genetics: Negative", text)
        self.assertIn("Mid rectal cancer", text)
        self.assertIn("T3N2", text)
        self.assertIn("mesorectal fascia intact", text)
        self.assertIn("For TNT", text)

    def test_an_unresulted_investigation_shows_as_outstanding_not_blank(self):
        from mdc import slides
        from patients.models import Investigation

        Investigation.objects.create(
            patient=self.patient, kind=Investigation.Kind.CAP_CT,
            status=Investigation.Status.ORDERED,
        )
        text = self._slide_text(
            slides.build_mdc_deck(self.mdc.name, date(2026, 9, 8), [self.listing])
        )
        self.assertIn("[ordered]", text)

    def test_guideline_evidence_goes_into_the_notes_not_onto_the_slide(self):
        from mdc import slides

        evidence = {self.patient.pk: "Guideline says consider TNT. Sources: Rectal, pages 3-9"}
        stream = slides.build_mdc_deck(
            self.mdc.name, date(2026, 9, 8), [self.listing], evidence=evidence
        )
        import zipfile
        from io import BytesIO

        archive = zipfile.ZipFile(BytesIO(stream.read()))
        notes = [n for n in archive.namelist() if "notesSlide" in n]
        self.assertTrue(notes, "expected a notes slide")
        notes_text = archive.read(notes[0]).decode("utf8")
        self.assertIn("Guideline says consider TNT", notes_text)

        slide_text = self._slide_text(
            slides.build_mdc_deck(
                self.mdc.name, date(2026, 9, 8), [self.listing], evidence=evidence
            )
        )
        self.assertNotIn("Guideline says consider TNT", slide_text)
