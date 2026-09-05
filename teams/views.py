from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.models import User
from patients import categories
from patients.models import SurgeryBooking
from patients.views import visible_patients, visible_teams

from .forms import FellowAssignmentForm
from .models import FellowAssignment, Team


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


@login_required
def team_home(request):
    """Send the user to their own team, or let them choose one.

    A consultant or coordinator has one team. A fellow has whichever teams they
    are rotating through. The chairman and prep-clinic coordinator see them all.
    """
    team_ids = visible_teams(request.user)

    if team_ids is None:  # chairman / prep coordinator — every team
        teams = Team.objects.all()
    else:
        teams = Team.objects.filter(pk__in=team_ids)

    if teams.count() == 1:
        return redirect("team_detail", pk=teams.first().pk)

    if not teams:
        messages.info(
            request,
            "You are not attached to a team. A team coordinator assigns fellows "
            "to a team at the start of each rotation.",
        )
        return redirect("dashboard")

    rows = []
    for team in teams.prefetch_related("patients"):
        rows.append({"team": team, "members": categories.team_members(team)})
    return render(request, "teams/team_list.html", {"rows": rows})


@login_required
def team_detail(request, pk):
    """One team's own page: who is on it, and where every patient stands."""
    team = get_object_or_404(Team, pk=pk)

    team_ids = visible_teams(request.user)
    if team_ids is not None and team.pk not in team_ids:
        raise PermissionDenied("You do not have access to this team.")

    # Scope to this team inside what the user may already see, so the page can
    # never widen anyone's access.
    patients = visible_patients(request.user).filter(team=team)

    listings = categories.listings_for_week(patients, offset_weeks=1)
    bookings = (
        SurgeryBooking.objects.filter(patient__in=patients, performed=False)
        .select_related("patient")
    )

    return render(
        request,
        "teams/team_detail.html",
        {
            "team": team,
            "members": categories.team_members(team),
            "counts": categories.summary_counts(patients),
            "total": patients.count(),
            "needs_listing": categories.ready_but_unlisted(patients),
            "needs_scheduling": categories.decided_for_surgery_unscheduled(patients),
            "postop_flagged": categories.post_op_needing_mdc(patients),
            "next_week_listings": listings,
            "next_week_range": categories.week_range(1),
            "workup": categories.in_workup(patients).prefetch_related("investigations"),
            "neoadjuvant": categories.on_neoadjuvant(patients).prefetch_related(
                "treatment_courses"
            ),
            "bookings": bookings,
            "quarter": FellowAssignment.current_quarter(),
        },
    )
