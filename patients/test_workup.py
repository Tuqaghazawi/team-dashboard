"""The per-diagnosis workup checklists and their conditional rules.

Clinical source: PRD Appendix A, signed off 5 September 2026.
"""

from datetime import date

from django.test import TestCase
from django.utils import timezone

from patients.diagnosis import Group, group_for
from patients.models import Investigation, Patient
from patients.workup import baseline_items, create_baseline_workup, restaging_items
from teams.models import Team

K = Investigation.Kind


def kinds(items):
    return {item.kind for item in items}


class DiagnosisGroupTests(TestCase):
    """Specialty is too coarse; the diagnosis decides."""

    def setUp(self):
        self.team = Team.objects.create(consultant="Dr. Test", specialty="General")

    def patient(self, diagnosis, specialty="GENERAL", mrn="980000", **extra):
        return Patient.objects.create(
            name="Test", mrn=mrn, date_of_birth=date(1960, 1, 1),
            diagnosis=diagnosis, specialty=specialty, team=self.team, **extra,
        )

    def test_colon_and_rectum_separate_despite_one_specialty(self):
        colon = self.patient("Ascending colon cancer", "COLORECTAL", "980001")
        rectum = self.patient("Low rectal cancer", "COLORECTAL", "980002")
        self.assertEqual(group_for(colon), Group.COLON)
        self.assertEqual(group_for(rectum), Group.RECTUM)

    def test_rectosigmoid_reads_as_rectum_not_colon(self):
        # "sigmoid" appears inside "rectosigmoid"; the rectal rule must win.
        patient = self.patient("Rectosigmoid junction tumour", "COLORECTAL", "980003")
        self.assertEqual(group_for(patient), Group.RECTUM)

    def test_oesophageal_and_gastric_separate_despite_one_specialty(self):
        gastric = self.patient("Gastric cancer", "UPPER_GI", "980004")
        oeso = self.patient("Distal oesophageal cancer", "UPPER_GI", "980005")
        self.assertEqual(group_for(gastric), Group.GASTRIC)
        self.assertEqual(group_for(oeso), Group.ESOPHAGEAL)

    def test_hpb_splits_into_pancreas_biliary_and_liver(self):
        self.assertEqual(
            group_for(self.patient("Pancreatic head mass", "HPB", "980006")), Group.PANCREAS
        )
        self.assertEqual(
            group_for(self.patient("Hilar cholangiocarcinoma", "HPB", "980007")), Group.BILIARY
        )
        self.assertEqual(
            group_for(self.patient("Hepatocellular carcinoma", "HPB", "980008")), Group.LIVER
        )

    def test_an_unrecognised_diagnosis_falls_back_to_the_specialty(self):
        patient = self.patient("Unusual presentation", "BREAST", "980009")
        self.assertEqual(group_for(patient), Group.BREAST)


class UniversalItemTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(consultant="Dr. Test", specialty="General")

    def patient(self, mrn="980100", **extra):
        return Patient.objects.create(
            name="Test", mrn=mrn, date_of_birth=extra.pop("dob", date(1960, 1, 1)),
            diagnosis=extra.pop("diagnosis", "Ascending colon cancer"),
            specialty=extra.pop("specialty", "COLORECTAL"), team=self.team, **extra,
        )

    def test_every_patient_gets_the_universal_baseline(self):
        items = kinds(baseline_items(self.patient()))
        for kind in (K.PATHOLOGY, K.PATH_REVIEW, K.CBC, K.CMP,
                     K.PERFORMANCE_STATUS, K.PRIOR_IMAGING):
            self.assertIn(kind, items)

    def test_fertility_counselling_for_a_woman_under_40(self):
        young = self.patient(
            mrn="980101", sex="F", dob=date(timezone.localdate().year - 32, 1, 1)
        )
        self.assertIn(K.FERTILITY, kinds(baseline_items(young)))

    def test_no_fertility_counselling_for_a_woman_over_40(self):
        older = self.patient(
            mrn="980102", sex="F", dob=date(timezone.localdate().year - 55, 1, 1)
        )
        self.assertNotIn(K.FERTILITY, kinds(baseline_items(older)))

    def test_no_fertility_counselling_for_a_man(self):
        man = self.patient(
            mrn="980103", sex="M", dob=date(timezone.localdate().year - 30, 1, 1)
        )
        self.assertNotIn(K.FERTILITY, kinds(baseline_items(man)))


class BreastStagingTests(TestCase):
    """Early breast cancer gets abdomen US + CXR; advanced gets CAP CT."""

    def setUp(self):
        self.team = Team.objects.create(consultant="Dr. Test", specialty="Breast")

    def patient(self, stage, mrn, **extra):
        return Patient.objects.create(
            name="Test", mrn=mrn, date_of_birth=date(1955, 1, 1),
            diagnosis="Right breast cancer", specialty="BREAST", team=self.team,
            sex="F", clinical_stage=stage, **extra,
        )

    def test_early_gets_abdomen_us_and_cxr_instead_of_cap_ct(self):
        items = kinds(baseline_items(self.patient("cT2N0", "980200")))
        self.assertIn(K.ABDOMEN_US, items)
        self.assertIn(K.CXR, items)
        self.assertNotIn(K.CAP_CT, items)
        self.assertNotIn(K.BONE_SCAN, items)

    def test_node_positive_gets_cap_ct_instead(self):
        items = kinds(baseline_items(self.patient("cT2N+", "980201")))
        self.assertIn(K.CAP_CT, items)
        self.assertIn(K.BONE_SCAN, items)
        self.assertNotIn(K.ABDOMEN_US, items)

    def test_t4_reads_as_locally_advanced(self):
        self.assertIn(K.CAP_CT, kinds(baseline_items(self.patient("cT4N0", "980202"))))

    def test_t3_reads_as_locally_advanced(self):
        self.assertIn(K.CAP_CT, kinds(baseline_items(self.patient("cT3N0", "980203"))))

    def test_an_unrecorded_stage_gets_the_fuller_staging(self):
        """Under-staging is the worse error, so an unknown stage gets CAP CT."""
        items = kinds(baseline_items(self.patient("", "980204")))
        self.assertIn(K.CAP_CT, items)
        self.assertNotIn(K.ABDOMEN_US, items)

    def test_the_reason_says_the_stage_was_not_recorded(self):
        patient = self.patient("", "980205")
        item = next(i for i in baseline_items(patient) if i.kind == K.CAP_CT)
        self.assertIn("not recorded", item.why(patient))

    def test_breast_always_gets_receptor_biomarkers(self):
        self.assertIn(K.BIOMARKERS, kinds(baseline_items(self.patient("cT2N0", "980206"))))


class BreastGeneticsTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(consultant="Dr. Test", specialty="Breast")

    def patient(self, age, mrn, family_history=""):
        return Patient.objects.create(
            name="Test", mrn=mrn,
            date_of_birth=date(timezone.localdate().year - age, 1, 1),
            diagnosis="Right breast cancer", specialty="BREAST", team=self.team,
            sex="F", clinical_stage="cT2N0", family_history=family_history,
        )

    def test_offered_under_65(self):
        self.assertIn(K.GENETICS, kinds(baseline_items(self.patient(48, "980300"))))

    def test_not_offered_over_65_without_a_family_history(self):
        self.assertNotIn(K.GENETICS, kinds(baseline_items(self.patient(72, "980301"))))

    def test_offered_over_65_with_a_family_history(self):
        patient = self.patient(72, "980302", family_history="Sister, breast cancer at 50.")
        self.assertIn(K.GENETICS, kinds(baseline_items(patient)))


class PerDiagnosisTests(TestCase):
    """Each group gets its own investigations, and not another group's."""

    def setUp(self):
        self.team = Team.objects.create(consultant="Dr. Test", specialty="General")

    def patient(self, diagnosis, specialty, mrn, stage="T2N0"):
        return Patient.objects.create(
            name="Test", mrn=mrn, date_of_birth=date(1960, 1, 1),
            diagnosis=diagnosis, specialty=specialty, team=self.team,
            clinical_stage=stage,
        )

    def test_rectum_gets_pelvic_mri_and_dre(self):
        items = kinds(baseline_items(self.patient("Low rectal cancer", "COLORECTAL", "980400")))
        self.assertIn(K.PELVIC_MRI, items)
        self.assertIn(K.DRE, items)

    def test_colon_gets_neither_pelvic_mri_nor_dre(self):
        items = kinds(baseline_items(self.patient("Ascending colon cancer", "COLORECTAL", "980401")))
        self.assertNotIn(K.PELVIC_MRI, items)
        self.assertNotIn(K.DRE, items)
        self.assertIn(K.MMR_MSI, items)

    def test_ras_braf_only_when_metastatic(self):
        local = self.patient("Ascending colon cancer", "COLORECTAL", "980402", "T3N0")
        meta = self.patient("Ascending colon cancer", "COLORECTAL", "980403", "T3N1M1")
        self.assertNotIn(K.RAS_BRAF, kinds(baseline_items(local)))
        self.assertIn(K.RAS_BRAF, kinds(baseline_items(meta)))

    def test_thyroid_gets_laryngoscopy(self):
        items = kinds(baseline_items(self.patient("Papillary thyroid carcinoma", "THYROID", "980404")))
        self.assertIn(K.LARYNGOSCOPY, items)
        self.assertIn(K.NECK_US, items)

    def test_gastric_gets_her2_and_eus(self):
        items = kinds(baseline_items(self.patient("Gastric cancer", "UPPER_GI", "980405")))
        self.assertIn(K.HER2, items)
        self.assertIn(K.EUS, items)
        self.assertNotIn(K.PD_L1, items)

    def test_oesophageal_gets_pd_l1_and_pet(self):
        items = kinds(baseline_items(self.patient("Distal oesophageal cancer", "UPPER_GI", "980406")))
        self.assertIn(K.PD_L1, items)
        self.assertIn(K.PET_CT, items)

    def test_pancreas_gets_protocol_ct_and_mrcp(self):
        items = kinds(baseline_items(self.patient("Pancreatic head mass", "HPB", "980407")))
        self.assertIn(K.PANCREAS_CT, items)
        self.assertIn(K.MRCP, items)
        self.assertIn(K.CA_19_9, items)

    def test_liver_gets_triphasic_afp_and_child_pugh(self):
        items = kinds(baseline_items(self.patient("Hepatocellular carcinoma", "HPB", "980408")))
        for kind in (K.TRIPHASIC, K.AFP, K.HEPATITIS, K.CHILD_PUGH):
            self.assertIn(kind, items)
        self.assertNotIn(K.PANCREAS_CT, items)


class CreationTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(consultant="Dr. Test", specialty="Breast")
        self.patient = Patient.objects.create(
            name="Test", mrn="980500", date_of_birth=date(1955, 1, 1),
            diagnosis="Right breast cancer", specialty="BREAST", team=self.team,
            sex="F", clinical_stage="cT2N0",
        )

    def test_the_reason_is_recorded_on_the_investigation(self):
        create_baseline_workup(self.patient)
        item = self.patient.investigations.get(kind=K.ABDOMEN_US)
        self.assertIn("early breast cancer", item.rationale)

    def test_optional_items_are_created_as_not_required(self):
        create_baseline_workup(self.patient)
        self.assertFalse(self.patient.investigations.get(kind=K.BREAST_MRI).required)

    def test_an_optional_item_does_not_block_readiness(self):
        create_baseline_workup(self.patient)
        for item in self.patient.investigations.filter(required=True):
            item.mark_ready("Reported.")
        self.assertTrue(Patient.objects.get(pk=self.patient.pk).workup_ready)

    def test_creating_twice_adds_nothing_and_keeps_results(self):
        create_baseline_workup(self.patient)
        first = self.patient.investigations.get(kind=K.MAMMOGRAM)
        first.mark_ready("Original report.")

        self.assertEqual(create_baseline_workup(self.patient), [])
        first.refresh_from_db()
        self.assertEqual(first.result_text, "Original report.")

    def test_restaging_is_per_diagnosis_too(self):
        rectum = Patient.objects.create(
            name="R", mrn="980501", date_of_birth=date(1960, 1, 1),
            diagnosis="Low rectal cancer", specialty="COLORECTAL", team=self.team,
        )
        self.assertIn(K.PELVIC_MRI, kinds(restaging_items(rectum)))
        self.assertNotIn(K.PELVIC_MRI, kinds(restaging_items(self.patient)))


class HistologyBeatsSiteTests(TestCase):
    """A sarcoma is a sarcoma wherever it grows."""

    def setUp(self):
        self.team = Team.objects.create(consultant="Dr. Test", specialty="General")

    def patient(self, diagnosis, mrn, specialty="GENERAL"):
        return Patient.objects.create(
            name="Test", mrn=mrn, date_of_birth=date(1960, 1, 1),
            diagnosis=diagnosis, specialty=specialty, team=self.team,
        )

    def test_a_gastric_gist_is_a_sarcoma_not_a_gastric_cancer(self):
        # Matching on "stomach" first sent this to the gastric adenocarcinoma
        # guideline, which is a different disease with a different workup.
        self.assertEqual(group_for(self.patient("GIST of stomach", "981000")), Group.SARCOMA)

    def test_the_spelled_out_form_routes_the_same_way(self):
        patient = self.patient("Gastrointestinal stromal tumour, stomach", "981001")
        self.assertEqual(group_for(patient), Group.SARCOMA)

    def test_a_rectal_leiomyosarcoma_is_a_sarcoma_not_a_rectal_cancer(self):
        patient = self.patient("Leiomyosarcoma of the rectum", "981002")
        self.assertEqual(group_for(patient), Group.SARCOMA)

    def test_a_retroperitoneal_liposarcoma_is_a_sarcoma(self):
        self.assertEqual(
            group_for(self.patient("Retroperitoneal liposarcoma", "981003")), Group.SARCOMA
        )

    def test_ordinary_organ_cancers_are_unaffected(self):
        for diagnosis, mrn, expected in [
            ("Gastric cancer", "981010", Group.GASTRIC),
            ("Low rectal cancer", "981011", Group.RECTUM),
            ("Ascending colon cancer", "981012", Group.COLON),
            ("Distal oesophageal cancer", "981013", Group.ESOPHAGEAL),
        ]:
            with self.subTest(diagnosis=diagnosis):
                self.assertEqual(group_for(self.patient(diagnosis, mrn)), expected)

    def test_a_gist_gets_the_sarcoma_checklist(self):
        items = kinds(baseline_items(self.patient("GIST of stomach", "981020")))
        self.assertIn(K.LOCAL_MRI, items)
        self.assertNotIn(K.HER2, items)
