import calendar
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from ai.extraction import review
from ai.pharmacy import periop_api
from teams.models import FellowAssignment, Team

from . import categories, flow
from .forms import (
    AddInvestigationForm,
    ClinicalDetailForm,
    InvestigationResultForm,
    OperativeOutcomeForm,
    PatientRegistrationForm,
    SurgeryBookingForm,
    TreatmentCourseForm,
)
from .models import (
    Investigation,
    Patient,
    ReportExtraction,
    SurgeryBooking,
    TreatmentCourse,
)


def visible_teams(user):
    """Team ids this user may see, or ``None`` meaning "every team"."""
    if user.can_see_all_patients:
        return None
    team_ids = set()
    if user.is_team_scoped and user.team_id:
        team_ids.add(user.team_id)
    if user.role == user.Role.FELLOW:
        # A fellow sees a team only while actually rotating through it.
        team_ids.update(FellowAssignment.teams_for(user))
    return team_ids


def visible_patients(user):
    """The set of patients a given user works with day to day.

    Public because other apps (e.g. ``mdc``) must apply the same rule.

    The prep clinic is the exception: her job is the handover queue, so her list
    holds only patients no coordinator has picked up yet. Once a patient is on
    an MDC list the team owns them and they leave her page. Her *reports* still
    count everybody — see :func:`reportable_patients`.
    """
    if user.role == user.Role.PREP_COORDINATOR and not user.is_superuser:
        return (
            Patient.objects.select_related("team")
            .filter(mdc_listings__isnull=True)
            .distinct()
        )
    if user.can_see_all_patients:
        return Patient.objects.select_related("team").all()

    team_ids = visible_teams(user)
    if team_ids:
        return Patient.objects.select_related("team").filter(team_id__in=team_ids)
    if user.role == user.Role.MDC_COORDINATOR and user.mdc_id:
        # only patients listed on this coordinator's MDC
        return (
            Patient.objects.select_related("team")
            .filter(mdc_listings__mdc=user.mdc)
            .distinct()
        )
    # a user with no team / no rotation / no MDC
    return Patient.objects.none()


def reportable_patients(user):
    """Everyone a user may count in a report.

    Wider than :func:`visible_patients` for the prep coordinator, whose working
    list is only the handover queue but whose weekly and monthly returns cover
    every patient she registered.
    """
    if user.can_see_all_patients:
        return Patient.objects.select_related("team").all()
    return visible_patients(user)


def _mdc_period_range(period):
    """Return (start, end) dates for an MDC-meeting period, or None for 'any time'."""
    today = timezone.localdate()
    if period == "this_week":
        start = today - timedelta(days=today.weekday())
        return start, start + timedelta(days=6)
    if period == "next_week":
        start = today - timedelta(days=today.weekday()) + timedelta(days=7)
        return start, start + timedelta(days=6)
    if period == "this_month":
        start = today.replace(day=1)
        last_day = calendar.monthrange(today.year, today.month)[1]
        return start, today.replace(day=last_day)
    return None


@login_required
def patient_list(request):
    visible = visible_patients(request.user)
    patients = visible

    # --- read filters from the URL ---
    q = request.GET.get("q", "").strip()
    selected_team = request.GET.get("team", "")
    selected_stage = request.GET.get("stage", "")
    selected_period = request.GET.get("period", "")
    new_only = request.GET.get("new") == "1"

    if q:
        patients = patients.filter(Q(name__icontains=q) | Q(mrn__icontains=q))
    if selected_team:
        patients = patients.filter(team_id=selected_team)
    if selected_stage:
        patients = patients.filter(stage=selected_stage)
    if new_only:
        cutoff = timezone.now() - timedelta(days=30)
        patients = patients.filter(registered_at__gte=cutoff)

    period_range = _mdc_period_range(selected_period)
    if period_range:
        patients = patients.filter(mdc_listings__meeting_date__range=period_range).distinct()

    patients = patients.prefetch_related("mdc_listings__mdc")

    # Stage options shown depend on which specialties this user actually sees
    present_specialties = set(visible.values_list("specialty", flat=True))
    stage_options = Patient.stages_for_specialties(present_specialties)

    context = {
        "patients": patients,
        "q": q,
        "selected_team": selected_team,
        "selected_stage": selected_stage,
        "selected_period": selected_period,
        "new_only": new_only,
        "stages": stage_options,
        # Only see-all users get a team filter (team-scoped users already see one team)
        "show_team_filter": request.user.can_see_all_patients,
        "teams": Team.objects.all() if request.user.can_see_all_patients else None,
    }
    return render(request, "patients/patient_list.html", context)


@login_required
def patient_detail(request, pk):
    # get_object_or_404 on the *visible* set => users can't open another team's patient
    patient = get_object_or_404(visible_patients(request.user), pk=pk)
    investigations = list(patient.investigations.all())
    ready, total = patient.workup_progress()
    context = {
        "patient": patient,
        "listings": patient.mdc_listings.select_related("mdc"),
        "baseline": [i for i in investigations if i.purpose == Investigation.Purpose.BASELINE],
        "restaging": [i for i in investigations if i.purpose == Investigation.Purpose.RESTAGING],
        "workup_ready_count": ready,
        "workup_total": total,
        "workup_percent": int(ready / total * 100) if total else 0,
        "courses": patient.treatment_courses.all(),
        "bookings": patient.surgery_bookings.all(),
    }
    return render(request, "patients/patient_detail.html", context)


@login_required
def dashboard(request):
    """The role-aware home page: every bucket the team works from."""
    visible = visible_patients(request.user)
    listings = categories.listings_for_week(visible, offset_weeks=1)

    context = {
        "counts": categories.summary_counts(visible),
        "new_patients": categories.new_patients(visible)[:8],
        "workup": categories.in_workup(visible).prefetch_related("investigations")[:8],
        "next_week_listings": listings,
        "next_week_range": categories.week_range(1),
        "neoadjuvant": categories.on_neoadjuvant(visible).prefetch_related("treatment_courses")[:8],
        "surgery": categories.awaiting_surgery(visible).prefetch_related("surgery_bookings")[:8],
        "postop_flagged": categories.post_op_needing_mdc(visible)[:8],
    }
    return render(request, "patients/dashboard.html", context)


@login_required
def patient_register(request):
    """Prep-clinic registration — step 1 of the pathway."""
    if not request.user.can_register_patients:
        raise PermissionDenied(
            "Only the prep clinic and team coordinators register patients."
        )
    if not request.user.can_see_all_patients and not request.user.team_id:
        messages.error(
            request,
            "You are not attached to a team, so there is no team to register a "
            "patient onto.",
        )
        return redirect("dashboard")

    if request.method == "POST":
        form = PatientRegistrationForm(request.POST, registrar=request.user)
        if form.is_valid():
            patient = form.save()
            notes = flow.on_patient_registered(patient, registered_by=request.user)
            messages.success(
                request,
                f"{patient.name} registered to {patient.team.consultant}. "
                f"{len(notes)} team member(s) notified by email.",
            )
            return redirect("patient_detail", pk=patient.pk)
    else:
        form = PatientRegistrationForm(registrar=request.user)
    return render(request, "patients/patient_register.html", {"form": form})


@login_required
def edit_clinical(request, pk):
    """The clinical background a fellow keeps up to date for the slides."""
    patient = get_object_or_404(visible_patients(request.user), pk=pk)
    if not request.user.can_record_clinical:
        raise PermissionDenied("Only the clinical team may edit these details.")

    if request.method == "POST":
        form = ClinicalDetailForm(request.POST, instance=patient)
        if form.is_valid():
            form.save()
            messages.success(request, "Clinical details updated.")
            return redirect("patient_detail", pk=patient.pk)
    else:
        form = ClinicalDetailForm(instance=patient)
    return render(
        request, "patients/edit_clinical.html", {"patient": patient, "form": form}
    )


@login_required
@require_POST
def begin_workup(request, pk):
    """Create the standard checklist for this specialty and start the workup."""
    patient = get_object_or_404(visible_patients(request.user), pk=pk)
    if not request.user.can_record_clinical:
        raise PermissionDenied("Only the clinical team may start a workup.")

    created = flow.start_workup(patient)
    if created:
        messages.success(
            request,
            f"Workup started — {len(created)} investigation(s) added to the checklist.",
        )
    else:
        messages.info(request, "The checklist was already in place.")
    return redirect("patient_detail", pk=patient.pk)


@login_required
def record_result(request, pk, investigation_pk):
    """Enter the report for one investigation."""
    patient = get_object_or_404(visible_patients(request.user), pk=pk)
    investigation = get_object_or_404(patient.investigations, pk=investigation_pk)
    if not request.user.can_record_clinical:
        raise PermissionDenied("Only the clinical team may record results.")

    if request.method == "POST":
        form = InvestigationResultForm(request.POST, instance=investigation)
        if form.is_valid():
            investigation = form.save(commit=False)
            investigation.status = Investigation.Status.READY
            investigation.resulted_on = timezone.localdate()
            investigation.save()
            sent = flow.on_result_recorded(investigation)
            messages.success(
                request,
                f"{investigation.get_kind_display()} result recorded."
                + (" The team has been notified." if sent else ""),
            )
            return redirect("patient_detail", pk=patient.pk)
    else:
        form = InvestigationResultForm(instance=investigation)
    return render(
        request,
        "patients/record_result.html",
        {"patient": patient, "investigation": investigation, "form": form},
    )


@login_required
def add_investigation(request, pk):
    """Add an extra item to a patient's workup checklist."""
    patient = get_object_or_404(visible_patients(request.user), pk=pk)
    if not request.user.can_record_clinical:
        raise PermissionDenied("Only the clinical team may change the checklist.")

    if request.method == "POST":
        form = AddInvestigationForm(request.POST)
        if form.is_valid():
            investigation = form.save(commit=False)
            investigation.patient = patient
            duplicate = patient.investigations.filter(
                kind=investigation.kind, purpose=investigation.purpose
            ).exists()
            if duplicate:
                messages.warning(
                    request,
                    f"{investigation.get_kind_display()} is already on this checklist.",
                )
            else:
                investigation.save()
                messages.success(
                    request, f"{investigation.get_kind_display()} added to the checklist."
                )
            return redirect("patient_detail", pk=patient.pk)
    else:
        form = AddInvestigationForm()
    return render(
        request, "patients/add_investigation.html", {"patient": patient, "form": form}
    )


# --- Neoadjuvant treatment (NACT / TNT) --------------------------------------

@login_required
def treatment_list(request):
    """The follow-up page for patients on NACT or TNT."""
    visible = visible_patients(request.user)
    courses = (
        TreatmentCourse.objects.filter(patient__in=visible, active=True)
        .select_related("patient", "patient__team")
        .prefetch_related("patient__investigations")
    )
    rows = []
    for course in courses:
        restaging = [
            i for i in course.patient.investigations.all()
            if i.purpose == Investigation.Purpose.RESTAGING
        ]
        rows.append({
            "course": course,
            "patient": course.patient,
            "restaging": restaging,
            "restaging_ready": course.restaging_ready,
        })
    return render(request, "patients/treatment_list.html", {"rows": rows})


@login_required
def start_treatment(request, pk):
    """Open a NACT / TNT course after the MDC has decided on one."""
    patient = get_object_or_404(visible_patients(request.user), pk=pk)
    if not request.user.can_record_clinical:
        raise PermissionDenied("Only the clinical team may open a treatment course.")

    if request.method == "POST":
        form = TreatmentCourseForm(request.POST)
        if form.is_valid():
            course = form.save(commit=False)
            course.patient = patient
            course.save()
            messages.success(
                request,
                f"{course.get_kind_display()} course opened — "
                f"{course.total_cycles} cycles of {course.regimen}.",
            )
            return redirect("patient_detail", pk=patient.pk)
    else:
        initial = {}
        if patient.stage == Patient.Stage.TNT:
            initial["kind"] = TreatmentCourse.Kind.TNT
        elif patient.stage == Patient.Stage.NACT:
            initial["kind"] = TreatmentCourse.Kind.NACT
        form = TreatmentCourseForm(initial=initial)
    return render(
        request, "patients/start_treatment.html", {"patient": patient, "form": form}
    )


@login_required
@require_POST
def record_cycle(request, pk, course_pk):
    """Mark one more cycle given. Triggers the restaging alert when due."""
    patient = get_object_or_404(visible_patients(request.user), pk=pk)
    course = get_object_or_404(patient.treatment_courses, pk=course_pk)
    if not request.user.can_record_clinical:
        raise PermissionDenied("Only the clinical team may record cycles.")

    if course.completed_cycles < course.total_cycles:
        course.completed_cycles += 1
        course.save(update_fields=["completed_cycles"])

    alerted = flow.check_restaging_due()
    message = f"Cycle {course.completed_cycles} of {course.total_cycles} recorded."
    if any(c.pk == course.pk for c in alerted):
        message += " Last cycle approaching — the team has been emailed to order restaging."
    messages.success(request, message)
    return redirect("patient_detail", pk=patient.pk)


@login_required
@require_POST
def close_treatment(request, pk, course_pk):
    """Close a course once the patient moves on to the definitive decision."""
    patient = get_object_or_404(visible_patients(request.user), pk=pk)
    course = get_object_or_404(patient.treatment_courses, pk=course_pk)
    if not request.user.can_record_clinical:
        raise PermissionDenied("Only the clinical team may close a treatment course.")

    course.active = False
    course.save(update_fields=["active"])
    messages.success(request, f"{course.get_kind_display()} course closed.")
    return redirect("patient_detail", pk=patient.pk)


# --- Surgery ------------------------------------------------------------------

@login_required
def surgery_schedule(request):
    """The team's surgery list."""
    visible = visible_patients(request.user)
    bookings = (
        SurgeryBooking.objects.filter(patient__in=visible, performed=False)
        .select_related("patient", "patient__team")
    )
    recent = (
        SurgeryBooking.objects.filter(patient__in=visible, performed=True)
        .select_related("patient", "patient__team")
        .order_by("-performed_on")[:15]
    )
    return render(
        request,
        "patients/surgery_schedule.html",
        {"bookings": bookings, "recent": recent},
    )


@login_required
def list_for_surgery(request, pk):
    """The coordinator puts a patient on the surgery schedule."""
    patient = get_object_or_404(visible_patients(request.user), pk=pk)
    if not request.user.can_manage_team_schedule:
        raise PermissionDenied("Only the team coordinator schedules surgery.")

    if request.method == "POST":
        form = SurgeryBookingForm(request.POST)
        if form.is_valid():
            booking = form.save(commit=False)
            booking.patient = patient
            booking.listed_by = request.user
            booking.save()
            if patient.stage != Patient.Stage.SURGERY:
                patient.stage = Patient.Stage.SURGERY
                patient.save(update_fields=["stage"])
            messages.success(
                request,
                f"{patient.name} listed for {booking.procedure} on {booking.planned_date}.",
            )
            return redirect("patient_detail", pk=patient.pk)
    else:
        form = SurgeryBookingForm()
    return render(
        request, "patients/list_for_surgery.html", {"patient": patient, "form": form}
    )


@login_required
def record_surgery(request, pk, booking_pk):
    """Record that surgery happened — this flags the patient for post-op MDC."""
    patient = get_object_or_404(visible_patients(request.user), pk=pk)
    booking = get_object_or_404(patient.surgery_bookings, pk=booking_pk)
    if not request.user.can_record_clinical:
        raise PermissionDenied("Only the clinical team may record an operation.")

    if request.method == "POST":
        form = OperativeOutcomeForm(request.POST, instance=booking)
        if form.is_valid():
            booking = form.save(commit=False)
            booking.performed = True
            booking.performed_on = booking.performed_on or timezone.localdate()
            booking.save()
            flow.on_surgery_performed(booking)
            messages.success(
                request,
                f"Surgery recorded. {patient.name} is now flagged for post-operative "
                f"MDC re-discussion.",
            )
            return redirect("patient_detail", pk=patient.pk)
    else:
        form = OperativeOutcomeForm(instance=booking)
    return render(
        request,
        "patients/record_surgery.html",
        {"patient": patient, "booking": booking, "form": form},
    )


# --- Report extraction (Capstone 1) -------------------------------------------

@login_required
@require_POST
def run_extraction(request, pk, investigation_pk):
    """Run the extractor over one report and open it for review.

    Nothing is saved to the patient record here — the result is stored as a
    pending extraction that a clinician must confirm.
    """
    patient = get_object_or_404(visible_patients(request.user), pk=pk)
    investigation = get_object_or_404(patient.investigations, pk=investigation_pk)
    if not request.user.can_record_clinical:
        raise PermissionDenied("Only the clinical team may run an extraction.")
    if not investigation.result_text.strip():
        messages.warning(request, "There is no report text to extract from yet.")
        return redirect("patient_detail", pk=patient.pk)

    try:
        extraction = review.extract(investigation.result_text)
    except review.ExtractionUnavailable as exc:
        messages.error(request, f"The extractor is unavailable ({exc}).")
        return redirect("patient_detail", pk=patient.pk)

    rows, meta = review.flatten(extraction)
    ReportExtraction.objects.update_or_create(
        investigation=investigation,
        defaults={
            "raw_fields": {"rows": rows, "meta": meta},
            "needs_human_review": meta["needs_human_review"],
            "status": ReportExtraction.Status.PENDING,
            "confirmed_fields": None,
            "reviewed_by": None,
            "reviewed_at": None,
        },
    )
    messages.info(
        request,
        "Extraction ready for review. Nothing has been saved to the record — "
        "check every field, especially the ones marked critical.",
    )
    return redirect("review_extraction", pk=patient.pk, investigation_pk=investigation.pk)


@login_required
def review_extraction(request, pk, investigation_pk):
    """The clinician checks, corrects and confirms an extraction."""
    patient = get_object_or_404(visible_patients(request.user), pk=pk)
    investigation = get_object_or_404(patient.investigations, pk=investigation_pk)
    extraction = get_object_or_404(ReportExtraction, investigation=investigation)
    if not request.user.can_record_clinical:
        raise PermissionDenied("Only the clinical team may review an extraction.")

    rows = extraction.raw_fields.get("rows", [])
    meta = extraction.raw_fields.get("meta", {})

    if request.method == "POST":
        if "reject" in request.POST:
            extraction.status = ReportExtraction.Status.REJECTED
            extraction.reviewed_by = request.user
            extraction.reviewed_at = timezone.now()
            extraction.save()
            messages.success(request, "Extraction rejected. The report text is unchanged.")
            return redirect("patient_detail", pk=patient.pk)

        confirmed = {
            row["path"]: request.POST.get(f"field__{row['path']}", "").strip()
            for row in rows
        }
        extraction.confirmed_fields = confirmed
        extraction.status = ReportExtraction.Status.CONFIRMED
        extraction.reviewed_by = request.user
        extraction.reviewed_at = timezone.now()
        extraction.save()
        messages.success(
            request,
            f"Extraction confirmed by {request.user.get_full_name() or request.user.username}.",
        )
        return redirect("patient_detail", pk=patient.pk)

    return render(
        request,
        "patients/review_extraction.html",
        {
            "patient": patient,
            "investigation": investigation,
            "extraction": extraction,
            "rows": rows,
            "meta": meta,
        },
    )


# --- Peri-operative medication check (Session 3) -------------------------------

@login_required
def periop_check_view(request, pk, booking_pk):
    """Medication alerts for a patient booked for surgery."""
    patient = get_object_or_404(visible_patients(request.user), pk=pk)
    booking = get_object_or_404(patient.surgery_bookings, pk=booking_pk)

    result, error = None, None
    try:
        result = periop_api.periop_alerts(patient.pharmacy_mrn, booking.planned_date)
    except periop_api.PeriopUnavailable as exc:
        error = str(exc)

    return render(
        request,
        "patients/periop_check.html",
        {"patient": patient, "booking": booking, "result": result, "error": error},
    )
