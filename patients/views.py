from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .models import Patient


@login_required
def patient_list(request):
    """Show the patients this user is allowed to see."""
    user = request.user

    if user.can_see_all_patients:
        patients = Patient.objects.select_related("team").all()
    elif user.is_team_scoped and user.team_id:
        patients = Patient.objects.select_related("team").filter(team=user.team)
    else:
        # e.g. MDC coordinator (their list isn't built yet) or a user with no team
        patients = Patient.objects.none()

    return render(request, "patients/patient_list.html", {"patients": patients})
