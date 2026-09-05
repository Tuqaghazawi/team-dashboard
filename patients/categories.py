"""The buckets a team looks at every day.

One place to define "new", "for MDC next week", "post-op" and so on, so the
dashboard, the patient list and the reports all count the same patients.

Every function takes the queryset of patients the current user may see, so
these never widen what somebody is allowed to look at.
"""

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from mdc.models import MDCListing

from .models import Patient


def new_patients(visible):
    """Registered, but with no MDC plan yet.

    That means nobody has put them on an MDC list, and no decision exists.
    """
    return (
        visible.filter(stage__in=[Patient.Stage.REGISTERED, Patient.Stage.CLINIC])
        .exclude(mdc_listings__isnull=False)
        .distinct()
    )


def in_workup(visible):
    """Under investigation — the checklist is open."""
    return visible.filter(stage=Patient.Stage.WORKUP).distinct()


def week_range(offset_weeks=1, today=None):
    """(Monday, Sunday) of the week ``offset_weeks`` from now."""
    today = today or timezone.localdate()
    monday = today - timedelta(days=today.weekday()) + timedelta(weeks=offset_weeks)
    return monday, monday + timedelta(days=6)


def listings_for_week(visible, offset_weeks=1, today=None):
    """MDC listings in a given week, for patients this user can see.

    ``offset_weeks=1`` is next week — the list the coordinator prepares and the
    fellow builds slides from.
    """
    start, end = week_range(offset_weeks, today)
    return (
        MDCListing.objects.filter(
            patient__in=visible, meeting_date__range=(start, end)
        )
        .select_related("patient", "patient__team", "mdc")
        .prefetch_related("patient__investigations")
        .order_by("meeting_date", "mdc__name", "patient__name")
    )


def post_mdc(visible, category):
    """Patients whose latest decision was ``category`` (surgery / NACT / TNT ...)."""
    return (
        visible.filter(mdc_listings__decision_category=category)
        .distinct()
    )


def on_neoadjuvant(visible):
    """NACT and TNT patients — followed by the team until the definitive decision."""
    return visible.filter(
        stage__in=[Patient.Stage.NACT, Patient.Stage.TNT, Patient.Stage.RESTAGING]
    ).distinct()


def awaiting_surgery(visible):
    return visible.filter(stage=Patient.Stage.SURGERY).distinct()


def post_operative(visible):
    """Post-op patients, still followed until re-discussed at MDC."""
    return visible.filter(stage=Patient.Stage.POSTOP).distinct()


def post_op_needing_mdc(visible):
    """Post-op patients with no post-op MDC listing yet — these must be flagged."""
    return (
        visible.filter(stage=Patient.Stage.POSTOP)
        .exclude(mdc_listings__is_postop=True)
        .distinct()
    )


def referred_out(visible):
    return visible.filter(stage=Patient.Stage.REFERRED).distinct()


def summary_counts(visible):
    """The numbers on the dashboard tiles."""
    return {
        "new": new_patients(visible).count(),
        "workup": in_workup(visible).count(),
        "mdc_next_week": listings_for_week(visible, 1).count(),
        "neoadjuvant": on_neoadjuvant(visible).count(),
        "surgery": awaiting_surgery(visible).count(),
        "postop": post_operative(visible).count(),
        "postop_flagged": post_op_needing_mdc(visible).count(),
    }


def ready_but_unlisted(visible):
    """Workup complete, but nobody has put them on an MDC list yet.

    This is the gap a consultant wants to catch: the patient is waiting and
    nothing is scheduled. Returns a list, because readiness is worked out in
    Python rather than in the database.
    """
    candidates = visible.filter(
        stage__in=[Patient.Stage.WORKUP, Patient.Stage.MDC]
    ).prefetch_related("investigations", "mdc_listings")

    waiting = []
    for patient in candidates:
        if not patient.workup_ready:
            continue
        # An undiscussed listing means it is already scheduled.
        if any(not listing.presented for listing in patient.mdc_listings.all()):
            continue
        waiting.append(patient)
    return waiting


def team_members(team):
    """Who is on a team right now: consultant, coordinator, and rotating fellows."""
    from accounts.models import User
    from teams.models import FellowAssignment

    today = timezone.localdate()
    members = team.members.filter(is_active=True)
    return {
        "consultants": list(members.filter(role=User.Role.CONSULTANT)),
        "coordinators": list(members.filter(role=User.Role.TEAM_COORDINATOR)),
        "rotations": list(
            FellowAssignment.objects.filter(
                team=team, start_date__lte=today, end_date__gte=today
            ).select_related("fellow")
        ),
    }


def decided_for_surgery_unscheduled(visible):
    """Decided for surgery at MDC, but never put on the theatre schedule.

    The other gap worth catching: the decision was made and then nothing
    happened. Returns a list.
    """
    candidates = awaiting_surgery(visible).prefetch_related("surgery_bookings")
    return [
        patient for patient in candidates
        if not any(not booking.performed for booking in patient.surgery_bookings.all())
    ]


def grouped_by_team(visible):
    """Patients split by the team they were assigned to.

    The prep-clinic view: she assigns patients to teams, so she needs to see how
    they are distributed rather than one flat list. Teams with nobody waiting are
    left out.
    """
    from collections import defaultdict

    buckets = defaultdict(list)
    for patient in visible.select_related("team").order_by("name"):
        buckets[patient.team].append(patient)

    return sorted(
        ({"team": team, "patients": rows} for team, rows in buckets.items()),
        key=lambda row: row["team"].consultant,
    )
