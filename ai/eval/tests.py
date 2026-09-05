"""The evaluator's own checks.

The history check is the one that needs testing, because it has produced two
false positives of the same shape — a forbidden phrase sitting in a sentence
that proposes something else entirely. A checker that cries wolf is worse than
no checker: it trains you to skim past a real failure.
"""

from django.test import SimpleTestCase

from ai.eval.guideline_eval import CaseResult, check_history, summarise


class HistoryCheckTests(SimpleTestCase):
    def test_a_proposal_of_the_completed_operation_is_caught(self):
        self.assertTrue(check_history(
            "We recommend proceeding to total gastrectomy.", ["gastrectomy"]
        ))

    def test_a_candidate_phrasing_is_caught(self):
        self.assertTrue(check_history(
            "The patient is a candidate for oesophagectomy if medically fit.",
            ["oesophagectomy"],
        ))

    def test_mentioning_the_operation_as_history_is_not_caught(self):
        # "consider X following Y" proposes X and merely dates it from Y.
        self.assertEqual(check_history(
            "Consider adjuvant systemic therapy following modified radical "
            "mastectomy, particularly endocrine therapy.",
            ["mastectomy"],
        ), [])

    def test_postmastectomy_radiotherapy_is_not_caught(self):
        # The correct recommendation after a mastectomy; "mastectomy" is a
        # substring of it, which is why the match is on word boundaries.
        self.assertEqual(check_history(
            "The guideline supports postmastectomy radiation therapy (PMRT).",
            ["mastectomy"],
        ), [])

    def test_after_the_operation_is_not_caught(self):
        self.assertEqual(check_history(
            "Consider adjuvant chemotherapy after the gastrectomy.", ["gastrectomy"]
        ), [])

    def test_a_sentence_that_proposes_nothing_is_not_checked(self):
        self.assertEqual(check_history(
            "The patient underwent a total gastrectomy in August.", ["gastrectomy"]
        ), [])


class SummaryTests(SimpleTestCase):
    def _result(self, **kwargs):
        defaults = dict(case_id="c", refused=False, should_refuse=False,
                        sources=["Colon, pages 1-2"], expect_sources=["Colon"])
        defaults.update(kwargs)
        return CaseResult(**defaults)

    def test_a_correct_refusal_counts_as_correct_sources(self):
        # A refusal carries no citations, so there is nothing to get wrong.
        result = self._result(refused=True, should_refuse=True, sources=[],
                              expect_sources=[])
        self.assertTrue(result.sources_correct)
        self.assertTrue(result.refusal_correct)

    def test_an_answer_citing_another_disease_fails_sources(self):
        result = self._result(sources=["Pancreatic, pages 210-232"])
        self.assertFalse(result.sources_correct)

    def test_history_safety_is_measured_over_answered_cases_only(self):
        results = [
            self._result(refused=True, should_refuse=True, sources=[], expect_sources=[]),
            self._result(history_violations=["gastrectomy -> ..."]),
        ]
        # One answered case, and it failed.
        self.assertEqual(summarise(results)["history_safety"], "0/1 (0%)")
