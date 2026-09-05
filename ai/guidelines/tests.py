"""Tests for the guideline brain's question-building and coverage checks.

These cover the part that was silently wrong: what the brain is *asked*. The
retrieval and the model call are not exercised here — they need an API key.
"""

from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone

from ai.guidelines import suggest
from patients.models import Investigation, Patient, SurgeryBooking, TreatmentCourse
from teams.models import Team


class CaseBlockTests(TestCase):
    """The case must say what has already happened, not just the diagnosis."""

    def setUp(self):
        self.team = Team.objects.create(consultant="Dr. Test", specialty="Colorectal cancer")
        self.patient = Patient.objects.create(
            name="Test", mrn="960001", date_of_birth=date(1950, 1, 1),
            diagnosis="Mid rectal cancer", specialty="COLORECTAL", team=self.team,
            sex="M", clinical_stage="T3N2",
        )

    def test_treatment_already_given_is_in_the_case(self):
        TreatmentCourse.objects.create(
            patient=self.patient, kind=TreatmentCourse.Kind.TNT,
            regimen="XELOX x 6", total_cycles=6, completed_cycles=5,
            start_date=timezone.localdate() - timedelta(days=90),
        )
        case = suggest._case_block(self.patient)
        self.assertIn("Already done", case)
        self.assertIn("5 of 6 cycles", case)
        self.assertIn("in progress", case)

    def test_a_completed_course_is_marked_completed(self):
        TreatmentCourse.objects.create(
            patient=self.patient, kind=TreatmentCourse.Kind.NACT,
            regimen="AC-T", total_cycles=4, completed_cycles=4,
            start_date=timezone.localdate() - timedelta(days=120),
        )
        self.assertIn("completed", suggest._case_block(self.patient))

    def test_surgery_already_performed_is_in_the_case(self):
        SurgeryBooking.objects.create(
            patient=self.patient, procedure="Total gastrectomy",
            planned_date=timezone.localdate() - timedelta(days=10),
            performed=True, performed_on=timezone.localdate() - timedelta(days=10),
            final_pathology="ypT2N1a, negative margins.",
        )
        case = suggest._case_block(self.patient)
        self.assertIn("Has already undergone Total gastrectomy", case)
        self.assertIn("ypT2N1a", case)

    def test_a_planned_operation_is_not_reported_as_done(self):
        SurgeryBooking.objects.create(
            patient=self.patient, procedure="Anterior resection",
            planned_date=timezone.localdate() + timedelta(days=10),
        )
        self.assertNotIn("already undergone", suggest._case_block(self.patient))

    def test_baseline_and_restaging_findings_are_labelled_separately(self):
        Investigation.objects.create(
            patient=self.patient, kind=Investigation.Kind.PELVIC_MRI,
            purpose=Investigation.Purpose.BASELINE,
            status=Investigation.Status.READY, result_text="T3N2 at baseline.",
        )
        Investigation.objects.create(
            patient=self.patient, kind=Investigation.Kind.PELVIC_MRI,
            purpose=Investigation.Purpose.RESTAGING,
            status=Investigation.Status.READY, result_text="Partial response.",
        )
        case = suggest._case_block(self.patient)
        self.assertIn("Baseline investigations", case)
        self.assertIn("Restaging after treatment", case)
        self.assertLess(case.index("Baseline"), case.index("Restaging"))

    def test_an_unresulted_investigation_is_not_quoted_as_a_finding(self):
        Investigation.objects.create(
            patient=self.patient, kind=Investigation.Kind.PET_CT,
            status=Investigation.Status.ORDERED,
        )
        self.assertNotIn("PET", suggest._case_block(self.patient))


class DecisionAskedTests(TestCase):
    """The question must name the decision the MDC is actually facing."""

    def setUp(self):
        self.team = Team.objects.create(consultant="Dr. Test", specialty="Colorectal cancer")

    def _patient(self, stage, mrn):
        return Patient.objects.create(
            name="Test", mrn=mrn, date_of_birth=date(1950, 1, 1),
            diagnosis="Rectal cancer", specialty="COLORECTAL", team=self.team,
            stage=stage,
        )

    def test_a_post_op_patient_is_asked_about_the_adjuvant_plan(self):
        asked = suggest.decision_asked(self._patient(Patient.Stage.POSTOP, "960010"))
        self.assertIn("POST-OPERATIVE", asked)
        self.assertIn("adjuvant", asked)

    def test_a_patient_on_tnt_is_asked_what_comes_after_it(self):
        asked = suggest.decision_asked(self._patient(Patient.Stage.TNT, "960011"))
        self.assertIn("PART-WAY THROUGH", asked)

    def test_a_new_patient_is_asked_about_primary_treatment(self):
        asked = suggest.decision_asked(self._patient(Patient.Stage.MDC, "960012"))
        self.assertIn("primary treatment", asked)


class CoverageTests(TestCase):
    """A vector search always returns something, even for an unindexed disease."""

    def setUp(self):
        self.team = Team.objects.create(consultant="Dr. Test", specialty="General surgical oncology")

    def _patient(self, specialty, mrn):
        return Patient.objects.create(
            name="Test", mrn=mrn, date_of_birth=date(1970, 1, 1),
            diagnosis="Something", specialty=specialty, team=self.team,
        )

    def test_a_covered_specialty_is_reported_as_covered(self):
        coverage = suggest.coverage_for(self._patient("COLORECTAL", "960020"))
        self.assertTrue(coverage["covered"])
        self.assertEqual(coverage["expected"], ["Colon", "Rectal"])

    def test_sarcoma_is_reported_as_uncovered(self):
        # There is no sarcoma guideline in the index, so retrieval would return
        # the nearest chunks from an unrelated cancer.
        coverage = suggest.coverage_for(self._patient("SARCOMA", "960021"))
        self.assertFalse(coverage["covered"])
        self.assertEqual(coverage["expected"], [])

    def test_the_indexed_guidelines_are_listed_for_the_warning(self):
        coverage = suggest.coverage_for(self._patient("SARCOMA", "960022"))
        self.assertIn("Breast", coverage["indexed"])
        self.assertIn("Pancreatic", coverage["indexed"])
        self.assertNotIn("Sarcoma", coverage["indexed"])
