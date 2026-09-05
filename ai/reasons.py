"""Explaining why an AI feature is unavailable, in words worth reading.

Each AI feature degrades to "unavailable" rather than failing a clinical page.
What reached the clinician, though, was the raw exception — `No module named
'chromadb'` — alongside advice to check an API key that had nothing to do with
it. On the deployed demo that reads as a broken app rather than a feature that
was never going to work there.

So: name the cause, say whether it is expected, and say that nothing else on the
page is affected. Anything unrecognised falls through to the original text,
because a wrong explanation is worse than a raw one.
"""

# Matched against the lower-cased exception text.
CAUSES = [
    (
        ("chromadb", "no such collection", "collection guidelines", "does not exist"),
        "the guideline index is not installed on this server, so there is nothing "
        "to search. That is expected here — the guidelines are licensed and cannot "
        "be published alongside the code. Run the app locally with the guideline "
        "PDFs to use this feature.",
    ),
    (
        ("openai_api_key", "api_key", "api key", "authentication", "401", "incorrect api key"),
        "OPENAI_API_KEY is not set on this server, or is not valid.",
    ),
    (
        ("langgraph", "langchain"),
        "the workflow library is not installed on this server.",
    ),
    (
        ("rate limit", "429"),
        "the model provider is rate-limiting requests. Try again shortly.",
    ),
    (
        ("timed out", "timeout", "connection", "temporarily unavailable"),
        "the model provider could not be reached. Try again shortly.",
    ),
    (
        ("insufficient_quota", "quota", "billing"),
        "the OpenAI account has no remaining quota.",
    ),
]

UNAFFECTED = "Nothing else on this page is affected."


def explain(exception, feature):
    """A one-line message for a clinician, naming the feature and the cause.

    ``feature`` is a noun phrase — "The guideline brain", "The MDC workflow".
    """
    text = str(exception).strip()
    lowered = text.lower()

    for needles, cause in CAUSES:
        if any(needle in lowered for needle in needles):
            return f"{feature} is unavailable: {cause} {UNAFFECTED}"

    # Unrecognised. Show what actually happened rather than guess at it.
    return f"{feature} is unavailable ({text}). {UNAFFECTED}"
