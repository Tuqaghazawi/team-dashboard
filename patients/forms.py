from django import forms

from teams.models import Team

from .models import Investigation, Patient, SurgeryBooking, TreatmentCourse


class PatientRegistrationForm(forms.ModelForm):
    """The details captured when a patient first arrives.

    Filled by the prep-clinic nurse for patients coming through prep, or by a
    team coordinator for one arriving straight at their own clinic. Choosing the
    team is how the consultant is chosen — a team *is* its consultant.
    """

    class Meta:
        model = Patient
        fields = ["name", "mrn", "date_of_birth", "diagnosis", "specialty", "team"]
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
            "diagnosis": forms.TextInput(),
        }
        labels = {
            "mrn": "MRN",
            "team": "Consultant / team",
            "specialty": "Specialty",
        }
        help_texts = {
            "team": "The consultant this patient is booked under.",
        }

    def __init__(self, *args, registrar=None, **kwargs):
        super().__init__(*args, **kwargs)
        # A team coordinator registers onto her own team only; the prep clinic
        # chooses freely because assigning the team is the whole point of prep.
        if registrar is not None and not registrar.can_see_all_patients:
            if registrar.team_id:
                self.fields["team"].queryset = Team.objects.filter(pk=registrar.team_id)
                self.fields["team"].initial = registrar.team_id
                self.fields["team"].help_text = "Your own team."


class ClinicalDetailForm(forms.ModelForm):
    """The clinical background a fellow adds — this is what the slides print."""

    class Meta:
        model = Patient
        fields = [
            "sex", "comorbidities", "family_history", "genetic_testing",
            "clinical_stage", "diagnosis",
        ]
        widgets = {
            "comorbidities": forms.Textarea(attrs={"rows": 2}),
            "family_history": forms.Textarea(attrs={"rows": 2}),
        }
        labels = {
            "clinical_stage": "Clinical stage",
            "genetic_testing": "Genetic testing",
        }


class InvestigationResultForm(forms.ModelForm):
    """Enter the report for one workup item."""

    class Meta:
        model = Investigation
        fields = ["result_text"]
        widgets = {
            "result_text": forms.Textarea(
                attrs={"rows": 4, "placeholder": "Paste the report text as it should read on the slide."}
            )
        }
        labels = {"result_text": "Report"}


class AddInvestigationForm(forms.ModelForm):
    """Add an extra investigation to a patient's checklist."""

    class Meta:
        model = Investigation
        fields = ["kind", "purpose", "required"]
        labels = {"kind": "Investigation", "required": "Required before MDC"}


class TreatmentCourseForm(forms.ModelForm):
    """Open a NACT / TNT course after the MDC decides on one."""

    class Meta:
        model = TreatmentCourse
        fields = ["kind", "regimen", "total_cycles", "start_date", "next_cycle_date"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "next_cycle_date": forms.DateInput(attrs={"type": "date"}),
        }
        labels = {
            "kind": "Treatment",
            "total_cycles": "Planned number of cycles",
            "next_cycle_date": "Next cycle due",
        }


class SurgeryBookingForm(forms.ModelForm):
    """Put a patient on the team's surgery schedule."""

    class Meta:
        model = SurgeryBooking
        fields = ["planned_date", "procedure"]
        widgets = {"planned_date": forms.DateInput(attrs={"type": "date"})}
        labels = {"planned_date": "Planned date", "procedure": "Procedure"}


class OperativeOutcomeForm(forms.ModelForm):
    """Record that surgery happened, and the final pathology it produced."""

    class Meta:
        model = SurgeryBooking
        fields = ["performed_on", "final_pathology"]
        widgets = {
            "performed_on": forms.DateInput(attrs={"type": "date"}),
            "final_pathology": forms.Textarea(attrs={"rows": 4}),
        }
        labels = {"performed_on": "Date of surgery", "final_pathology": "Final pathology"}
