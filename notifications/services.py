"""Creating notifications and sending the matching emails.

One entry point — :func:`notify` — so every alert in the app is recorded the
same way: a row in the inbox plus an email. Email failures never break the
clinical action that triggered them.
"""

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from .models import Notification

logger = logging.getLogger(__name__)


def team_recipients(team, include_fellows=True):
    """Everyone who should hear about a patient on ``team``.

    That is the team's nurse coordinator and consultant, plus the fellows
    currently rotating through the team.
    """
    from accounts.models import User
    from teams.models import FellowAssignment

    people = set(
        User.objects.filter(
            team=team,
            role__in=[User.Role.TEAM_COORDINATOR, User.Role.CONSULTANT],
            is_active=True,
        )
    )
    if include_fellows:
        today = timezone.localdate()
        people |= set(
            User.objects.filter(
                rotations__team=team,
                rotations__start_date__lte=today,
                rotations__end_date__gte=today,
                is_active=True,
            )
        )
    return [p for p in people if p.email]


def notify(recipients, patient, kind, subject, body):
    """Record a notification for each recipient and email it.

    Returns the created Notification objects. Recipients without an email
    address still get the in-app row.
    """
    created = []
    for person in recipients:
        note = Notification.objects.create(
            recipient=person, patient=patient, kind=kind, subject=subject, body=body
        )
        created.append(note)

    addresses = [p.email for p in recipients if p.email]
    if addresses:
        try:
            send_mail(
                subject=f"[KHCC Surgical Oncology] {subject}",
                message=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=addresses,
                fail_silently=False,
            )
        except Exception:
            # An unreachable mail server must not roll back the clinical action.
            logger.exception("Could not send notification email for %s", patient)
        else:
            now = timezone.now()
            for note in created:
                if note.recipient.email:
                    note.emailed_at = now
                    note.save(update_fields=["emailed_at"])
    return created


def patient_url(patient):
    """Absolute-ish link used inside email bodies."""
    return f"{settings.SITE_URL.rstrip('/')}/patients/{patient.pk}/"
