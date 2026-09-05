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

    KHCC = ["Breast", "Colon", "Gastric", "Pancreatic", "Rectal", "Thyroid"]

    def setUp(self):
        self.team = Team.objects.create(
            consultant="Dr. Test", specialty="General surgical oncology"
        )
        # Pin what the index contains, so these tests do not depend on ChromaDB.
        suggest._indexed_cache = list(self.KHCC)
        self.addCleanup(setattr, suggest, "_indexed_cache", None)

    def _patient(self, specialty, mrn, diagnosis="Something"):
        return Patient.objects.create(
            name="Test", mrn=mrn, date_of_birth=date(1970, 1, 1),
            diagnosis=diagnosis, specialty=specialty, team=self.team,
        )

    def test_the_topic_comes_from_the_diagnosis_not_the_specialty(self):
        # "Upper GI" covers gastric and oesophageal; only the diagnosis says which.
        patient = self._patient("UPPER_GI", "960020", "Distal oesophageal cancer")
        self.assertEqual(suggest.topics_for(patient), ["esophageal"])

    def test_a_rectal_diagnosis_matches_the_rectal_guideline(self):
        coverage = suggest.coverage_for(
            self._patient("COLORECTAL", "960021", "Low rectal cancer")
        )
        self.assertTrue(coverage["covered"])
        self.assertEqual(coverage["matched"], ["Rectal"])

    def test_a_colon_diagnosis_matches_the_colon_guideline(self):
        coverage = suggest.coverage_for(
            self._patient("COLORECTAL", "960022", "Sigmoid colon cancer")
        )
        self.assertEqual(coverage["matched"], ["Colon"])

    def test_oesophageal_is_uncovered_even_though_gastric_is_indexed(self):
        # The bug this guards: treating "Upper GI" as covered because gastric is.
        coverage = suggest.coverage_for(
            self._patient("UPPER_GI", "960023", "Distal oesophageal cancer")
        )
        self.assertFalse(coverage["covered"])
        self.assertEqual(coverage["matched"], [])

    def test_sarcoma_is_reported_as_uncovered(self):
        coverage = suggest.coverage_for(
            self._patient("SARCOMA", "960024", "Soft tissue sarcoma, thigh")
        )
        self.assertFalse(coverage["covered"])

    def test_biliary_is_uncovered_even_though_pancreatic_is_indexed(self):
        coverage = suggest.coverage_for(
            self._patient("HPB", "960025", "Hilar cholangiocarcinoma")
        )
        self.assertFalse(coverage["covered"])

    def test_adding_a_guideline_makes_the_matching_patient_covered(self):
        """Coverage reads the index, so add_guideline widens it with no code change."""
        patient = self._patient("UPPER_GI", "960026", "Distal oesophageal cancer")
        self.assertFalse(suggest.coverage_for(patient)["covered"])

        suggest._indexed_cache = self.KHCC + ["Esophageal (NCCN)"]
        coverage = suggest.coverage_for(patient)
        self.assertTrue(coverage["covered"])
        self.assertEqual(coverage["matched"], ["Esophageal (NCCN)"])

    def test_the_indexed_guidelines_are_listed_for_the_warning(self):
        coverage = suggest.coverage_for(
            self._patient("SARCOMA", "960027", "Sarcoma of thigh")
        )
        self.assertIn("Breast", coverage["indexed"])
        self.assertNotIn("Sarcoma", coverage["indexed"])


class ScopedRetrievalTests(TestCase):
    """Coverage gates retrieval, rather than being a warning after the fact."""

    KHCC = ["Breast", "Colon", "Gastric", "Pancreatic", "Rectal", "Thyroid"]

    def setUp(self):
        self.team = Team.objects.create(consultant="Dr. Test", specialty="General")
        suggest._indexed_cache = list(self.KHCC)
        self.addCleanup(setattr, suggest, "_indexed_cache", None)

    def _patient(self, diagnosis, specialty, mrn):
        return Patient.objects.create(
            name="Test", mrn=mrn, date_of_birth=date(1960, 1, 1),
            diagnosis=diagnosis, specialty=specialty, team=self.team,
            clinical_stage="T2N0",
        )

    def test_an_uncovered_disease_refuses_without_calling_the_model(self):
        """No guideline covers it, so there is nothing to ground an answer in."""
        from unittest import mock

        patient = self._patient("Soft tissue sarcoma, thigh", "SARCOMA", "961000")
        with mock.patch.object(suggest, "_rag") as rag:
            result = suggest.suggest_decision(patient)

        self.assertTrue(result["refused"])
        self.assertEqual(result["citations"], [])
        rag.assert_not_called()

    def test_the_near_miss_case_refuses_too(self):
        """Oesophageal shares a specialty with gastric and sits next to it in
        embedding space. Answering it from the gastric guideline is the failure
        this gate exists to stop."""
        from unittest import mock

        patient = self._patient("Distal oesophageal cancer", "UPPER_GI", "961001")
        with mock.patch.object(suggest, "_rag") as rag:
            result = suggest.suggest_decision(patient)

        self.assertTrue(result["refused"])
        rag.assert_not_called()

    def test_a_covered_disease_retrieves_only_from_its_own_guidelines(self):
        from unittest import mock

        patient = self._patient("Ascending colon cancer", "COLORECTAL", "961002")
        fake = mock.MagicMock()
        fake.embed.return_value = [[0.0]]
        collection = fake.chroma.get_collection.return_value
        collection.query.return_value = {
            "documents": [["Colon guidance."]],
            "metadatas": [[{"cancer": "Colon", "pages": "113-176"}]],
        }
        fake.build_context.return_value = "context"
        fake.client.chat.completions.create.return_value.choices = [
            mock.MagicMock(message=mock.MagicMock(content="Resect it."))
        ]

        with mock.patch.object(suggest, "_rag", return_value=fake):
            result = suggest.suggest_decision(patient)

        # The search was restricted to the guidelines that cover colon cancer.
        where = collection.query.call_args.kwargs["where"]
        self.assertEqual(where, {"cancer": {"$in": ["Colon"]}})
        self.assertFalse(result["refused"])
        self.assertEqual(result["citations"], ["Colon, pages 113-176"])

    def test_a_refusal_carries_no_citations_and_no_slide_note(self):
        from mdc.models import GuidelineSuggestion

        suggestion = GuidelineSuggestion(
            patient=self._patient("Hepatocellular carcinoma", "HPB", "961003"),
            kind=GuidelineSuggestion.Kind.DECISION,
            question="q", answer="Not found in the provided guidelines.",
            citations="", refused=True,
        )
        self.assertEqual(suggestion.citation_list, [])
        self.assertEqual(suggestion.as_slide_note(), "")
