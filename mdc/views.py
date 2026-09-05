import json
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from ai import reasons
from ai.agents import dashboard_workflow
from ai.guidelines import suggest
from patients import categories, flow
from patients.views import visible_patients
from teams.models import MDC

from . import slides
from .forms import MDCDecisionForm, MDCListingForm
from .models import GuidelineSuggestion, MDCAgentReview, MDCListing


@login_required
def add_listing(request, patient_pk):
    """Add one patient to an MDC's discussion list."""
    # Look the patient up inside what this user may see, so nobody can add a
    # patient from another team just by editing the URL.
    patient = get_object_or_404(visible_patients(request.user), pk=patient_pk)
    if not request.user.can_manage_mdc_list:
        raise PermissionDenied("Only team coordinators may add patients to an MDC list.")

    if request.method == "POST":
        form = MDCListingForm(request.POST, patient=patient)
        if form.is_valid():
            listing = form.save(commit=False)
            listing.patient = patient
            listing.save()
            flow.on_listed_for_mdc(listing, listed_by=request.user)
            messages.success(
                request,
                f"{patient.name} added to the {listing.mdc.name} MDC list "
                f"for {listing.meeting_date}. The team has been notified.",
            )
            return redirect("patient_detail", pk=patient.pk)
    else:
        form = MDCListingForm(patient=patient)

    # Each MDC's suggested date, so choosing a different MDC updates the date.
    next_dates = {
        str(m.pk): m.suggested_listing_date().isoformat()
        for m in MDC.objects.all()
        if m.suggested_listing_date()
    }

    context = {
        "patient": patient,
        "form": form,
        "next_dates_json": json.dumps(next_dates),
    }
    return render(request, "mdc/add_listing.html", context)


@login_required
def mdc_board(request):
    """Every MDC list this user can see, grouped by week.

    The readiness column is what the coordinator and fellow work from: a patient
    whose investigations are not all back is not ready to be presented.
    """
    visible = visible_patients(request.user)
    weeks = []
    for offset, label in ((0, "This week"), (1, "Next week"), (2, "The week after")):
        start, end = categories.week_range(offset)
        listings = categories.listings_for_week(visible, offset)
        weeks.append({
            "label": label,
            "offset": offset,
            "start": start,
            "end": end,
            "listings": listings,
            "ready_count": sum(1 for listing in listings if listing.patient.workup_ready),
        })

    return render(
        request,
        "mdc/board.html",
        {
            "weeks": weeks,
            "mdcs": MDC.objects.all(),
            "postop_flagged": categories.post_op_needing_mdc(visible),
        },
    )


@login_required
def record_decision(request, pk):
    """Enter the MDC's decision and move the patient on."""
    listing = get_object_or_404(
        MDCListing.objects.select_related("patient", "mdc"),
        pk=pk,
        patient__in=visible_patients(request.user),
    )
    if not request.user.can_record_clinical:
        raise PermissionDenied("Only the clinical team may record an MDC decision.")

    if request.method == "POST":
        form = MDCDecisionForm(request.POST, instance=listing)
        if form.is_valid():
            listing = form.save()
            next_step = flow.apply_decision(listing, decided_by=request.user)
            messages.success(
                request,
                f"Decision recorded: {listing.get_decision_category_display()}."
                + (f" Next: {next_step}" if next_step else ""),
            )
            return redirect("patient_detail", pk=listing.patient_id)
    else:
        form = MDCDecisionForm(instance=listing)

    suggestion = listing.patient.guideline_suggestions.filter(
        kind=GuidelineSuggestion.Kind.DECISION
    ).first()
    return render(
        request,
        "mdc/record_decision.html",
        {
            "listing": listing,
            "patient": listing.patient,
            "form": form,
            "suggestion": suggestion,
            "agent_review": MDCAgentReview.objects.filter(listing=listing).first(),
        },
    )


@login_required
@require_POST
def request_suggestion(request, patient_pk, kind):
    """Ask the guideline brain for a workup or decision suggestion."""
    patient = get_object_or_404(visible_patients(request.user), pk=patient_pk)
    if not request.user.can_record_clinical:
        raise PermissionDenied("Only the clinical team may request a suggestion.")
    if kind not in GuidelineSuggestion.Kind.values:
        raise Http404("Unknown suggestion type.")

    ask = suggest.suggest_workup if kind == GuidelineSuggestion.Kind.WORKUP else suggest.suggest_decision
    try:
        result = ask(patient)
    except suggest.GuidelineUnavailable as exc:
        messages.error(request, reasons.explain(exc, "The guideline brain"))
    else:
        coverage = result.get("coverage", {})
        grading = result.get("grading", {})
        note = ""
        if not coverage.get("covered", True):
            topics = ", ".join(coverage.get("topics") or []) or patient.get_specialty_display()
            note = (
                f"No guideline covering {topics} is indexed, so this answer cannot "
                f"be grounded in one. Indexed: "
                f"{', '.join(coverage.get('indexed', []))}."
            )

        GuidelineSuggestion.objects.create(
            patient=patient,
            kind=kind,
            question=result["question"],
            answer=result["answer"],
            citations="\n".join(result["citations"]),
            refused=result.get("refused", False),
            coverage_note=note,
            grade_attempts=grading.get("attempts", 0),
            graded_pass=grading.get("passed"),
            grader_feedback=grading.get("feedback", ""),
            requested_by=request.user,
        )
        if result.get("refused"):
            messages.warning(
                request,
                "The guideline brain found nothing covering this case and declined "
                "to answer." + (f" {note}" if note else ""),
            )
        else:
            messages.success(
                request,
                "Guideline suggestion ready — review it before acting on it. "
                "Nothing has been changed on the patient record.",
            )
    return redirect(request.POST.get("next") or "patient_detail", pk=patient.pk)


# --- slide decks --------------------------------------------------------------

def _evidence_notes(patients):
    """Latest decision-suggestion per patient, for the slide notes field."""
    notes = {}
    for patient in patients:
        suggestion = patient.guideline_suggestions.filter(
            kind=GuidelineSuggestion.Kind.DECISION
        ).first()
        if suggestion:
            notes[patient.pk] = suggestion.as_slide_note()
    return notes


@login_required
def download_mdc_deck(request, mdc_pk, meeting_date):
    """Generate the MDC slide deck for one meeting."""
    mdc = get_object_or_404(MDC, pk=mdc_pk)
    try:
        date_obj = date.fromisoformat(meeting_date)
    except ValueError:
        raise Http404("Bad meeting date.")

    listings = (
        MDCListing.objects.filter(
            mdc=mdc, meeting_date=date_obj, patient__in=visible_patients(request.user)
        )
        .select_related("patient", "patient__team")
        .prefetch_related(
            "patient__investigations",
            "patient__treatment_courses",
            "patient__surgery_bookings",
            "patient__guideline_suggestions",
        )
        .order_by("patient__name")
    )
    if not listings:
        messages.warning(request, "No patients are listed for that meeting.")
        return redirect("mdc_board")

    presenter = request.user.get_full_name() or ""
    if request.user.team_id:
        presenter = request.user.team.consultant

    stream = slides.build_mdc_deck(
        mdc.name,
        date_obj,
        listings,
        presenter=presenter,
        evidence=_evidence_notes([listing.patient for listing in listings]),
    )
    filename = f"{mdc.name.replace(' ', '_')}_MDC_{date_obj:%Y-%m-%d}.pptx"
    return _pptx_response(stream, filename)


@login_required
def download_planning_deck(request):
    """Generate the team's planning-round deck (operative patients)."""
    team = request.user.team
    if team is None:
        messages.error(request, "You are not attached to a team, so there is no planning list.")
        return redirect("surgery_schedule")

    visible = visible_patients(request.user)
    patients = (
        visible.filter(team=team, surgery_bookings__performed=False)
        .distinct()
        .prefetch_related(
            "investigations", "treatment_courses", "surgery_bookings", "guideline_suggestions"
        )
        .order_by("name")
    )
    if not patients:
        messages.warning(request, "No patients are currently listed for surgery.")
        return redirect("surgery_schedule")

    today = timezone.localdate()
    stream = slides.build_planning_deck(
        team, today, patients, evidence=_evidence_notes(patients)
    )
    filename = f"Planning_{team.consultant.replace(' ', '_')}_{today:%Y-%m-%d}.pptx"
    return _pptx_response(stream, filename)


def _pptx_response(stream, filename):
    response = HttpResponse(
        stream.read(),
        content_type=(
            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        ),
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


# --- Multi-agent MDC workflow with physician sign-off (Session 5) --------------

@login_required
@require_POST
def start_agent_review(request, pk):
    """Run the multi-agent workflow and hold its draft for sign-off."""
    listing = get_object_or_404(
        MDCListing.objects.select_related("patient"),
        pk=pk,
        patient__in=visible_patients(request.user),
    )
    if not request.user.can_record_clinical:
        raise PermissionDenied("Only the clinical team may run the MDC workflow.")

    try:
        draft = dashboard_workflow.start_review(listing)
    except dashboard_workflow.WorkflowUnavailable as exc:
        messages.error(request, reasons.explain(exc, "The MDC workflow"))
        return redirect("record_decision", pk=listing.pk)

    MDCAgentReview.objects.update_or_create(
        listing=listing,
        defaults={
            "recommendation": draft,
            "status": MDCAgentReview.Status.AWAITING,
            "started_by": request.user,
            "approved_by": None,
            "approved_at": None,
        },
    )
    messages.info(
        request,
        "The workflow has drafted a recommendation and is holding it for sign-off. "
        "Nothing has been recorded against the patient.",
    )
    return redirect("record_decision", pk=listing.pk)


@login_required
@require_POST
def sign_off_agent_review(request, pk):
    """Approve the draft, or reject it with feedback so the graph revises."""
    listing = get_object_or_404(
        MDCListing.objects.select_related("patient"),
        pk=pk,
        patient__in=visible_patients(request.user),
    )
    review = get_object_or_404(MDCAgentReview, listing=listing)
    if not request.user.can_record_clinical:
        raise PermissionDenied("Only the clinical team may sign off a recommendation.")

    approved = request.POST.get("verdict") == "approve"
    feedback = request.POST.get("feedback", "").strip()
    if not approved and not feedback:
        messages.error(request, "Say what needs changing so the workflow can revise it.")
        return redirect("record_decision", pk=listing.pk)

    try:
        status, recommendation = dashboard_workflow.resume_review(
            listing, "approved" if approved else "rejected", feedback
        )
    except dashboard_workflow.WorkflowUnavailable as exc:
        messages.error(request, reasons.explain(exc, "The MDC workflow"))
        return redirect("record_decision", pk=listing.pk)

    review.recommendation = recommendation or review.recommendation
    review.revisions = dashboard_workflow.revisions(listing)
    if status == "approved":
        review.status = MDCAgentReview.Status.APPROVED
        review.approved_by = request.user
        review.approved_at = timezone.now()
        messages.success(
            request,
            "Recommendation approved. Record the MDC decision below — approving the "
            "draft does not write it to the patient record.",
        )
    else:
        review.status = MDCAgentReview.Status.AWAITING
        review.last_feedback = feedback
        messages.info(request, "Sent back with your feedback. A revised draft is ready.")
    review.save()
    return redirect("record_decision", pk=listing.pk)
