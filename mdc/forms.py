from django import forms

from .models import MDCListing, suggested_mdc_for


class MDCListingForm(forms.ModelForm):
    """Put one patient on an MDC's list for a given meeting date.

    The patient is fixed by the page you came from, so it is not a field here.
    """

    class Meta:
        model = MDCListing
        fields = ["mdc", "meeting_date"]
        widgets = {"meeting_date": forms.DateInput(attrs={"type": "date"})}
        labels = {"mdc": "Which MDC", "meeting_date": "Meeting date"}

    def __init__(self, *args, patient, **kwargs):
        super().__init__(*args, **kwargs)
        self.patient = patient

        # Pre-select the MDC this specialty usually goes to, and that MDC's next
        # meeting date. Both stay editable — and for "General surgical oncology"
        # there is no suggestion, so the coordinator chooses.
        if not self.is_bound:
            suggested = suggested_mdc_for(patient.specialty)
            if suggested:
                self.fields["mdc"].initial = suggested.pk
                self.fields["meeting_date"].initial = suggested.suggested_listing_date()

    def clean(self):
        cleaned = super().clean()
        mdc = cleaned.get("mdc")
        meeting_date = cleaned.get("meeting_date")
        if mdc and meeting_date:
            already_listed = MDCListing.objects.filter(
                patient=self.patient, mdc=mdc, meeting_date=meeting_date
            ).exists()
            if already_listed:
                raise forms.ValidationError(
                    f"{self.patient.name} is already on the {mdc.name} MDC list "
                    f"for {meeting_date}."
                )
        return cleaned
