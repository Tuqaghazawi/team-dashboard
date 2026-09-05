"""Peri-operative medication check for a dashboard patient.

The valuable part of the Session 3 module is its rule table — the deterministic
join between a patient's active drugs and the KHCC GDLPT-25 guideline, with the
stop-by date arithmetic. That is reused here unchanged (``load_rules`` and
``parse_stop_days`` from ``periop_flag``).

What changed is where the drugs come from. ``periop_flag`` reads a standalone
pharmacy database keyed by its own MRNs, which meant it could never see the
patients this dashboard tracks. Medications now live on the patient, synced from
the EHR, so the check runs on real patients.

The ``synced`` flag is the safety-critical part. "We have never read the EHR for
this patient" and "the EHR says this patient is on nothing to hold" produce the
same empty alert list, and they are not the same thing. The caller is told which.
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

PHARMACY_DIR = Path(__file__).resolve().parent


class PeriopUnavailable(RuntimeError):
    """The guideline rule table could not be read."""


def _rules():
    if str(PHARMACY_DIR) not in sys.path:
        sys.path.insert(0, str(PHARMACY_DIR))
    try:
        import periop_flag
    except Exception as exc:
        raise PeriopUnavailable(f"cannot load the peri-op rules: {exc}") from exc
    try:
        return periop_flag.load_rules(), periop_flag.parse_stop_days
    except Exception as exc:
        raise PeriopUnavailable(f"cannot read the guideline rules file: {exc}") from exc


def periop_alerts(patient, surgery_date):
    """Medication alerts for one patient before one operation.

    Returns::

        {
          "synced": bool,          # has the EHR ever been read for this patient?
          "synced_at": datetime | None,
          "checked": int,          # active medications considered
          "alerts": [ {drug, action, timing, stop_by, consult, high_alert}, ... ],
          "continued": [ ... ],    # active drugs the guideline says to continue
          "source": str,
        }
    """
    rules, parse_stop_days = _rules()
    surgery = _as_date(surgery_date)

    by_class = _rules_by_class(rules)
    medications = list(patient.medications.filter(active=True))
    alerts, continued, unmatched = [], [], []

    for medication in medications:
        rule = rules.get(medication.drug_name.lower())
        matched_by = "name"

        if rule is None:
            # The guideline matches on drug name alone, so a drug it does not
            # list by name is invisible to it — naproxen is an NSAID the table
            # never names, and the NSAID rule says discontinue. Fall back to the
            # drug's class so a whole class is not silently missed, and say that
            # is what happened.
            rule = by_class.get(_normalise(medication.drug_class))
            matched_by = "class"

        if rule is None:
            unmatched.append(
                {"drug": medication.drug_name, "drug_class": medication.drug_class}
            )
            continue

        if rule["action"] == "CONTINUE":
            continued.append({"drug": medication.drug_name, "drug_class": medication.drug_class})
            continue

        stop_days = parse_stop_days(rule["timing"])
        alerts.append(
            {
                "drug": medication.drug_name,
                "drug_class": medication.drug_class or rule["drug_class"],
                "high_alert": medication.high_alert,
                "action": "CONDITIONAL" if matched_by == "class" else rule["action"],
                "guideline_action": rule["action"],
                "matched_by": matched_by,
                "timing": rule["timing"],
                "rationale": rule["rationale"],
                "stop_by": surgery - timedelta(days=stop_days) if stop_days > 0 else None,
                "consult": rule["consult"],
            }
        )

    # Most urgent first: discontinue, then hold, then review.
    rank = {"DISCONTINUE": 0, "HOLD": 1, "CONDITIONAL": 2}
    alerts.sort(key=lambda a: (rank.get(a["action"], 9), a["drug"]))

    source = next(iter(rules.values()))["guideline_source"] if rules else ""
    return {
        "synced": patient.ehr_synced_at is not None,
        "synced_at": patient.ehr_synced_at,
        "checked": len(medications),
        "alerts": alerts,
        "continued": sorted(continued, key=lambda c: c["drug"]),
        # Neither named nor class-matched. Listed separately, never as "continue":
        # the guideline has said nothing about these, which is not the same as
        # having cleared them.
        "unmatched": sorted(unmatched, key=lambda c: c["drug"]),
        "source": source,
    }


def _rules_by_class(rules):
    """The strictest non-CONTINUE rule for each drug class."""
    rank = {"DISCONTINUE": 0, "HOLD": 1, "CONDITIONAL": 2}
    best = {}
    for rule in rules.values():
        if rule["action"] == "CONTINUE":
            continue
        key = _normalise(rule["drug_class"])
        if not key:
            continue
        current = best.get(key)
        if current is None or rank.get(rule["action"], 9) < rank.get(current["action"], 9):
            best[key] = rule
    return best


def _normalise(text):
    """Loose class key, so 'NSAID' and 'NSAIDs' match."""
    return (text or "").strip().lower().rstrip("s")


def _as_date(value):
    if isinstance(value, str):
        return datetime.strptime(value, "%Y-%m-%d").date()
    return value
