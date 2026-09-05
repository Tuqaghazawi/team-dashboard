from datetime import date, timedelta

from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from mdc.models import MDCListing
from notifications.models import Notification
from patients import flow
from patients.models import (
    Investigation,
    Medication,
    Patient,
    ReportExtraction,
    SurgeryBooking,
    TreatmentCourse,
)
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


class RestagingDoesNotAffectBaselineReadinessTests(TestCase):
    """Opening restaging must not make a completed baseline workup look unfinished."""

    def setUp(self):
        self.team = Team.objects.create(consultant="Dr. Test", specialty="Colorectal cancer")
        self.patient = make_patient(self.team, mrn="900050")
        create_baseline_workup(self.patient)
        for item in self.patient.investigations.all():
            item.mark_ready("Reported.")

    def test_baseline_stays_complete_after_restaging_is_opened(self):
        patient = Patient.objects.get(pk=self.patient.pk)
        ready, total = patient.workup_progress()
        self.assertEqual(ready, total)
        self.assertTrue(patient.workup_ready)

        from patients.workup import create_restaging_workup

        create_restaging_workup(self.patient)

        patient = Patient.objects.get(pk=self.patient.pk)
        ready_after, total_after = patient.workup_progress()
        self.assertEqual((ready_after, total_after), (ready, total))
        self.assertTrue(patient.workup_ready)
        self.assertEqual(patient.outstanding_investigations, [])


class PeriopCheckTests(TestCase):
    """A missing medication record must never read as 'nothing to hold'."""

    def setUp(self):
        self.team = Team.objects.create(consultant="Dr. Test", specialty="Colorectal cancer")
        self.patient = make_patient(self.team, mrn="900060")

    def test_a_patient_never_read_from_the_ehr_is_reported_as_unsynced(self):
        from ai.pharmacy import periop_api

        result = periop_api.periop_alerts(self.patient, "2026-10-01")
        self.assertFalse(result["synced"])
        self.assertEqual(result["alerts"], [])
        self.assertEqual(result["checked"], 0)

    def test_a_synced_patient_on_nothing_is_distinguishable_from_an_unread_one(self):
        from ai.pharmacy import periop_api

        self.patient.ehr_synced_at = timezone.now()
        self.patient.save()
        result = periop_api.periop_alerts(self.patient, "2026-10-01")
        self.assertTrue(result["synced"])
        self.assertEqual(result["checked"], 0)

    def test_a_named_drug_is_flagged_with_its_stop_date(self):
        from ai.pharmacy import periop_api

        self.patient.ehr_synced_at = timezone.now()
        self.patient.save()
        Medication.objects.create(
            patient=self.patient, drug_name="Warfarin",
            drug_class="Vitamin K antagonists", high_alert=True,
        )
        result = periop_api.periop_alerts(self.patient, date(2026, 10, 1))
        self.assertEqual(len(result["alerts"]), 1)
        alert = result["alerts"][0]
        self.assertEqual(alert["drug"], "Warfarin")
        self.assertEqual(alert["matched_by"], "name")
        self.assertIsNotNone(alert["stop_by"])

    def test_a_drug_the_guideline_never_names_is_caught_by_its_class(self):
        from ai.pharmacy import periop_api

        # Naproxen is an NSAID; the rule table names only ibuprofen, celecoxib
        # and diclofenac, so name-only matching would miss it entirely.
        self.patient.ehr_synced_at = timezone.now()
        self.patient.save()
        Medication.objects.create(
            patient=self.patient, drug_name="Naproxen", drug_class="NSAID"
        )
        result = periop_api.periop_alerts(self.patient, date(2026, 10, 1))
        self.assertEqual(len(result["alerts"]), 1)
        alert = result["alerts"][0]
        self.assertEqual(alert["matched_by"], "class")
        self.assertEqual(alert["guideline_action"], "DISCONTINUE")
        self.assertEqual(result["continued"], [])

    def test_an_unknown_drug_is_listed_as_unchecked_not_as_continue(self):
        from ai.pharmacy import periop_api

        self.patient.ehr_synced_at = timezone.now()
        self.patient.save()
        Medication.objects.create(
            patient=self.patient, drug_name="Investigational XYZ", drug_class="Unknown"
        )
        result = periop_api.periop_alerts(self.patient, date(2026, 10, 1))
        self.assertEqual(result["continued"], [])
        self.assertEqual(len(result["unmatched"]), 1)
        self.assertEqual(result["unmatched"][0]["drug"], "Investigational XYZ")

    def test_a_stopped_drug_is_not_checked(self):
        from ai.pharmacy import periop_api

        self.patient.ehr_synced_at = timezone.now()
        self.patient.save()
        Medication.objects.create(
            patient=self.patient, drug_name="Warfarin",
            drug_class="Vitamin K antagonists", active=False,
        )
        result = periop_api.periop_alerts(self.patient, date(2026, 10, 1))
        self.assertEqual(result["checked"], 0)
        self.assertEqual(result["alerts"], [])

    def test_the_page_says_no_record_rather_than_no_holds(self):
        booking = SurgeryBooking.objects.create(
            patient=self.patient, procedure="Anterior resection",
            planned_date=timezone.localdate(),
        )
        user = User.objects.create_user(
            "px", password="x", role=User.Role.CONSULTANT, team=self.team
        )
        self.client.force_login(user)
        response = self.client.get(
            f"/patients/{self.patient.pk}/surgery/{booking.pk}/periop/"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "never been read from the EHR")
        self.assertNotContains(response, "No medication holds flagged")


class ExtractionReviewTests(TestCase):
    """An extraction is a draft for a clinician, never a saved fact."""

    def setUp(self):
        self.team = Team.objects.create(consultant="Dr. Test", specialty="Thyroid and breast")
        self.patient = make_patient(self.team, mrn="900070", specialty="BREAST")
        self.investigation = Investigation.objects.create(
            patient=self.patient, kind=Investigation.Kind.PATHOLOGY,
            status=Investigation.Status.READY,
            result_text="IDC grade 3, 3 of 14 nodes positive, LVI present.",
        )
        self.user = User.objects.create_user(
            "fx", password="x", role=User.Role.FELLOW, team=self.team
        )
        self.client.force_login(self.user)

    def test_critical_fields_are_marked_and_sorted_first(self):
        from ai.extraction import review

        class FakeExtraction:
            def model_dump(self):
                return {
                    "histologic_type": "IDC",
                    "grade": "3",
                    "nodes_positive": 3,
                    "meta": {"needs_human_review": True, "missing_fields": ["margins"]},
                }

        rows, meta = review.flatten(FakeExtraction())
        self.assertTrue(meta["needs_human_review"])
        self.assertEqual(meta["missing_fields"], ["margins"])
        critical = [r["path"] for r in rows if r["critical"]]
        self.assertEqual(set(critical), {"grade", "nodes_positive"})
        # Critical rows come first so they cannot be scrolled past.
        self.assertTrue(rows[0]["critical"])
        self.assertFalse(rows[-1]["critical"])

    def test_a_failing_extractor_degrades_instead_of_breaking_the_page(self):
        from unittest.mock import patch

        from ai.extraction import review

        with patch("ai.extraction.review.extract", side_effect=review.ExtractionUnavailable("no key")):
            response = self.client.post(
                f"/patients/{self.patient.pk}/workup/{self.investigation.pk}/extract/",
                follow=True,
            )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "extractor is unavailable")
        self.assertFalse(ReportExtraction.objects.exists())

    def test_an_extraction_starts_pending_and_only_a_person_confirms_it(self):
        extraction = ReportExtraction.objects.create(
            investigation=self.investigation,
            raw_fields={
                "rows": [
                    {"path": "grade", "label": "Grade", "value": "3", "critical": True},
                    {"path": "nodes_positive", "label": "Nodes positive", "value": "", "critical": True},
                ],
                "meta": {"needs_human_review": True, "missing_fields": [], "evidence_spans": []},
            },
            needs_human_review=True,
        )
        self.assertFalse(extraction.is_confirmed)

        response = self.client.post(
            f"/patients/{self.patient.pk}/workup/{self.investigation.pk}/extract/review/",
            {"field__grade": "3", "field__nodes_positive": "3"},
        )
        self.assertEqual(response.status_code, 302)

        extraction.refresh_from_db()
        self.assertTrue(extraction.is_confirmed)
        self.assertEqual(extraction.reviewed_by, self.user)
        # The clinician's correction is kept separately from what the model said.
        self.assertEqual(extraction.confirmed_fields["nodes_positive"], "3")
        self.assertEqual(extraction.raw_fields["rows"][1]["value"], "")

    def test_rejecting_an_extraction_records_it_and_changes_nothing(self):
        ReportExtraction.objects.create(
            investigation=self.investigation,
            raw_fields={"rows": [], "meta": {}},
        )
        self.client.post(
            f"/patients/{self.patient.pk}/workup/{self.investigation.pk}/extract/review/",
            {"reject": "1"},
        )
        extraction = ReportExtraction.objects.get()
        self.assertEqual(extraction.status, ReportExtraction.Status.REJECTED)
        self.investigation.refresh_from_db()
        self.assertIn("grade 3", self.investigation.result_text)


class PrepClinicHandoverTests(TestCase):
    """The prep nurse works a handover queue, not the whole hospital."""

    def setUp(self):
        self.team = Team.objects.create(consultant="Dr. Test", specialty="Colorectal cancer")
        self.mdc = MDC.objects.create(name="Gastrointestinal (GI)", meeting_weekday=1)
        self.prep = User.objects.create_user(
            "p1", password="x", role=User.Role.PREP_COORDINATOR
        )
        self.handed_over = make_patient(self.team, mrn="950001", name="Handed Over")
        self.waiting = make_patient(self.team, mrn="950002", name="Still Waiting")
        MDCListing.objects.create(
            patient=self.handed_over, mdc=self.mdc,
            meeting_date=timezone.localdate() + timedelta(days=7),
        )

    def _visible(self):
        from patients.views import visible_patients

        return set(visible_patients(self.prep))

    def test_a_listed_patient_leaves_her_list(self):
        self.assertEqual(self._visible(), {self.waiting})

    def test_she_cannot_open_a_patient_she_has_handed_over(self):
        self.client.force_login(self.prep)
        self.assertEqual(
            self.client.get(f"/patients/{self.handed_over.pk}/").status_code, 404
        )
        self.assertEqual(
            self.client.get(f"/patients/{self.waiting.pk}/").status_code, 200
        )

    def test_her_reports_still_count_every_patient(self):
        from patients.views import reportable_patients

        # The working list shrinks; the monthly return must not.
        self.assertEqual(len(self._visible()), 1)
        self.assertEqual(reportable_patients(self.prep).count(), 2)

    def test_the_report_page_counts_handed_over_patients(self):
        self.client.force_login(self.prep)
        response = self.client.get(reverse("reports_home"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["periods"][1]["data"]["total"], 2)

    def test_the_chairman_still_sees_everybody(self):
        from patients.views import visible_patients

        chair = User.objects.create_user("ch", password="x", role=User.Role.CHAIRMAN)
        self.assertEqual(visible_patients(chair).count(), 2)


class CoordinatorRegistrationTests(TestCase):
    """A coordinator registers a walk-in onto her own team, and only hers."""

    def setUp(self):
        self.mine = Team.objects.create(consultant="Dr. Mine", specialty="Colorectal cancer")
        self.other = Team.objects.create(consultant="Dr. Other", specialty="Thyroid and breast")
        self.coordinator = User.objects.create_user(
            "co", password="x", role=User.Role.TEAM_COORDINATOR, team=self.mine
        )
        self.client.force_login(self.coordinator)

    def _payload(self, team, mrn="950010"):
        return {
            "name": "Walk In", "mrn": mrn, "date_of_birth": "1965-03-03",
            "diagnosis": "Rectal cancer", "specialty": "COLORECTAL", "team": team.pk,
        }

    def test_a_coordinator_may_open_the_registration_page(self):
        self.assertEqual(self.client.get(reverse("patient_register")).status_code, 200)

    def test_she_registers_onto_her_own_team(self):
        response = self.client.post(reverse("patient_register"), self._payload(self.mine))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Patient.objects.get(mrn="950010").team, self.mine)

    def test_she_cannot_register_onto_another_team(self):
        response = self.client.post(
            reverse("patient_register"), self._payload(self.other, mrn="950011")
        )
        self.assertEqual(response.status_code, 200)  # redisplayed with an error
        self.assertFalse(Patient.objects.filter(mrn="950011").exists())

    def test_only_her_own_team_is_offered(self):
        response = self.client.get(reverse("patient_register"))
        choices = list(response.context["form"].fields["team"].queryset)
        self.assertEqual(choices, [self.mine])

    def test_registering_notifies_her_team(self):
        User.objects.create_user(
            "cons", email="cons@example.test", password="x",
            role=User.Role.CONSULTANT, team=self.mine,
        )
        self.client.post(reverse("patient_register"), self._payload(self.mine, "950012"))
        self.assertTrue(
            Notification.objects.filter(
                kind=Notification.Kind.NEW_PATIENT, patient__mrn="950012"
            ).exists()
        )

    def test_a_fellow_still_may_not_register(self):
        fellow = User.objects.create_user("fe", password="x", role=User.Role.FELLOW)
        self.client.force_login(fellow)
        self.assertEqual(self.client.get(reverse("patient_register")).status_code, 403)

    def test_a_coordinator_with_no_team_is_told_rather_than_shown_a_broken_form(self):
        stray = User.objects.create_user(
            "st", password="x", role=User.Role.TEAM_COORDINATOR
        )
        self.client.force_login(stray)
        self.assertRedirects(
            self.client.get(reverse("patient_register")), reverse("dashboard")
        )
