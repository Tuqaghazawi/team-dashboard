"""
text_to_sql.py — ask the pharmacy database questions in plain English.

Flow:
  English question --[ LLM + your schema ]--> SQL --[ safety guard ]--> run --> answer

SAFETY: the LLM can suggest anything, so we NEVER trust it blindly. Every
generated query passes is_safe() first — it must be a single read-only SELECT.
A pharmacist's question must never be able to change or delete data.
"""
import re
import sqlite3
from pathlib import Path
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).parent
DB_PATH = ROOT / "pharmacy.db"
MODEL = "gpt-4o-mini"

# ---------------------------------------------------------------------------
# Ground the model in the real schema so it writes queries that actually run.
# This is the prompt-engineering core of Part 3: the model can only be as good
# as the schema you describe to it.
# ---------------------------------------------------------------------------
SCHEMA_DESCRIPTION = """
Tables in this SQLite database:

patients(patient_id, mrn, age, sex, ward)
medications(medication_id, drug_name, drug_class, form, strength, high_alert)   -- high_alert: 1=yes 0=no
orders(order_id, patient_id, medication_id, dose, route, frequency, order_status, start_date, prescriber)
        -- order_status is one of 'active','discontinued','on hold'
drug_interactions(interaction_id, note_id, drug_a, drug_b, severity, mechanism, evidence_span)

Relationships:
  orders.patient_id    -> patients.patient_id
  orders.medication_id -> medications.medication_id
Drug names are stored capitalised, e.g. 'Warfarin'.
"""

SYSTEM_PROMPT = (
    "You translate a pharmacist's plain-English question into ONE SQLite query. "
    "Use only the tables and columns in the schema. Return a single SELECT "
    "statement, read-only, no INSERT/UPDATE/DELETE/DROP. Do not add explanation.\n\n"
    + SCHEMA_DESCRIPTION
)


class SQLQuery(BaseModel):
    sql: str


# ---------------------------------------------------------------------------
# SAFETY GUARD -- given. Rejects anything that isn't a single read-only SELECT.
# ---------------------------------------------------------------------------
FORBIDDEN = ["insert", "update", "delete", "drop", "alter", "create",
             "replace", "truncate", "attach", "detach", "pragma"]


def is_safe(sql):
    s = sql.strip().rstrip(";").strip().lower()
    if not s.startswith("select"):
        return False, "not a SELECT"
    if ";" in s:                                   # block multiple statements
        return False, "multiple statements"
    for word in FORBIDDEN:
        if re.search(rf"\b{word}\b", s):
            return False, f"forbidden keyword: {word}"
    return True, "ok"


def to_sql(question):
    """Ask the LLM for a query. Returns the SQL string."""
    client = OpenAI()
    resp = client.responses.parse(
        model=MODEL,
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ],
        text_format=SQLQuery,
    )
    return resp.output_parsed.sql


def run_readonly(sql):
    """Execute the query. Opened read-only so it physically CANNOT write."""
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(sql).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def ask(question):
    print(f"\nQ: {question}")
    sql = to_sql(question)
    print(f"SQL: {sql}")
    ok, reason = is_safe(sql)
    if not ok:
        print(f"BLOCKED ({reason}) — query not run.")
        return
    rows = run_readonly(sql)
    print(f"{len(rows)} result(s):")
    for r in rows[:15]:
        print("  ", r)


if __name__ == "__main__":
    ask("Which patients are on warfarin?")
    ask("List all high-alert medications.")
    ask("How many active orders are there per ward?")
    # TODO: add a question of your own here
