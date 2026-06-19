from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from teams.models import Team

from .models import Patient


def _visible_patients(user):
    """The set of patients a given user is allowed to see."""
    if user.can_see_all_patients:
        return Patient.objects.select_related("team").all()
    if user.is_team_scoped and user.team_id:
        return Patient.objects.select_related("team").filter(team=user.team)
    # e.g. MDC coordinator (list not built yet) or a user with no team
    return Patient.objects.none()


@login_required
def patient_list(request):
    visible = _visible_patients(request.user)
    patients = visible

    # --- read filters from the URL (?q=...&team=...&stage=...&new=1) ---
    q = request.GET.get("q", "").strip()
    selected_team = request.GET.get("team", "")
    selected_stage = request.GET.get("stage", "")
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

    # Stage options shown depend on which specialties this user actually sees
    present_specialties = set(visible.values_list("specialty", flat=True))
    stage_options = Patient.stages_for_specialties(present_specialties)

    context = {
        "patients": patients,
        "q": q,
        "selected_team": selected_team,
        "selected_stage": selected_stage,
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
    patient = get_object_or_404(_visible_patients(request.user), pk=pk)
    return render(request, "patients/patient_detail.html", {"patient": patient})
