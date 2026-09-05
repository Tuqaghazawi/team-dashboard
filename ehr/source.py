"""Read-only access to the hospital EHR tables.

This stands in for the real integration. The dashboard never writes here and
never assumes the EHR is reachable — every call can raise
:class:`EHRUnavailable`, and the caller degrades rather than failing a clinical
page.

The synthetic EHR is a SQLite file keyed by the patient's own MRN, which is what
a real integration would key on. Swapping this module for a hospital connector
(an HL7/FHIR client, a linked-server view) is the whole of the migration: the
two functions below are the entire surface the rest of the app uses.
"""

import os
import sqlite3
from contextlib import closing
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "data" / "synthetic" / "ehr.sqlite3"


class EHRUnavailable(RuntimeError):
    """The EHR could not be reached or read."""


def database_path():
    """Where the EHR lives. Overridable so tests can point at their own copy."""
    return Path(os.environ.get("EHR_DATABASE", DEFAULT_PATH))


def _connect():
    path = database_path()
    if not path.exists():
        raise EHRUnavailable(
            f"no EHR at {path} — run 'python manage.py build_ehr' to create the "
            f"synthetic one"
        )
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def results_for(mrn):
    """Every result the EHR holds for one MRN, finalised or still pending."""
    try:
        with closing(_connect()) as connection:
            rows = connection.execute(
                """
                SELECT test_code, purpose, status, resulted_on, report
                FROM ehr_results
                WHERE mrn = ?
                ORDER BY resulted_on
                """,
                (mrn,),
            ).fetchall()
    except sqlite3.Error as exc:
        raise EHRUnavailable(str(exc)) from exc
    return [dict(row) for row in rows]


def medications_for(mrn):
    """Every medication order the EHR holds for one MRN."""
    try:
        with closing(_connect()) as connection:
            rows = connection.execute(
                """
                SELECT drug_name, drug_class, high_alert, status, started_on
                FROM ehr_medications
                WHERE mrn = ?
                ORDER BY drug_name
                """,
                (mrn,),
            ).fetchall()
    except sqlite3.Error as exc:
        raise EHRUnavailable(str(exc)) from exc
    return [dict(row) for row in rows]


def known_mrn(mrn):
    """Whether the EHR has this patient at all."""
    try:
        with closing(_connect()) as connection:
            row = connection.execute(
                "SELECT 1 FROM ehr_patients WHERE mrn = ?", (mrn,)
            ).fetchone()
    except sqlite3.Error as exc:
        raise EHRUnavailable(str(exc)) from exc
    return row is not None
