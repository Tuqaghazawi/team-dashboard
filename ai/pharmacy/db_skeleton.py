"""
db.py — YOUR build.  Load medication_orders.csv into a SQLite database.

The point is the Python reps, not the SQL: a loop, dicts used as lookups,
and the sqlite3 module. Fill in each TODO. One worked example (patients)
is given — copy its *shape* for medications and orders.

Stuck? The finished version is in db.py. Peek only after trying.
"""
import csv
import sqlite3
from pathlib import Path

ROOT = Path(__file__).parent
DB_PATH = ROOT / "pharmacy.db"
CSV_PATH = ROOT / "data" / "medication_orders.csv"

# ---------------------------------------------------------------------------
# SCHEMA is GIVEN. Read it, don't rewrite it — it's the "shape" of the db.
# Notice the keys:
#   PRIMARY KEY = unique id for a row in THIS table
#   REFERENCES  = foreign key: this column must match a primary key elsewhere
# ---------------------------------------------------------------------------
SCHEMA = """
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS medications;
DROP TABLE IF EXISTS patients;
DROP TABLE IF EXISTS drug_interactions;
DROP TABLE IF EXISTS consultation_notes;

CREATE TABLE patients (
    patient_id INTEGER PRIMARY KEY,
    mrn        TEXT UNIQUE NOT NULL,
    age        INTEGER,
    sex        TEXT,
    ward       TEXT
);

CREATE TABLE medications (
    medication_id INTEGER PRIMARY KEY,
    drug_name     TEXT UNIQUE NOT NULL,
    drug_class    TEXT,
    form          TEXT,
    strength      TEXT,
    high_alert    INTEGER DEFAULT 0
);

CREATE TABLE orders (
    order_id      INTEGER PRIMARY KEY,
    patient_id    INTEGER NOT NULL REFERENCES patients(patient_id),
    medication_id INTEGER NOT NULL REFERENCES medications(medication_id),
    dose          TEXT,
    route         TEXT,
    frequency     TEXT,
    order_status  TEXT,
    start_date    TEXT,
    prescriber    TEXT
);

CREATE TABLE consultation_notes (
    note_id    INTEGER PRIMARY KEY,
    patient_id INTEGER REFERENCES patients(patient_id),
    note_date  TEXT,
    author     TEXT,
    note_text  TEXT
);

CREATE TABLE drug_interactions (
    interaction_id INTEGER PRIMARY KEY,
    note_id        INTEGER REFERENCES consultation_notes(note_id),
    drug_a         TEXT,
    drug_b         TEXT,
    severity       TEXT,
    mechanism      TEXT,
    evidence_span  TEXT,
    confidence     REAL
);
"""


def build():
    # -- TODO 1 -- Connect to the database, then get a cursor.
    # Q: which sqlite3 function opens (or creates) the .db file and returns a
    #    connection? And which method of that connection gives you a cursor?
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
  

    # -- TODO 2 -- Create all 5 tables.
    # Q: cur.execute() runs ONE statement. SCHEMA holds many (split by ';').
    #    Which cursor method runs a whole *script* at once?
    cur.executescript(SCHEMA)
          

  
    patients = {}
    meds = {}
    p_id = 0
    m_id = 0

    # -- TODO 3 -- Open the CSV and loop its rows.
    # Q: which csv reader yields each row as a dict, so you can write
    #    row["mrn"] instead of row[1]?
    with open(CSV_PATH, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
         

            # -- TODO 4 -- Patient upsert.  *** WORKED EXAMPLE — study it ***
            # The CSV repeats the same mrn on every order for that patient,
            # but patients should get ONE row each. So: only insert an mrn the
            # first time you see it. The '?' are placeholders sqlite fills in
            # safely (never paste values straight into SQL — that's an
            # injection risk, and it matters again in Part 3).
            if row["mrn"] not in patients:
                p_id += 1
                patients[row["mrn"]] = p_id
                cur.execute(
                    "INSERT INTO patients (patient_id, mrn, age, sex, ward) "
                    "VALUES (?,?,?,?,?)",
                    (p_id, row["mrn"], int(row["patient_age"]),
                     row["patient_sex"], row["ward"]),
                )

            # -- TODO 5 -- Medication upsert.  YOUR TURN.
            # Same shape as TODO 4, but keyed on row["drug_name"] and writing
            # into medications. Q: which columns does medications need, and
            # which CSV fields fill them? (check SCHEMA + the csv header)
            if row["drug_name"] not in meds:
                m_id += 1
                meds[row["drug_name"]] = m_id
                cur.execute(
                    "INSERT INTO medications (medication_id, drug_name, drug_class, form, strength, high_alert) "
                    "VALUES (?,?,?,?,?,?)",
                    (m_id, row["drug_name"], row["drug_class"], row["form"],
                     row["strength"], int(row["high_alert"])),
                )

            # -- TODO 6 -- Insert the order.  YOUR TURN.
            # Q: orders needs patient_id and medication_id, but the CSV only
            #    has mrn and drug_name. Where do the integer ids come from?
            #    (hint: you just stored them in the two dicts.)
            cur.execute(
                "INSERT INTO orders (order_id, patient_id, medication_id, dose, route, frequency, order_status, start_date, prescriber) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (int(row["order_id"]), patients[row["mrn"]], meds[row["drug_name"]],
                 row["dose"], row["route"], row["frequency"],
                 row["order_status"], row["start_date"], row["prescriber"]),
            )

    # -- TODO 7 -- Save and report.
    # Q: your inserts aren't actually written to the file until you call what
    #    on the connection? After that, SELECT COUNT(*) each table to confirm.
        conn.commit()

    for table in ["patients", "medications", "orders"]:
        count = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"{table}: {count} rows")

    conn.close()


if __name__ == "__main__":
    build()
    print("done — open pharmacy.db and check the tables")