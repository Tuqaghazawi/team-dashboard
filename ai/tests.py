"""What a clinician is told when an AI feature is unavailable.

Every AI feature degrades rather than failing a page, so these messages are what
people actually see. Two properties matter: the cause must be the real one, and
an unrecognised cause must not be dressed up as a recognised one.
"""

from django.test import SimpleTestCase

from ai.reasons import explain


class ExplainTests(SimpleTestCase):
    def test_a_missing_index_is_explained_as_expected_here(self):
        message = explain(ModuleNotFoundError("No module named 'chromadb'"),
                          "The guideline brain")
        self.assertIn("The guideline brain is unavailable", message)
        self.assertIn("guideline index is not installed", message)
        self.assertIn("expected here", message)
        # The old message blamed the API key, which had nothing to do with it.
        self.assertNotIn("OPENAI_API_KEY", message)

    def test_a_missing_key_is_named_as_the_key(self):
        message = explain(Exception("The api_key client option must be set"),
                          "The extractor")
        self.assertIn("OPENAI_API_KEY is not set", message)
        self.assertNotIn("guideline index", message)

    def test_a_missing_workflow_library_is_named_as_that(self):
        message = explain(ModuleNotFoundError("No module named 'langgraph'"),
                          "The MDC workflow")
        self.assertIn("workflow library is not installed", message)

    def test_a_rate_limit_says_to_try_again(self):
        message = explain(Exception("Rate limit reached for gpt-4o-mini"),
                          "The guideline brain")
        self.assertIn("rate-limiting", message)
        self.assertIn("Try again", message)

    def test_an_unrecognised_failure_keeps_its_own_words(self):
        """A wrong explanation is worse than a raw one."""
        message = explain(Exception("Segmentation fault in the widget"),
                          "The MDC workflow")
        self.assertIn("Segmentation fault in the widget", message)
        self.assertNotIn("guideline index", message)
        self.assertNotIn("OPENAI_API_KEY", message)

    def test_every_message_names_the_feature_and_reassures_about_the_rest(self):
        for exception, feature in [
            (ModuleNotFoundError("No module named 'chromadb'"), "The guideline brain"),
            (Exception("api_key missing"), "The extractor"),
            (Exception("something odd"), "The MDC workflow"),
        ]:
            with self.subTest(feature=feature):
                message = explain(exception, feature)
                self.assertTrue(message.startswith(feature))
                self.assertIn("Nothing else on this page is affected.", message)
