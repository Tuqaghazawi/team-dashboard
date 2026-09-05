"""The guideline brain behind the dashboard's workup and decision suggestions.

This does not re-implement retrieval. It reuses the Session 6 RAG module
(``ai/rag``) — the same ChromaDB index over the KHCC guidelines — and adds two
things the dashboard needs and the original script does not provide:

  * a return value instead of printed output, with the citations kept separate
    so they can be shown under the suggestion and written into the slide notes;
  * graceful failure, so a missing API key or index degrades to "unavailable"
    rather than breaking a clinical page.

Everything here is a *suggestion*. It is rendered as a suggestion, it never
writes to the patient record on its own, and a clinician decides.
"""

import sys
from pathlib import Path

RAG_DIR = Path(__file__).resolve().parents[1] / "rag"

CHAT_MODEL = "gpt-4o-mini"

WORKUP_SYSTEM = (
    "You are a clinical guideline assistant for a surgical oncology MDC at KHCC.\n"
    "1. Answer ONLY from the numbered context passages. Use no outside knowledge.\n"
    "2. List the staging and workup investigations the guideline requires for this "
    "presentation, as short bullet lines.\n"
    "3. If the guideline does not cover it, reply exactly: "
    "'Not found in the provided guidelines.'\n"
    "4. Cite the passages you used with their exact labels as shown."
)

DECISION_SYSTEM = (
    "You are a clinical guideline assistant for a surgical oncology MDC at KHCC.\n"
    "1. Answer ONLY from the numbered context passages. Use no outside knowledge.\n"
    "2. State the treatment option the guideline supports for this presentation, "
    "in one or two sentences, then give the supporting evidence as short bullets.\n"
    "3. This is a suggestion for the MDC to consider, not a decision. Do not use "
    "commanding language.\n"
    "4. If the guideline does not cover it, reply exactly: "
    "'Not found in the provided guidelines.'\n"
    "5. Cite the passages you used with their exact labels as shown."
)


class GuidelineUnavailable(RuntimeError):
    """Raised when the guideline index or the API key is not usable."""


def _rag():
    """Import the Session 6 RAG module, which expects to run from its own folder."""
    if str(RAG_DIR) not in sys.path:
        sys.path.insert(0, str(RAG_DIR))
    try:
        import rag_answer  # noqa: PLC0415 - deliberately deferred
    except Exception as exc:  # missing key, missing chromadb, missing index
        raise GuidelineUnavailable(str(exc)) from exc
    return rag_answer


def patient_summary(patient):
    """The one-line presentation the guideline is asked about."""
    bits = [f"{patient.age}-year-old"]
    if patient.sex:
        bits.append(patient.get_sex_display().lower())
    bits.append(f"with {patient.diagnosis}")
    if patient.clinical_stage:
        bits.append(f"clinical stage {patient.clinical_stage}")
    if patient.genetic_testing:
        bits.append(f"genetics: {patient.genetic_testing}")
    return ", ".join(bits)


def suggest_workup(patient, k=5):
    """Investigations the guideline expects before this patient is discussed."""
    question = (
        f"What staging and workup investigations are required for a "
        f"{patient_summary(patient)}?"
    )
    return _ask(question, WORKUP_SYSTEM, k)


def suggest_decision(patient, k=5):
    """Treatment options the guideline supports, for the MDC to consider."""
    summary = patient_summary(patient)
    findings = _findings(patient)
    question = (
        f"What treatment does the guideline support for a {summary}?"
        + (f"\n\nInvestigation findings:\n{findings}" if findings else "")
    )
    return _ask(question, DECISION_SYSTEM, k)


def _findings(patient):
    from patients.models import Investigation

    lines = [
        f"- {i.get_kind_display()}: {i.result_text}"
        for i in patient.investigations.all()
        if i.status == Investigation.Status.READY and i.result_text
    ]
    return "\n".join(lines)


def _ask(question, system, k):
    """Retrieve, answer, and return {'answer', 'citations', 'question'}."""
    rag = _rag()
    try:
        chunks = rag.retrieve(question, k=k)
        context = rag.build_context(chunks)
        response = rag.client.chat.completions.create(
            model=CHAT_MODEL,
            temperature=0,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
            ],
        )
    except Exception as exc:
        raise GuidelineUnavailable(str(exc)) from exc

    citations = sorted({f"{c['cancer']}, pages {c['pages']}" for c in chunks})
    return {
        "question": question,
        "answer": response.choices[0].message.content.strip(),
        "citations": citations,
    }
