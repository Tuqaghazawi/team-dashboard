from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .models import Notification


@login_required
def notification_list(request):
    """This user's inbox — every alert the pathway has raised for them."""
    notes = request.user.notifications.select_related("patient", "patient__team")
    return render(
        request,
        "notifications/notification_list.html",
        {"notes": notes, "unread": [n for n in notes if not n.is_read]},
    )


@login_required
def open_notification(request, pk):
    """Mark one alert read and jump to the patient it is about."""
    note = get_object_or_404(request.user.notifications, pk=pk)
    note.mark_read()
    return redirect("patient_detail", pk=note.patient_id)


@login_required
def mark_all_read(request):
    for note in request.user.notifications.filter(read_at__isnull=True):
        note.mark_read()
    return redirect("notification_list")
