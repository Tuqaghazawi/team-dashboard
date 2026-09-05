"""What happens next, at each step of the patient pathway.

Every rule that moves a patient forward or sends an alert lives here, so the
views stay thin and the pathway can be read in one place.

Nothing in here decides anything clinical on its own: it reacts to what a
clinician has already recorded.
"""

from django.utils import timezone

from notifications.models import Notification
from notifications.services import notify, patient_url, team_recipients

from .models import Investigation, Patient
from .workup import create_baseline_workup, create_restaging_workup


def on_patient_registered(patient, registered_by=None):
    """Step 1 — the prep clinic has registered a patient onto a team.

    The team's coordinator, consultant and rotating fellows are told there is a
    new patient for the coming clinic.
    """
    body = (
        f"{patient.name} (MRN {patient.mrn}) has been registered to "
        f"{patient.team.consultant} for the upcoming clinic.\n\n"
        f"Diagnosis: {patient.diagnosis}\n"
        f"Specialty: {patient.get_specialty_display()}\n"
        f"Date of birth: {patient.date_of_birth} (age {patient.age})\n"
    )
    if registered_by:
        body += f"Registered by: {registered_by.get_full_name() or registered_by.username}\n"
    body += (
        f"\nNext step: the team coordinator should place this patient on the "
        f"proposed MDC list for next week.\n\n{patient_url(patient)}"
    )
    return notify(
        team_recipients(patient.team),
        patient,
        Notification.Kind.NEW_PATIENT,
        f"New patient for {patient.team.consultant}: {patient.name}",
        body,
    )


def on_listed_for_mdc(listing, listed_by=None):
    """Step 2 — the coordinator has put the patient on an MDC list."""
    patient = listing.patient
    body = (
        f"{patient.name} (MRN {patient.mrn}) is listed for the "
        f"{listing.mdc.name} MDC on {listing.meeting_date}.\n\n"
        f"Workup: {format_workup_progress(patient)}\n\n{patient_url(patient)}"
    )
    return notify(
        team_recipients(patient.team),
        patient,
        Notification.Kind.MDC_LISTED,
        f"Listed for {listing.mdc.name} MDC ({listing.meeting_date}): {patient.name}",
        body,
    )


def start_workup(patient):
    """Step 3 — the patient has been seen in clinic and workup begins.

    Creates the standard checklist for the specialty and moves the patient to
    the workup stage. Existing checklist items are untouched.
    """
    created = create_baseline_workup(patient)
    if patient.stage in (Patient.Stage.REGISTERED, Patient.Stage.CLINIC):
        patient.stage = Patient.Stage.WORKUP
        patient.save(update_fields=["stage"])
    return created


def on_result_recorded(investigation):
    """Step 4 — a report has come back.

    When it completes the baseline checklist, the team is told the patient is
    ready to be presented.
    """
    patient = investigation.patient
    if investigation.purpose == Investigation.Purpose.BASELINE:
        if patient.workup_ready:
            return notify(
                team_recipients(patient.team),
                patient,
                Notification.Kind.WORKUP_READY,
                f"Workup complete — ready for MDC: {patient.name}",
                f"All requested investigations for {patient.name} (MRN {patient.mrn}) "
                f"are back. The patient can now be presented at MDC.\n\n"
                f"{patient_url(patient)}",
            )
        return []

    # Restaging: tell the team once every restaging report is in, so they can
    # review before the upcoming clinic.
    course = patient.active_treatment
    if course and course.restaging_ready and course.results_alert_sent_on is None:
        course.results_alert_sent_on = timezone.localdate()
        course.save(update_fields=["results_alert_sent_on"])
        return notify(
            team_recipients(patient.team),
            patient,
            Notification.Kind.RESTAGING_READY,
            f"Restaging reports ready for review: {patient.name}",
            f"Restaging for {patient.name} (MRN {patient.mrn}) after "
            f"{course.get_kind_display()} ({course.regimen}) is complete. "
            f"Please review before the upcoming clinic.\n\n"
            f"{format_results(course.restaging_investigations)}\n\n"
            f"{patient_url(patient)}",
        )
    return []


def apply_decision(listing, decided_by=None):
    """Step 5 — record an MDC decision and move the patient accordingly.

    ``listing.decision_category`` must already be set. Returns a short note on
    what the coordinator has to do next, or an empty string.
    """
    from mdc.models import MDCListing

    patient = listing.patient
    category = listing.decision_category
    if not category:
        return ""

    listing.presented = True
    listing.decided_on = listing.decided_on or timezone.localdate()
    listing.save(update_fields=["presented", "decided_on"])

    new_stage = MDCListing.DECISION_TO_STAGE.get(category)
    if new_stage:
        patient.stage = new_stage
        patient.save(update_fields=["stage"])

    # Further workup means a fresh look at the checklist.
    if category == MDCListing.Decision.MORE_WORKUP:
        create_baseline_workup(patient)

    body = (
        f"MDC decision for {patient.name} (MRN {patient.mrn}) at the "
        f"{listing.mdc.name} MDC on {listing.meeting_date}:\n\n"
        f"{listing.get_decision_category_display()}\n"
        f"{listing.decision}\n\n{patient_url(patient)}"
    )
    notify(
        team_recipients(patient.team),
        patient,
        Notification.Kind.DECISION,
        f"MDC decision — {patient.name}: {listing.get_decision_category_display()}",
        body,
    )

    next_steps = {
        MDCListing.Decision.SURGERY: "Add this patient to the team's surgery schedule.",
        MDCListing.Decision.NACT: "Open a NACT course so the team can follow the cycles.",
        MDCListing.Decision.TNT: "Open a TNT course so the team can follow the cycles.",
        MDCListing.Decision.MORE_WORKUP: "Complete the outstanding investigations and re-list.",
    }
    return next_steps.get(category, "")


def on_surgery_performed(booking):
    """Step 6 — surgery is done; the patient must come back to MDC."""
    patient = booking.patient
    patient.stage = Patient.Stage.POSTOP
    patient.save(update_fields=["stage"])
    return notify(
        team_recipients(patient.team),
        patient,
        Notification.Kind.POSTOP_MDC_DUE,
        f"Post-op — needs re-discussion at MDC: {patient.name}",
        f"{patient.name} (MRN {patient.mrn}) had {booking.procedure} on "
        f"{booking.performed_on}. The patient must be re-presented at MDC for the "
        f"post-operative plan.\n\n"
        f"Final pathology: {booking.final_pathology or 'not yet available'}\n\n"
        f"{patient_url(patient)}",
    )


# --- helpers -----------------------------------------------------------------

def format_workup_progress(patient):
    ready, total = patient.workup_progress()
    if total == 0:
        return "no checklist yet"
    if ready == total:
        return f"complete ({ready}/{total})"
    outstanding = ", ".join(i.get_kind_display() for i in patient.outstanding_investigations)
    return f"{ready}/{total} back — still awaiting: {outstanding}"


def format_results(investigations):
    lines = []
    for item in investigations:
        if item.status == Investigation.Status.READY:
            lines.append(f"- {item.get_kind_display()}: {item.result_text}")
        else:
            lines.append(f"- {item.get_kind_display()}: {item.get_status_display()}")
    return "\n".join(lines)


def check_restaging_due(today=None):
    """Alert teams whose NACT/TNT patients are reaching their last cycle.

    Sends one email per course, the first time it reaches the penultimate
    cycle, telling the team to order restaging. Safe to run daily.
    Returns the courses alerted on.
    """
    from .models import TreatmentCourse

    today = today or timezone.localdate()
    alerted = []
    courses = (
        TreatmentCourse.objects.filter(active=True, restaging_alert_sent_on__isnull=True)
        .select_related("patient", "patient__team")
    )
    for course in courses:
        if not course.on_last_cycle:
            continue
        patient = course.patient
        created = create_restaging_workup(patient)
        course.restaging_alert_sent_on = today
        course.save(update_fields=["restaging_alert_sent_on"])
        notify(
            team_recipients(patient.team),
            patient,
            Notification.Kind.RESTAGING_DUE,
            f"Order restaging — {patient.name} is on the last cycle",
            f"{patient.name} (MRN {patient.mrn}) has completed "
            f"{course.completed_cycles} of {course.total_cycles} cycles of "
            f"{course.get_kind_display()} ({course.regimen}).\n\n"
            f"Please order restaging investigations before the last cycle so the "
            f"results are ready for the team to review.\n\n"
            f"Restaging checklist "
            f"{'created' if created else 'already in place'}:\n"
            f"{format_results(course.restaging_investigations)}\n\n"
            f"{patient_url(patient)}",
        )
        alerted.append(course)
    return alerted


def check_postop_mdc_due(today=None):
    """Remind teams about post-op patients not yet re-presented at MDC.

    Sends at most one reminder per patient (the notification row is the record).
    """
    reminded = []
    postop = (
        Patient.objects.filter(stage=Patient.Stage.POSTOP)
        .select_related("team")
        .prefetch_related("mdc_listings")
    )
    for patient in postop:
        if not patient.needs_postop_mdc:
            continue
        already = patient.notifications.filter(
            kind=Notification.Kind.POSTOP_MDC_DUE
        ).exists()
        if already:
            continue
        notify(
            team_recipients(patient.team),
            patient,
            Notification.Kind.POSTOP_MDC_DUE,
            f"Post-op patient awaiting MDC re-discussion: {patient.name}",
            f"{patient.name} (MRN {patient.mrn}) is post-operative and has not yet "
            f"been re-presented at MDC for the post-operative plan.\n\n"
            f"{patient_url(patient)}",
        )
        reminded.append(patient)
    return reminded
