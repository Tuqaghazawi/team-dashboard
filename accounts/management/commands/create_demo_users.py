from django.core.management.base import BaseCommand

from accounts.models import User
from teams.models import Team

# Throwaway password for the synthetic-data prototype only. These demo logins must
# never exist in a real deployment — see the note in README.
DEMO_PASSWORD = "demo1234"


class Command(BaseCommand):
    help = "Create (or reset) the demo team-coordinator login used to try out features."

    def handle(self, *args, **options):
        # Same team as fellow1, so you can compare what each role sees.
        team = Team.objects.filter(consultant__icontains="Alawneh").first()
        if team is None:
            self.stderr.write(
                self.style.ERROR("No 'Alawneh' team found — load the teams fixture first.")
            )
            return

        user, created = User.objects.get_or_create(
            username="coord1",
            defaults={"first_name": "Demo", "last_name": "Coordinator"},
        )
        # Set every time, so re-running repairs a changed role or forgotten password.
        user.role = User.Role.TEAM_COORDINATOR
        user.team = team
        user.set_password(DEMO_PASSWORD)
        user.save()

        self.stdout.write(
            self.style.SUCCESS(
                f"{'Created' if created else 'Reset'} demo login "
                f"'{user.username}' (password: {DEMO_PASSWORD})\n"
                f"  Role: {user.get_role_display()}\n"
                f"  Team: {team.consultant}"
            )
        )
