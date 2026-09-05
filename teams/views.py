from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.utils import timezone

from accounts.models import User

from .forms import FellowAssignmentForm
from .models import FellowAssignment


@login_required
def rotation_list(request):
    """Fellows assigned to teams for the current three-month rotation.

    The team's nurse coordinator sets these at the start of each block; an
    assignment is what gives a fellow access to the team dashboard.
    """
    if not request.user.can_manage_team_schedule:
        raise PermissionDenied("Only the team coordinator manages rotations.")

    today = timezone.localdate()
    quarter_start, quarter_end = FellowAssignment.current_quarter(today)

    assignments = FellowAssignment.objects.select_related("fellow", "team")
    if request.user.team_id and not request.user.can_see_all_patients:
        assignments = assignments.filter(team=request.user.team)

    if request.method == "POST":
        form = FellowAssignmentForm(request.POST, coordinator=request.user)
        if form.is_valid():
            assignment = form.save(commit=False)
            assignment.assigned_by = request.user
            assignment.save()
            messages.success(
                request,
                f"{assignment.fellow.get_full_name() or assignment.fellow.username} "
                f"assigned to {assignment.team.consultant} "
                f"({assignment.start_date} to {assignment.end_date}).",
            )
            return redirect("rotation_list")
    else:
        form = FellowAssignmentForm(
            coordinator=request.user,
            initial={"start_date": quarter_start, "end_date": quarter_end},
        )

    return render(
        request,
        "teams/rotation_list.html",
        {
            "form": form,
            "current": [a for a in assignments if a.is_current],
            "past": [a for a in assignments if not a.is_current],
            "quarter_start": quarter_start,
            "quarter_end": quarter_end,
        },
    )
