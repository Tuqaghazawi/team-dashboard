"""
periop_flag.py — surgeon-facing pre-op medication alert.

For a given patient + surgery date, it:
  1. pulls the patient's ACTIVE orders from the database (Part 1 data)
  2. matches each drug BY NAME to the KHCC guideline rules (perioperative_rules.csv)
  3. for anything that must be held/stopped, computes the stop-by date
  4. prints an alert with the timing, the reason, and who to consult

No LLM here — this is a deterministic join + date math. The model's job
(Part 2) was reading text; this part must be trustworthy, so it's plain code.

Change the patient/date at the very bottom to check anyone.
"""
import csv
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).parent
DB_PATH = ROOT / "pharmacy.db"
RULES_CSV = ROOT / "data" / "perioperative_rules.csv"

ICON = {"DISCONTINUE": "[STOP]", "HOLD": "[HOLD]", "CONDITIONAL": "[REVIEW]"}


def load_rules():
    """Build a lookup: drug_name (lowercase) -> its guideline rule.
    Simple NAME match: each rule lists example drugs; we map every one."""
    rules = {}
    with open(RULES_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            for drug in row["example_drugs"].split(";"):
                drug = drug.strip().lower()
                if drug:
                    rules[drug] = row
    return rules


def parse_stop_days(timing):
    """Pull a CONSERVATIVE number of days from free-text timing.
    Safety rule: if a range is given, take the LARGEST number (earliest stop).
    'weeks' -> x7.  'morning of surgery' / hours -> 0 (day of surgery)."""
    t = timing.lower()
    nums = [int(n) for n in re.findall(r"\d+", t)]
    if "week" in t:
        return max(nums) * 7 if nums else 0
    if "day" in t:
        return max(nums) if nums else 0
    return 0


def periop_check(mrn, surgery_date):
    rules = load_rules()
    surg = datetime.strptime(surgery_date, "%Y-%m-%d").date()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    orders = conn.execute(
        """
        SELECT m.drug_name, m.drug_class, m.high_alert
        FROM orders o
        JOIN patients p    ON p.patient_id = o.patient_id
        JOIN medications m ON m.medication_id = o.medication_id
        WHERE p.mrn = ? AND o.order_status = 'active'
        """,
        (mrn,),
    ).fetchall()
    conn.close()

    print(f"\n=== PRE-OP MEDICATION ALERTS — {mrn} | surgery {surgery_date} ===")
    flags = 0
    for o in orders:
        rule = rules.get(o["drug_name"].lower())
        if rule and rule["action"] != "CONTINUE":
            stop_days = parse_stop_days(rule["timing"])
            stop_by = surg - timedelta(days=stop_days)
            tag = ICON.get(rule["action"], "[FLAG]")
            line = f'{tag} {o["drug_name"]:16} {rule["action"]:11} {rule["timing"]}'
            if stop_days > 0:
                line += f'  -> last dose by {stop_by}'
            if rule["consult"]:
                line += f'  | refer {rule["consult"]}'
            print("  " + line)
            flags += 1

    if flags == 0:
        print("  No medication holds flagged.")
    print(f"  ({len(orders)} active meds checked, {flags} flagged) "
          f"[source: {list(rules.values())[0]['guideline_source']}]")


if __name__ == "__main__":
    # Demo patients (from your data). Change MRN / date to check anyone.
    periop_check("MRN4003", "2026-09-15")   # on ibuprofen, simvastatin, metformin, spironolactone
    periop_check("MRN4007", "2026-09-15")   # on warfarin + heparin
    periop_check("MRN4004", "2026-09-15")   # on naproxen + enoxaparin