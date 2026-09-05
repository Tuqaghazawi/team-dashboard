"""Peri-operative medication check, as a return value rather than printed output.

This reuses the Session 3 rule logic in ``periop_flag`` — the deterministic join
between a patient's active orders and the KHCC GDLPT-25 guideline — and returns
structured alerts the dashboard can render.

The one thing it adds is an explicit ``linked`` flag. The pharmacy database is a
separate synthetic system keyed by its own MRNs, so a dashboard patient may have
no record in it at all. "We found no medication record for this patient" and
"this patient has no medications to hold" look identical if you only count
alerts, and they are not the same thing — one is a safe result, the other is a
gap. The caller is told which it is.
"""

import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

PHARMACY_DIR = Path(__file__).resolve().parent
DB_PATH = PHARMACY_DIR / "pharmacy.db"


class PeriopUnavailable(RuntimeError):
    """The pharmacy database or the guideline rules could not be read."""


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


def periop_alerts(pharmacy_mrn, surgery_date):
    """Medication alerts for one patient before one operation.

    Returns::

        {
          "linked": bool,        # was this MRN found in the pharmacy database?
          "orders_checked": int,
          "alerts": [ {drug, action, timing, stop_by, consult, high_alert}, ... ],
          "source": str,
        }
    """
    if not pharmacy_mrn:
        return {"linked": False, "orders_checked": 0, "alerts": [], "source": ""}
    if not DB_PATH.exists():
        raise PeriopUnavailable(
            "pharmacy.db has not been built — run ai/pharmacy/db_skeleton.py"
        )

    rules, parse_stop_days = _rules()
    surgery = _as_date(surgery_date)

    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        known = connection.execute(
            "SELECT 1 FROM patients WHERE mrn = ?", (pharmacy_mrn,)
        ).fetchone()
        orders = connection.execute(
            """
            SELECT m.drug_name, m.drug_class, m.high_alert
            FROM orders o
            JOIN patients p    ON p.patient_id = o.patient_id
            JOIN medications m ON m.medication_id = o.medication_id
            WHERE p.mrn = ? AND o.order_status = 'active'
            """,
            (pharmacy_mrn,),
        ).fetchall()
    finally:
        connection.close()

    alerts = []
    for order in orders:
        rule = rules.get(order["drug_name"].lower())
        if not rule or rule["action"] == "CONTINUE":
            continue
        stop_days = parse_stop_days(rule["timing"])
        alerts.append(
            {
                "drug": order["drug_name"],
                "drug_class": order["drug_class"],
                "high_alert": bool(order["high_alert"]),
                "action": rule["action"],
                "timing": rule["timing"],
                "stop_by": surgery - timedelta(days=stop_days) if stop_days > 0 else None,
                "consult": rule["consult"],
            }
        )

    # Most urgent first: discontinue, then hold, then review.
    order_of = {"DISCONTINUE": 0, "HOLD": 1, "CONDITIONAL": 2}
    alerts.sort(key=lambda a: (order_of.get(a["action"], 9), a["drug"]))

    source = next(iter(rules.values()))["guideline_source"] if rules else ""
    return {
        "linked": known is not None,
        "orders_checked": len(orders),
        "alerts": alerts,
        "source": source,
    }


def _as_date(value):
    if isinstance(value, str):
        return datetime.strptime(value, "%Y-%m-%d").date()
    return value
