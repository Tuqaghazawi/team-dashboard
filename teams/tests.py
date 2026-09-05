from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from mdc.models import MDCListing
from patients import categories
from patients.models import Investigation, Patient, SurgeryBooking
from patients.workup import create_baseline_workup

from .models import MDC, FellowAssignment, Team


def make_patient(team, mrn, **extra):
    return Patient.objects.create(
        name=extra.pop("name", f"Patient {mrn}"),
        mrn=mrn,
        date_of_birth=date(1960, 1, 1),
        diagnosis=extra.pop("diagnosis", "Rectal cancer"),
        specialty=extra.pop("specialty", "COLORECTAL"),
        team=team,
        **extra,
    )


class TeamPageAccessTests(TestCase):
    """The team page must never widen what somebody can already see."""

    def setUp(self):
        self.mine = Team.objects.create(consultant="Dr. Mine", specialty="Colorectal cancer")
        self.other = Team.objects.create(consultant="Dr. Other", specialty="Thyroid and breast")
        make_patient(self.mine, "940001")
        make_patient(self.other, "940002", specialty="BREAST")

        self.consultant = User.objects.create_user(
            "c1", password="x", role=User.Role.CONSULTANT, team=self.mine
        )
        self.chair = User.objects.create_user("ch", password="x", role=User.Role.CHAIRMAN)

    def test_a_consultant_opens_their_own_team(self):
        self.client.force_login(self.consultant)
        response = self.client.get(reverse("team_detail", args=[self.mine.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dr. Mine")

    def test_a_consultant_cannot_open_another_team(self):
        self.client.force_login(self.consultant)
        response = self.client.get(reverse("team_detail", args=[self.other.pk]))
        self.assertEqual(response.status_code, 403)

    def test_the_chairman_can_open_any_team(self):
        self.client.force_login(self.chair)
        self.assertEqual(
            self.client.get(reverse("team_detail", args=[self.other.pk])).status_code, 200
        )

    def test_team_home_sends_a_consultant_straight_to_their_team(self):
        self.client.force_login(self.consultant)
        response = self.client.get(reverse("team_home"))
        self.assertRedirects(response, reverse("team_detail", args=[self.mine.pk]))

    def test_team_home_lists_every_team_for_the_chairman(self):
        self.client.force_login(self.chair)
        response = self.client.get(reverse("team_home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dr. Mine")
        self.assertContains(response, "Dr. Other")

    def test_a_user_with_no_team_is_sent_back_to_the_dashboard(self):
        nobody = User.objects.create_user(
            "n1", password="x", role=User.Role.MDC_COORDINATOR
        )
        self.client.force_login(nobody)
        response = self.client.get(reverse("team_home"))
        self.assertRedirects(response, reverse("dashboard"))

    def test_the_page_only_counts_that_teams_patients(self):
        self.client.force_login(self.chair)
        response = self.client.get(reverse("team_detail", args=[self.mine.pk]))
        self.assertEqual(response.context["total"], 1)


class TeamPageRotationTests(TestCase):
    """A fellow reaches a team through a rotation, and only while it runs."""

    def setUp(self):
        self.team = Team.objects.create(consultant="Dr. Mine", specialty="Colorectal cancer")
        make_patient(self.team, "940010")
        self.fellow = User.objects.create_user("f1", password="x", role=User.Role.FELLOW)
        self.today = timezone.localdate()

    def test_a_rotating_fellow_is_taken_to_that_team(self):
        FellowAssignment.objects.create(
            fellow=self.fellow, team=self.team,
            start_date=self.today - timedelta(days=5),
            end_date=self.today + timedelta(days=5),
        )
        self.client.force_login(self.fellow)
        self.assertRedirects(
            self.client.get(reverse("team_home")),
            reverse("team_detail", args=[self.team.pk]),
        )

    def test_a_fellow_whose_rotation_ended_loses_the_page(self):
        FellowAssignment.objects.create(
            fellow=self.fellow, team=self.team,
            start_date=self.today - timedelta(days=100),
            end_date=self.today - timedelta(days=1),
        )
        self.client.force_login(self.fellow)
        self.assertEqual(
            self.client.get(reverse("team_detail", args=[self.team.pk])).status_code, 403
        )

    def test_the_page_shows_who_is_on_the_team_now(self):
        FellowAssignment.objects.create(
            fellow=self.fellow, team=self.team,
            start_date=self.today - timedelta(days=5),
            end_date=self.today + timedelta(days=5),
        )
        User.objects.create_user(
            "co", password="x", first_name="Suha", last_name="Coordinator",
            role=User.Role.TEAM_COORDINATOR, team=self.team,
        )
        members = categories.team_members(self.team)
        self.assertEqual(len(members["rotations"]), 1)
        self.assertEqual(members["coordinators"][0].first_name, "Suha")

    def test_an_expired_rotation_is_not_shown_as_a_current_member(self):
        FellowAssignment.objects.create(
            fellow=self.fellow, team=self.team,
            start_date=self.today - timedelta(days=100),
            end_date=self.today - timedelta(days=1),
        )
        self.assertEqual(categories.team_members(self.team)["rotations"], [])


class TeamAttentionTests(TestCase):
    """The two gaps the team page exists to catch."""

    def setUp(self):
        self.team = Team.objects.create(consultant="Dr. Mine", specialty="Colorectal cancer")
        self.mdc = MDC.objects.create(name="Gastrointestinal (GI)", meeting_weekday=1)
        self.visible = Patient.objects.filter(team=self.team)

    def _ready_patient(self, mrn):
        patient = make_patient(self.team, mrn, stage=Patient.Stage.WORKUP)
        create_baseline_workup(patient)
        for item in patient.investigations.all():
            item.mark_ready("Reported.")
        return patient

    def test_a_ready_patient_with_no_listing_is_flagged(self):
        patient = self._ready_patient("940020")
        self.assertIn(patient, categories.ready_but_unlisted(self.visible))

    def test_a_patient_still_in_workup_is_not_flagged(self):
        patient = make_patient(self.team, "940021", stage=Patient.Stage.WORKUP)
        create_baseline_workup(patient)
        self.assertNotIn(patient, categories.ready_but_unlisted(self.visible))

    def test_listing_a_ready_patient_clears_the_flag(self):
        patient = self._ready_patient("940022")
        MDCListing.objects.create(
            patient=patient, mdc=self.mdc,
            meeting_date=timezone.localdate() + timedelta(days=7),
        )
        self.assertNotIn(patient, categories.ready_but_unlisted(self.visible))

    def test_an_already_discussed_listing_does_not_clear_the_flag(self):
        # Discussed last week and still sitting in workup means nothing is booked.
        patient = self._ready_patient("940023")
        MDCListing.objects.create(
            patient=patient, mdc=self.mdc,
            meeting_date=timezone.localdate() - timedelta(days=7), presented=True,
        )
        self.assertIn(patient, categories.ready_but_unlisted(self.visible))

    def test_a_surgical_patient_with_no_booking_is_flagged(self):
        patient = make_patient(self.team, "940030", stage=Patient.Stage.SURGERY)
        self.assertIn(patient, categories.decided_for_surgery_unscheduled(self.visible))

    def test_booking_theatre_clears_the_flag(self):
        patient = make_patient(self.team, "940031", stage=Patient.Stage.SURGERY)
        SurgeryBooking.objects.create(
            patient=patient, procedure="Anterior resection",
            planned_date=timezone.localdate() + timedelta(days=7),
        )
        self.assertNotIn(patient, categories.decided_for_surgery_unscheduled(self.visible))

    def test_a_completed_operation_does_not_count_as_scheduled(self):
        patient = make_patient(self.team, "940032", stage=Patient.Stage.SURGERY)
        SurgeryBooking.objects.create(
            patient=patient, procedure="Anterior resection",
            planned_date=timezone.localdate() - timedelta(days=30),
            performed=True, performed_on=timezone.localdate() - timedelta(days=30),
        )
        self.assertIn(patient, categories.decided_for_surgery_unscheduled(self.visible))
