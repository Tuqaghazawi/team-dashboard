from django.db import migrations, models

MEETING_WEEKDAYS = {
    "Breast": 2,                    # Wednesday
    "Gastrointestinal (GI)": 0,     # Monday
    "Sarcoma": 6,                   # Sunday
    "Thyroid": 2,                   # Wednesday
}


def set_meeting_weekdays(apps, schema_editor):
    MDC = apps.get_model("teams", "MDC")
    for name, weekday in MEETING_WEEKDAYS.items():
        MDC.objects.filter(name=name).update(meeting_weekday=weekday)


def clear_meeting_weekdays(apps, schema_editor):
    MDC = apps.get_model("teams", "MDC")
    MDC.objects.update(meeting_weekday=None)


class Migration(migrations.Migration):

    dependencies = [
        ("teams", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="mdc",
            name="meeting_weekday",
            field=models.IntegerField(
                blank=True,
                choices=[
                    (0, "Monday"),
                    (1, "Tuesday"),
                    (2, "Wednesday"),
                    (3, "Thursday"),
                    (4, "Friday"),
                    (5, "Saturday"),
                    (6, "Sunday"),
                ],
                help_text="The day of the week this MDC meets, used to suggest the next meeting date.",
                null=True,
            ),
        ),
        migrations.RunPython(set_meeting_weekdays, clear_meeting_weekdays),
    ]
