from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import render

from patients.views import reportable_patients

from .build import build_workbook, collect, period_range


def _check(user):
    """Reports are the prep coordinator's and the chairman's view of activity."""
    if not user.can_see_all_patients:
        raise PermissionDenied("Only the prep-clinic coordinator and chairman see reports.")


@login_required
def reports_home(request):
    _check(request.user)
    patients = reportable_patients(request.user)
    periods = []
    for period in ("week", "month"):
        start, end, label = period_range(period)
        periods.append(
            {
                "period": period,
                "label": label,
                "start": start,
                "end": end,
                "data": collect(patients, start, end),
            }
        )
    return render(request, "reports/reports_home.html", {"periods": periods})


@login_required
def download_report(request, period):
    """The auto-generated Excel sheet."""
    _check(request.user)
    if period not in ("week", "month"):
        raise PermissionDenied("Unknown report period.")

    start, end, label = period_range(period)
    data = collect(reportable_patients(request.user), start, end)
    stream = build_workbook(data, label)

    filename = f"prep-clinic-{period}ly-{start:%Y-%m-%d}.xlsx"
    response = HttpResponse(
        stream.read(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
