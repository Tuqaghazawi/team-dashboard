import calendar
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from teams.models import Team

from .models import Patient


def visible_patients(user):
    """The set of patients a given user is allowed to see.

    Public because other apps (e.g. ``mdc``) must apply the same rule.
    """
    if user.can_see_all_patients:
        return Patient.objects.select_related("team").all()
    if user.is_team_scoped and user.team_id:
        return Patient.objects.select_related("team").filter(team=user.team)
    if user.role == user.Role.MDC_COORDINATOR and user.mdc_id:
        # only patients listed on this coordinator's MDC
        return (
            Patient.objects.select_related("team")
            .filter(mdc_listings__mdc=user.mdc)
            .distinct()
        )
    # a user with no team / no MDC
    return Patient.objects.none()


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
    context = {
        "patient": patient,
        "listings": patient.mdc_listings.select_related("mdc"),
    }
    return render(request, "patients/patient_detail.html", context)
