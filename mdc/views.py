import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from patients.views import visible_patients
from teams.models import MDC

from .forms import MDCListingForm


@login_required
def add_listing(request, patient_pk):
    """Add one patient to an MDC's discussion list."""
    # Look the patient up inside what this user may see, so nobody can add a
    # patient from another team just by editing the URL.
    patient = get_object_or_404(visible_patients(request.user), pk=patient_pk)
    if not request.user.can_manage_mdc_list:
        raise PermissionDenied("Only team coordinators may add patients to an MDC list.")

    if request.method == "POST":
        form = MDCListingForm(request.POST, patient=patient)
        if form.is_valid():
            listing = form.save(commit=False)
            listing.patient = patient
            listing.save()
            messages.success(
                request,
                f"{patient.name} added to the {listing.mdc.name} MDC list "
                f"for {listing.meeting_date}.",
            )
            return redirect("patient_detail", pk=patient.pk)
    else:
        form = MDCListingForm(patient=patient)

    # Each MDC's suggested date, so choosing a different MDC updates the date.
    next_dates = {
        str(m.pk): m.suggested_listing_date().isoformat()
        for m in MDC.objects.all()
        if m.suggested_listing_date()
    }

    context = {
        "patient": patient,
        "form": form,
        "next_dates_json": json.dumps(next_dates),
    }
    return render(request, "mdc/add_listing.html", context)
