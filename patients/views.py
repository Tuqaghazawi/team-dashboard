from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

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
    patients = _visible_patients(request.user)
    return render(request, "patients/patient_list.html", {"patients": patients})


@login_required
def patient_detail(request, pk):
    # get_object_or_404 on the *visible* set => users can't open another team's patient
    patient = get_object_or_404(_visible_patients(request.user), pk=pk)
    return render(request, "patients/patient_detail.html", {"patient": patient})
