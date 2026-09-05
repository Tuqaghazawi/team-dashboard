"""Driving the Session 5 MDC workflow from the dashboard.

The workflow itself — the supervisor, the two specialist agents, the recommend
node and the ``interrupt()`` sign-off gate — is unchanged; this module reuses
those node functions directly. It adds the two things a web app needs that the
standalone script does not:

* **Durable pauses.** ``mdc_workflow.build()`` compiles with ``InMemorySaver``,
  which is fine for a script but loses a paused case the moment the server
  restarts. Here the same graph is compiled with ``SqliteSaver``, so a
  recommendation waiting for a physician survives a restart. The wiring is
  repeated rather than the checkpointer being swapped after the fact, because a
  compiled graph's checkpointer is not meant to be reassigned.

* **A case description built from the patient record** instead of a hand-typed
  string.

The human gate is the point of all this: nothing the agents produce is recorded
against a patient until a physician approves it, and rejecting sends their
feedback back into the graph for a revision.
"""

import sqlite3
import threading
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "mdc_checkpoints.sqlite3"

_graph = None
_lock = threading.Lock()


class WorkflowUnavailable(RuntimeError):
    """The workflow could not be built — usually a missing API key."""


def _build_graph():
    """Compile the Session 5 graph with a durable checkpointer."""
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver
        from langgraph.graph import END, START, StateGraph

        from ai.agents import mdc_workflow
    except Exception as exc:
        raise WorkflowUnavailable(str(exc)) from exc

    connection = sqlite3.connect(DB_PATH, check_same_thread=False)
    saver = SqliteSaver(connection)
    saver.setup()

    builder = StateGraph(mdc_workflow.MDCState)
    builder.add_node("supervisor", mdc_workflow.supervisor)
    builder.add_node("guideline_checker", mdc_workflow.guideline_checker)
    builder.add_node("drug_checker", mdc_workflow.drug_checker)
    builder.add_node("recommend", mdc_workflow.recommend)
    builder.add_node("human_review", mdc_workflow.human_review)
    builder.add_edge(START, "supervisor")
    builder.add_edge("guideline_checker", "supervisor")
    builder.add_edge("drug_checker", "supervisor")
    builder.add_edge("recommend", "human_review")
    return builder.compile(checkpointer=saver)


def graph():
    """The compiled workflow, built once per process."""
    global _graph
    with _lock:
        if _graph is None:
            _graph = _build_graph()
    return _graph


def thread_config(listing):
    """One conversation thread per MDC listing, so revisions accumulate."""
    return {"configurable": {"thread_id": f"listing-{listing.pk}"}}


def case_text(patient):
    """The case as the agents see it, built from what the team has recorded."""
    from patients.models import Investigation

    lines = [
        f"{patient.age}-year-old "
        f"{patient.get_sex_display().lower() if patient.sex else ''} patient".replace("  ", " "),
        f"Diagnosis: {patient.diagnosis}",
    ]
    if patient.clinical_stage:
        lines.append(f"Clinical stage: {patient.clinical_stage}")
    if patient.comorbidities:
        lines.append(f"Background: {patient.comorbidities}")
    if patient.genetic_testing:
        lines.append(f"Genetic testing: {patient.genetic_testing}")

    results = [
        f"  - {i.get_kind_display()}: {i.result_text}"
        for i in patient.investigations.all()
        if i.status == Investigation.Status.READY and i.result_text
    ]
    if results:
        lines.append("Investigations:")
        lines.extend(results)

    for course in patient.treatment_courses.all():
        lines.append(
            f"Treatment given: {course.get_kind_display()} — {course.regimen} "
            f"({course.completed_cycles} of {course.total_cycles} cycles)"
        )
    for booking in patient.surgery_bookings.all():
        if booking.performed:
            lines.append(f"Surgery: {booking.procedure} on {booking.performed_on}")
            if booking.final_pathology:
                lines.append(f"Final pathology: {booking.final_pathology}")

    lines.append("MDC review requested.")
    return "\n".join(lines)


def start_review(listing):
    """Run the agents and draft a recommendation, pausing for sign-off.

    Returns the drafted recommendation. The graph stays paused at
    ``human_review`` until :func:`resume_review` is called.
    """
    compiled = graph()
    config = thread_config(listing)
    try:
        result = compiled.invoke(
            {"case": case_text(listing.patient), "revisions": 0}, config
        )
    except Exception as exc:
        raise WorkflowUnavailable(str(exc)) from exc
    return _pending_draft(result, compiled, config)


def resume_review(listing, decision, feedback=""):
    """Approve, or reject with feedback so the graph revises.

    Returns (status, recommendation) where status is "approved" or "revised".
    """
    from langgraph.types import Command

    compiled = graph()
    config = thread_config(listing)
    payload = {"decision": decision}
    if decision == "rejected":
        payload["feedback"] = feedback

    try:
        result = compiled.invoke(Command(resume=payload), config)
    except Exception as exc:
        raise WorkflowUnavailable(str(exc)) from exc

    state = compiled.get_state(config).values
    if decision == "approved":
        return "approved", state.get("recommendation", "")
    # Rejection loops back through recommend and pauses again with a new draft.
    return "revised", _pending_draft(result, compiled, config)


def revisions(listing):
    """How many times the physician has sent this recommendation back."""
    try:
        state = graph().get_state(thread_config(listing))
    except Exception:
        return 0
    return (state.values or {}).get("revisions", 0)


def _pending_draft(result, compiled, config):
    """The recommendation currently held at the interrupt."""
    interrupts = result.get("__interrupt__") if isinstance(result, dict) else None
    if interrupts:
        value = interrupts[0].value
        if isinstance(value, dict) and "recommendation" in value:
            return value["recommendation"]
    return (compiled.get_state(config).values or {}).get("recommendation", "")
