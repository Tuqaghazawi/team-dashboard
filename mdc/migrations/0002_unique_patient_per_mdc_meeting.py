from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("mdc", "0001_initial"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="mdclisting",
            constraint=models.UniqueConstraint(
                fields=("patient", "mdc", "meeting_date"),
                name="unique_patient_per_mdc_meeting",
            ),
        ),
    ]
