from datetime import date, timedelta

from django.core import mail
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from mdc.models import MDCListing
from notifications.models import Notification
from patients import flow
from patients.models import Investigation, Patient, SurgeryBooking, TreatmentCourse
from patients.workup import create_baseline_workup
from teams.models import MDC, FellowAssignment, Team


def make_patient(team, mrn="900001", specialty="COLORECTAL", **extra):
    return Patient.objects.create(
        name=extra.pop("name", "Test Patient"),
        mrn=mrn,
        date_of_birth=date(1960, 5, 1),
        diagnosis=extra.pop("diagnosis", "Rectal cancer"),
        specialty=specialty,
        team=team,
        **extra,
    )


class WorkupTests(TestCase):
    """The checklist that decides whether a patient can be presented."""

    def setUp(self):
        self.team = Team.objects.create(consultant="Dr. Test", specialty="Colorectal cancer")
        self.patient = make_patient(self.team)

    def test_baseline_checklist_matches_the_specialty(self):
        created = create_baseline_workup(self.patient)
        kinds = {i.kind for i in created}
        self.assertIn(Investigation.Kind.COLONOSCOPY, kinds)
        self.assertIn(Investigation.Kind.PELVIC_MRI, kinds)
        # Breast-only items must not appear on a colorectal checklist.
        self.assertNotIn(Investigation.Kind.MAMMOGRAM, kinds)

    def test_creating_the_checklist_twice_adds_nothing(self):
        create_baseline_workup(self.patient)
        before = self.patient.investigations.count()
        self.assertEqual(create_baseline_workup(self.patient), [])
        self.assertEqual(self.patient.investigations.count(), before)

    def test_patient_is_not_ready_until_every_required_result_is_back(self):
        create_baseline_workup(self.patient)
        self.assertFalse(self.patient.workup_ready)

        items = list(self.patient.investigations.all())
        for item in items[:-1]:
            item.mark_ready("Reported.")
        self.assertFalse(self.patient.workup_ready)

        items[-1].mark_ready("Reported.")
        self.assertTrue(Patient.objects.get(pk=self.patient.pk).workup_ready)

    def test_a_patient_with_no_checklist_is_not_ready(self):
        # Empty must not read as "everything is back".
        self.assertFalse(self.patient.workup_ready)

    def test_optional_items_do_not_hold_a_patient_back(self):
        create_baseline_workup(self.patient)
        extra = Investigation.objects.create(
            patient=self.patient, kind=Investigation.Kind.PET_CT, required=False
        )
        for item in self.patient.investigations.filter(required=True):
            item.mark_ready("Reported.")
        self.assertTrue(Patient.objects.get(pk=self.patient.pk).workup_ready)
        self.assertNotEqual(extra.status, Investigation.Status.READY)


class NotificationTests(TestCase):
    """Every step that must reach the team by email."""

    def setUp(self):
        self.team = Team.objects.create(consultant="Dr. Test", specialty="Colorectal cancer")
        self.coordinator = User.objects.create_user(
            "c1", email="c1@example.test", password="x",
            role=User.Role.TEAM_COORDINATOR, team=self.team,
        )
        self.consultant = User.objects.create_user(
            "s1", email="s1@example.test", password="x",
            role=User.Role.CONSULTANT, team=self.team,
        )
        self.fellow = User.objects.create_user(
            "f1", email="f1@example.test", password="x", role=User.Role.FELLOW,
        )
        today = timezone.localdate()
        FellowAssignment.objects.create(
            fellow=self.fellow, team=self.team,
            start_date=today - timedelta(days=10), end_date=today + timedelta(days=10),
        )
        self.patient = make_patient(self.team)

    def test_registration_notifies_coordinator_consultant_and_rotating_fellow(self):
        flow.on_patient_registered(self.patient)
        recipients = set(
            Notification.objects.filter(kind=Notification.Kind.NEW_PATIENT)
            .values_list("recipient__username", flat=True)
        )
        self.assertEqual(recipients, {"c1", "s1", "f1"})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.patient.name, mail.outbox[0].subject)

    def test_a_fellow_not_on_rotation_is_not_notified(self):
        FellowAssignment.objects.update(end_date=timezone.localdate() - timedelta(days=1))
        flow.on_patient_registered(self.patient)
        recipients = set(
            Notification.objects.values_list("recipient__username", flat=True)
        )
        self.assertNotIn("f1", recipients)

    def test_the_team_is_told_only_when_the_last_result_lands(self):
        create_baseline_workup(self.patient)
        items = list(self.patient.investigations.all())
        for item in items[:-1]:
            item.mark_ready("Reported.")
            flow.on_result_recorded(item)
        self.assertFalse(
            Notification.objects.filter(kind=Notification.Kind.WORKUP_READY).exists()
        )

        items[-1].mark_ready("Reported.")
        flow.on_result_recorded(items[-1])
        self.assertTrue(
            Notification.objects.filter(kind=Notification.Kind.WORKUP_READY).exists()
        )


class TreatmentAlertTests(TestCase):
    """The two emails around a NACT / TNT course."""

    def setUp(self):
        self.team = Team.objects.create(consultant="Dr. Test", specialty="Colorectal cancer")
        User.objects.create_user(
            "c1", email="c1@example.test", password="x",
            role=User.Role.TEAM_COORDINATOR, team=self.team,
        )
        self.patient = make_patient(self.team)
        self.course = TreatmentCourse.objects.create(
            patient=self.patient, kind=TreatmentCourse.Kind.TNT,
            regimen="XELOX x 6", total_cycles=6, completed_cycles=3,
            start_date=timezone.localdate() - timedelta(days=60),
        )

    def test_no_alert_before_the_last_cycle(self):
        self.assertEqual(flow.check_restaging_due(), [])
        self.assertFalse(
            Notification.objects.filter(kind=Notification.Kind.RESTAGING_DUE).exists()
        )

    def test_alert_fires_on_the_penultimate_cycle_and_opens_restaging(self):
        self.course.completed_cycles = 5
        self.course.save()
        alerted = flow.check_restaging_due()

        self.assertEqual(len(alerted), 1)
        self.assertTrue(
            Notification.objects.filter(kind=Notification.Kind.RESTAGING_DUE).exists()
        )
        self.assertTrue(
            self.patient.investigations.filter(
                purpose=Investigation.Purpose.RESTAGING
            ).exists()
        )

    def test_the_restaging_alert_is_never_sent_twice(self):
        self.course.completed_cycles = 5
        self.course.save()
        flow.check_restaging_due()
        self.assertEqual(flow.check_restaging_due(), [])
        self.assertEqual(
            Notification.objects.filter(kind=Notification.Kind.RESTAGING_DUE).count(), 1
        )

    def test_team_is_told_once_every_restaging_report_is_back(self):
        self.course.completed_cycles = 5
        self.course.save()
        flow.check_restaging_due()

        restaging = list(
            self.patient.investigations.filter(purpose=Investigation.Purpose.RESTAGING)
        )
        for item in restaging[:-1]:
            item.mark_ready("Reported.")
            flow.on_result_recorded(item)
        self.assertFalse(
            Notification.objects.filter(kind=Notification.Kind.RESTAGING_READY).exists()
        )

        restaging[-1].mark_ready("Reported.")
        flow.on_result_recorded(restaging[-1])
        self.assertTrue(
            Notification.objects.filter(kind=Notification.Kind.RESTAGING_READY).exists()
        )


class DecisionTests(TestCase):
    """Recording an MDC decision has to move the patient."""

    def setUp(self):
        self.team = Team.objects.create(consultant="Dr. Test", specialty="Colorectal cancer")
        self.mdc = MDC.objects.create(name="Gastrointestinal (GI)", meeting_weekday=1)
        self.patient = make_patient(self.team, stage=Patient.Stage.MDC)
        self.listing = MDCListing.objects.create(
            patient=self.patient, mdc=self.mdc, meeting_date=timezone.localdate()
        )

    def _decide(self, category):
        self.listing.decision_category = category
        self.listing.save()
        note = flow.apply_decision(self.listing)
        self.patient.refresh_from_db()
        return note

    def test_surgery_moves_the_patient_to_the_surgery_stage(self):
        self._decide(MDCListing.Decision.SURGERY)
        self.assertEqual(self.patient.stage, Patient.Stage.SURGERY)
        self.assertTrue(MDCListing.objects.get(pk=self.listing.pk).presented)

    def test_tnt_keeps_the_patient_on_the_team_list(self):
        self._decide(MDCListing.Decision.TNT)
        self.assertEqual(self.patient.stage, Patient.Stage.TNT)

    def test_referral_still_leaves_the_patient_visible_to_the_team(self):
        self._decide(MDCListing.Decision.REFER_MEDICAL)
        self.assertEqual(self.patient.stage, Patient.Stage.REFERRED)
        self.assertIn(self.patient, Patient.objects.filter(team=self.team))

    def test_further_workup_reopens_the_checklist(self):
        self._decide(MDCListing.Decision.MORE_WORKUP)
        self.assertEqual(self.patient.stage, Patient.Stage.WORKUP)
        self.assertTrue(self.patient.investigations.exists())


class PostOpTests(TestCase):
    """Post-op patients must be flagged until they are re-discussed."""

    def setUp(self):
        self.team = Team.objects.create(consultant="Dr. Test", specialty="Colorectal cancer")
        self.mdc = MDC.objects.create(name="Gastrointestinal (GI)", meeting_weekday=1)
        self.patient = make_patient(self.team, stage=Patient.Stage.SURGERY)
        self.booking = SurgeryBooking.objects.create(
            patient=self.patient, procedure="Low anterior resection",
            planned_date=timezone.localdate(),
        )

    def test_recording_surgery_flags_the_patient_for_post_op_mdc(self):
        self.booking.performed = True
        self.booking.performed_on = timezone.localdate()
        self.booking.save()
        flow.on_surgery_performed(self.booking)
        self.patient.refresh_from_db()

        self.assertEqual(self.patient.stage, Patient.Stage.POSTOP)
        self.assertTrue(self.patient.needs_postop_mdc)

    def test_the_flag_clears_once_a_post_op_listing_exists(self):
        self.patient.stage = Patient.Stage.POSTOP
        self.patient.save()
        self.assertTrue(self.patient.needs_postop_mdc)

        MDCListing.objects.create(
            patient=self.patient, mdc=self.mdc,
            meeting_date=timezone.localdate(), is_postop=True,
        )
        self.assertFalse(Patient.objects.get(pk=self.patient.pk).needs_postop_mdc)

    def test_an_ordinary_listing_does_not_clear_the_flag(self):
        self.patient.stage = Patient.Stage.POSTOP
        self.patient.save()
        MDCListing.objects.create(
            patient=self.patient, mdc=self.mdc, meeting_date=timezone.localdate()
        )
        self.assertTrue(Patient.objects.get(pk=self.patient.pk).needs_postop_mdc)


class VisibilityTests(TestCase):
    """Who can see whose patients."""

    def setUp(self):
        self.a = Team.objects.create(consultant="Dr. A", specialty="Colorectal cancer")
        self.b = Team.objects.create(consultant="Dr. B", specialty="Thyroid and breast")
        self.pa = make_patient(self.a, mrn="900010")
        self.pb = make_patient(self.b, mrn="900011", specialty="BREAST")

    def _visible(self, user):
        from patients.views import visible_patients

        return set(visible_patients(user))

    def test_chairman_sees_every_team(self):
        chair = User.objects.create_user("ch", password="x", role=User.Role.CHAIRMAN)
        self.assertEqual(self._visible(chair), {self.pa, self.pb})

    def test_consultant_sees_only_their_own_team(self):
        cons = User.objects.create_user(
            "co", password="x", role=User.Role.CONSULTANT, team=self.a
        )
        self.assertEqual(self._visible(cons), {self.pa})

    def test_fellow_sees_a_team_only_while_rotating_through_it(self):
        fellow = User.objects.create_user("fe", password="x", role=User.Role.FELLOW)
        self.assertEqual(self._visible(fellow), set())

        today = timezone.localdate()
        rotation = FellowAssignment.objects.create(
            fellow=fellow, team=self.a,
            start_date=today - timedelta(days=5), end_date=today + timedelta(days=5),
        )
        self.assertEqual(self._visible(fellow), {self.pa})

        rotation.end_date = today - timedelta(days=1)
        rotation.save()
        self.assertEqual(self._visible(fellow), set())


class RotationTests(TestCase):
    def test_quarters_are_three_month_blocks(self):
        self.assertEqual(
            FellowAssignment.current_quarter(date(2026, 8, 15)),
            (date(2026, 7, 1), date(2026, 9, 30)),
        )
        self.assertEqual(
            FellowAssignment.current_quarter(date(2026, 11, 2)),
            (date(2026, 10, 1), date(2026, 12, 31)),
        )
        self.assertEqual(
            FellowAssignment.current_quarter(date(2026, 1, 1)),
            (date(2026, 1, 1), date(2026, 3, 31)),
        )
