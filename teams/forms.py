from django import forms

from accounts.models import User

from .models import FellowAssignment, Team


class FellowAssignmentForm(forms.ModelForm):
    """Assign one fellow to a team for a rotation block."""

    class Meta:
        model = FellowAssignment
        fields = ["fellow", "team", "start_date", "end_date"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }
        labels = {"fellow": "Fellow", "team": "Team"}

    def __init__(self, *args, coordinator=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["fellow"].queryset = User.objects.filter(
            role=User.Role.FELLOW, is_active=True
        ).order_by("first_name", "username")

        # A team coordinator assigns to their own team only.
        if coordinator is not None and not coordinator.can_see_all_patients:
            if coordinator.team_id:
                self.fields["team"].queryset = Team.objects.filter(pk=coordinator.team_id)
                self.fields["team"].initial = coordinator.team_id

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start_date"), cleaned.get("end_date")
        if start and end and end < start:
            raise forms.ValidationError("The rotation cannot end before it starts.")
        return cleaned
