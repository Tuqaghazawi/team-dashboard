"""The guideline brain behind the dashboard's workup and decision suggestions.

This does not re-implement retrieval. It reuses the Session 6 RAG module
(``ai/rag``) — the same ChromaDB index over the KHCC guidelines — and adds what
the dashboard needs and the original script does not provide:

* a return value instead of printed output, with the citations kept separate;
* **the patient's history**, not just their diagnosis. Asking "what treatment
  does the guideline support for a T3N2 rectal cancer" about a patient who is
  already five cycles into TNT gets you a plan for a treatment-naive patient.
  Everything already done — treatment given, surgery performed, final
  pathology, restaging — goes into the question, and the question names which
  decision is actually being asked for;
* an honest coverage check. The index holds six guidelines. A patient whose
  disease is not one of them still retrieves *something*, because a vector
  search always returns its nearest neighbours, so the caller is told when no
  guideline for this disease exists;
* graceful failure, so a missing API key or index degrades to "unavailable"
  rather than breaking a clinical page.

Everything here is a *suggestion*. It is rendered as a suggestion, it never
writes to the patient record, and a clinician decides.
"""

import sys
from pathlib import Path

RAG_DIR = Path(__file__).resolve().parents[1] / "rag"

CHAT_MODEL = "gpt-4o-mini"

# The exact sentence the RAG prompt uses to decline. Detected so that a refusal
# is not decorated with citations that make it look researched.
REFUSAL = "Not found in the provided guidelines"

# Coverage is read from the index itself rather than hardcoded, so adding a
# guideline (see `manage.py add_guideline`) immediately widens what the app
# claims to cover. This list is only the fallback for when ChromaDB cannot be
# reached at all.
FALLBACK_GUIDELINES = {"Breast", "Colon", "Rectal", "Thyroid", "Gastric", "Pancreatic"}

# Which guideline topic a patient needs is decided by ``patients.diagnosis`` —
# the same module the workup checklist uses, so the two can never disagree about
# what a patient has.

_indexed_cache = None


def indexed_guidelines(refresh=False):
    """The guideline labels actually present in the ChromaDB index."""
    global _indexed_cache
    if _indexed_cache is not None and not refresh:
        return _indexed_cache
    try:
        rag = _rag()
        collection = rag.chroma.get_collection("guidelines")
        rows = collection.get(include=["metadatas"])
        _indexed_cache = sorted({m["cancer"] for m in rows["metadatas"] if m.get("cancer")})
    except Exception:
        _indexed_cache = sorted(FALLBACK_GUIDELINES)
    return _indexed_cache


def topics_for(patient):
    """The guideline topic(s) this patient actually needs."""
    from patients.diagnosis import topics_for as diagnosis_topics

    return diagnosis_topics(patient)

WORKUP_SYSTEM = (
    "You are a clinical guideline assistant for a surgical oncology MDC at KHCC.\n"
    "1. Answer ONLY from the numbered context passages. Use no outside knowledge.\n"
    "2. List the staging and workup investigations the guideline requires for this "
    "presentation, as short bullet lines.\n"
    "3. Take account of what has already been done. Do not re-request an "
    "investigation whose result is already given, and do not propose baseline "
    "staging for a patient who has already been treated.\n"
    f"4. If the guideline does not cover this disease, reply exactly: '{REFUSAL}.'\n"
    "5. Cite the passages you used with their exact labels as shown."
)

DECISION_SYSTEM = (
    "You are a clinical guideline assistant for a surgical oncology MDC at KHCC.\n"
    "1. Answer ONLY from the numbered context passages. Use no outside knowledge.\n"
    "2. Answer the specific decision the question asks about, at the point in "
    "treatment the patient has actually reached. Never propose a treatment the "
    "patient has already completed, and never propose an operation on an organ "
    "that has already been resected.\n"
    "3. State the option the guideline supports in one or two sentences, then "
    "give the supporting evidence as short bullets.\n"
    "4. This is a suggestion for the MDC to consider, not a decision. Do not use "
    "commanding language.\n"
    "5. Check that the evidence you cite applies to this patient's stage. Do not "
    "cite guidance for a different stage than the one given.\n"
    f"6. If the guideline does not cover this disease, reply exactly: '{REFUSAL}.'\n"
    "7. Cite the passages you used with their exact labels as shown."
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


# --- describing the patient ---------------------------------------------------

def patient_summary(patient):
    """The presentation line: who the patient is and what they have."""
    bits = [f"{patient.age}-year-old"]
    if patient.sex:
        bits.append(patient.get_sex_display().lower())
    bits.append(f"with {patient.diagnosis}")
    if patient.clinical_stage:
        bits.append(f"clinical stage {patient.clinical_stage}")
    if patient.genetic_testing:
        bits.append(f"genetics: {patient.genetic_testing}")
    return ", ".join(bits)


def treatment_history(patient):
    """What has already been done to this patient, as lines. Empty if nothing."""
    lines = []
    for course in patient.treatment_courses.all():
        state = "completed" if course.completed_cycles >= course.total_cycles else "in progress"
        lines.append(
            f"- Has already received {course.get_kind_display()} ({course.regimen}): "
            f"{course.completed_cycles} of {course.total_cycles} cycles, {state}."
        )
    for booking in patient.surgery_bookings.all():
        if booking.performed:
            lines.append(
                f"- Has already undergone {booking.procedure} on {booking.performed_on}."
            )
            if booking.final_pathology:
                lines.append(f"  Final pathology: {booking.final_pathology}")
    return lines


def _findings(patient, purpose):
    from patients.models import Investigation

    return [
        f"- {i.get_kind_display()}: {i.result_text}"
        for i in patient.investigations.all()
        if i.purpose == purpose
        and i.status == Investigation.Status.READY
        and i.result_text
    ]


def decision_asked(patient):
    """Which decision the MDC is actually being asked for.

    A post-operative patient needs an adjuvant plan, not a primary plan; a
    patient who has finished neoadjuvant treatment needs a decision on what
    follows it. Getting this wrong is what produced plans for treatments the
    patient had already had.
    """
    from patients.models import Patient

    stage = patient.stage
    if stage == Patient.Stage.POSTOP:
        return (
            "This is a POST-OPERATIVE re-discussion. The primary operation is done. "
            "What does the guideline support as the post-operative / adjuvant plan?"
        )
    if stage in (Patient.Stage.NACT, Patient.Stage.TNT, Patient.Stage.RESTAGING):
        return (
            "This patient is PART-WAY THROUGH neoadjuvant treatment. What does the "
            "guideline support as the next step after this neoadjuvant course "
            "completes and restaging is done?"
        )
    if stage == Patient.Stage.SURGERY:
        return (
            "Surgery has been decided but not yet performed. What does the guideline "
            "support around the operative plan for this patient?"
        )
    return "What primary treatment does the guideline support for this patient?"


def _case_block(patient, include_restaging=True):
    """The full case as the guideline brain should see it."""
    parts = [patient_summary(patient) + "."]

    history = treatment_history(patient)
    if history:
        parts.append("\nAlready done:\n" + "\n".join(history))

    baseline = _findings(patient, _purpose().BASELINE)
    if baseline:
        parts.append("\nBaseline investigations:\n" + "\n".join(baseline))

    if include_restaging:
        restaging = _findings(patient, _purpose().RESTAGING)
        if restaging:
            parts.append("\nRestaging after treatment:\n" + "\n".join(restaging))

    return "\n".join(parts)


def _purpose():
    from patients.models import Investigation

    return Investigation.Purpose


# --- coverage -----------------------------------------------------------------

def coverage_for(patient):
    """Whether a guideline for this patient's disease is in the index.

    Returns {"covered", "topics", "matched", "indexed"}. A vector search always
    returns its nearest neighbours, so an uncovered disease still gets passages
    back — from a different cancer entirely. The caller must say so.
    """
    topics = topics_for(patient)
    indexed = indexed_guidelines()
    matched = sorted(
        {
            label for label in indexed
            if any(topic in label.lower() for topic in topics)
        }
    )
    return {
        "covered": bool(matched),
        "topics": topics,
        "matched": matched,
        "indexed": indexed,
    }


# --- the two questions --------------------------------------------------------

def suggest_workup(patient, k=5):
    """Investigations the guideline expects for this patient, as they stand now."""
    question = (
        "What staging and workup investigations does the guideline require for "
        "this patient?\n\n"
        f"Patient:\n{_case_block(patient)}"
    )
    return _ask(question, WORKUP_SYSTEM, k, patient)


def suggest_decision(patient, k=5):
    """Treatment options the guideline supports, for the MDC to consider."""
    question = (
        f"{decision_asked(patient)}\n\n"
        f"Patient:\n{_case_block(patient)}"
    )
    return _ask(question, DECISION_SYSTEM, k, patient)


def _ask(question, system, k, patient=None):
    """Retrieve, answer, and return the answer with its citations."""
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

    answer = response.choices[0].message.content.strip()
    refused = answer.startswith(REFUSAL)

    # A refusal must not carry citations: listing the passages a vector search
    # happened to return makes "no guideline covers this" look researched.
    citations = (
        [] if refused
        else sorted({f"{c['cancer']}, pages {c['pages']}" for c in chunks})
    )

    result = {
        "question": question,
        "answer": answer,
        "citations": citations,
        "refused": refused,
        "retrieved_from": sorted({c["cancer"] for c in chunks}),
    }
    if patient is not None:
        result["coverage"] = coverage_for(patient)
    return result
