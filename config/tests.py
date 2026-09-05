"""Deployment configuration.

PRD §16 promises HTTPS, secure cookies and a PostgreSQL switch. These pin the
promises that are checkable without actually deploying, so a settings edit
cannot quietly undo them.
"""

import os
from unittest import mock

from django.test import SimpleTestCase


def load_settings(**environment):
    """Import settings fresh under a given environment.

    The module is dropped from sys.modules first rather than reloaded, because
    a reload re-executes the file over the *existing* module object: settings
    only assigned inside ``if not DEBUG`` would keep their value from a previous
    load, and a DEBUG=True check would read a production value.
    """
    import sys

    with mock.patch.dict(os.environ, environment, clear=False):
        sys.modules.pop("config.settings", None)
        import config.settings as module

        return module


class ProductionHardeningTests(SimpleTestCase):
    def tearDown(self):
        # Leave the module as the rest of the suite expects to find it.
        load_settings(DEBUG="True")

    def test_debug_off_turns_on_https_and_secure_cookies(self):
        settings = load_settings(DEBUG="False", DJANGO_SECRET_KEY="x" * 60)

        self.assertFalse(settings.DEBUG)
        self.assertTrue(settings.SECURE_SSL_REDIRECT)
        self.assertTrue(settings.SESSION_COOKIE_SECURE)
        self.assertTrue(settings.CSRF_COOKIE_SECURE)
        self.assertTrue(settings.SECURE_CONTENT_TYPE_NOSNIFF)
        self.assertEqual(settings.X_FRAME_OPTIONS, "DENY")

    def test_the_proxy_header_is_set_so_the_https_redirect_cannot_loop(self):
        # Render terminates TLS at its proxy. Without this Django sees http on
        # every request and SECURE_SSL_REDIRECT redirects to itself forever.
        settings = load_settings(DEBUG="False", DJANGO_SECRET_KEY="x" * 60)
        self.assertEqual(
            settings.SECURE_PROXY_SSL_HEADER, ("HTTP_X_FORWARDED_PROTO", "https")
        )

    def test_development_is_not_forced_onto_https(self):
        settings = load_settings(DEBUG="True")
        self.assertFalse(getattr(settings, "SECURE_SSL_REDIRECT", False))

    def test_hsts_is_off_by_default(self):
        """An HSTS header a browser has cached cannot be withdrawn early, so it
        stays off until the deployment is known good."""
        settings = load_settings(DEBUG="False", DJANGO_SECRET_KEY="x" * 60)
        self.assertEqual(settings.SECURE_HSTS_SECONDS, 0)

    def test_the_render_hostname_is_trusted_when_supplied(self):
        settings = load_settings(
            DEBUG="False", DJANGO_SECRET_KEY="x" * 60,
            RENDER_EXTERNAL_HOSTNAME="dash.onrender.com",
        )
        self.assertIn("dash.onrender.com", settings.ALLOWED_HOSTS)
        self.assertIn("https://dash.onrender.com", settings.CSRF_TRUSTED_ORIGINS)


class DatabaseSwitchTests(SimpleTestCase):
    def tearDown(self):
        load_settings(DEBUG="True")

    def test_database_url_switches_to_postgresql(self):
        settings = load_settings(
            DATABASE_URL="postgresql://u:p@db.example.com:5432/dash"
        )
        database = settings.DATABASES["default"]
        self.assertEqual(database["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(database["HOST"], "db.example.com")
        self.assertEqual(database["CONN_MAX_AGE"], 600)

    def test_sqlite_without_a_database_url(self):
        settings = load_settings(DATABASE_URL="")
        self.assertEqual(
            settings.DATABASES["default"]["ENGINE"], "django.db.backends.sqlite3"
        )


class StaticFilesTests(SimpleTestCase):
    def test_whitenoise_serves_static_files_in_production(self):
        from django.conf import settings

        self.assertIn(
            "whitenoise.middleware.WhiteNoiseMiddleware", settings.MIDDLEWARE
        )
        # It must sit directly after SecurityMiddleware, per WhiteNoise's docs.
        index = settings.MIDDLEWARE.index("whitenoise.middleware.WhiteNoiseMiddleware")
        self.assertEqual(
            settings.MIDDLEWARE[index - 1],
            "django.middleware.security.SecurityMiddleware",
        )

    def test_static_root_is_set_for_collectstatic(self):
        from django.conf import settings

        self.assertTrue(str(settings.STATIC_ROOT).endswith("staticfiles"))


class SecretsTests(SimpleTestCase):
    def test_no_secret_is_hardcoded_for_the_api_key(self):
        """The key comes from the environment or the feature is unavailable."""
        from django.conf import settings

        self.assertFalse(hasattr(settings, "OPENAI_API_KEY"))

    def test_an_empty_secret_key_in_env_still_falls_back(self):
        # An empty DJANGO_SECRET_KEY= line in .env once satisfied os.environ.get's
        # default and left the key blank, which broke every signed cookie.
        settings = load_settings(DJANGO_SECRET_KEY="")
        self.assertTrue(settings.SECRET_KEY)
