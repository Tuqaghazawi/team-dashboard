"""
extract.py — YOUR build.  Part 2, step 1: pull drug interactions out of notes.

Two new ideas here:
  1. A Pydantic MODEL = you describe the SHAPE of the data you want (a class).
  2. OpenAI structured output = you hand that shape to the model, and it returns
     data already built to fit it — no messy text parsing.

Run order (important):
  A. First run the Pydantic-only test at the bottom -> needs NO API key.
     Proves your model works before you spend a single API call.
  B. Then run the real extraction -> needs your OPENAI_API_KEY set.

The finished reference will be extract.py; try each TODO before peeking.
"""
import csv
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).parent
NOTES_CSV = ROOT / "data" / "consultation_notes.csv"
MODEL = "gpt-4o-mini"          # cheap + supports structured output; swap if Iyad says otherwise

client = OpenAI()              # automatically reads OPENAI_API_KEY from your environment


# ===========================================================================
# TODO 1 -- Define the SHAPE of ONE drug interaction.
# A Pydantic model is a class: each line is "field_name: type".
# Two fields are given as worked examples. Add the remaining THREE.
# ===========================================================================
class DrugInteraction(BaseModel):
    drug_a: str = Field(description="first drug in the interacting pair")     # worked example
    drug_b: str = Field(description="second drug in the interacting pair")    # worked example
    severity: Literal["contraindicated", "major", "moderate", "minor"]
    mechanism: str
    evidence_span: str



# ===========================================================================
# TODO 2 -- Define the CONTAINER the model returns for one whole note.
# A note may contain zero, one, or many interactions.
# Q: what type holds "a list of DrugInteraction"?  ->  list[DrugInteraction]
# ===========================================================================
class NoteExtraction(BaseModel):
    interactions: list[DrugInteraction]      # <-- this is the pattern; leave as is


# ===========================================================================
# The extraction call -- GIVEN. Read it; you don't need to write API syntax.
# The only thing that's YOURS is the system prompt (that's the prompt
# engineering this course is about). A simple v1 is provided; you'll refine it
# after you see where it fails.
# ===========================================================================
SYSTEM_PROMPT = (
    "You are a clinical pharmacist assistant. Read the clinical note and extract "
    "every drug-drug interaction it describes. Only report interactions the note "
    "actually states or clearly implies. Do NOT invent interactions. If the note "
    "describes none, return an empty list. Use the note's own wording for evidence_span."
)


def extract(note_text: str) -> NoteExtraction:
    response = client.responses.parse(
        model=MODEL,
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": note_text},
        ],
        text_format=NoteExtraction,       # <-- hand your shape to the model
    )
    return response.output_parsed         # <-- comes back as a NoteExtraction object


def run_on_all_notes():
    with open(NOTES_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            result = extract(row["note_text"])
            print(f"\nNote {row['note_id']} ({row['mrn']}):")
            if not result.interactions:
                print("   no interactions found")
            for i in result.interactions:
                print(f"   {i.drug_a} + {i.drug_b}  [{i.severity}]  {i.mechanism}")


# ===========================================================================
# Run A -- Pydantic-only test (NO API key needed). Run this FIRST.
# It builds one interaction by hand to prove your model from TODO 1 works.
# ===========================================================================
def test_pydantic_only():
    demo = DrugInteraction(
        drug_a="Warfarin",
        drug_b="Ibuprofen",
        severity="major",
        mechanism="additive bleeding risk",
        evidence_span="bleeding risk from concurrent warfarin and NSAID",
    )
    print("Pydantic model works! ->", demo)


if __name__ == "__main__":
    # test_pydantic_only()        # start here (no key)
    run_on_all_notes()        # uncomment AFTER your key is set
    import sqlite3
DB_PATH = ROOT / "pharmacy.db"

def store_all_interactions():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM drug_interactions")   # clear old runs so re-running doesn't duplicate
    total = 0
    with open(NOTES_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            result = extract(row["note_text"])
            for i in result.interactions:
                cur.execute(
                    "INSERT INTO drug_interactions "
                    "(note_id, drug_a, drug_b, severity, mechanism, evidence_span) "
                    "VALUES (?,?,?,?,?,?)",
                    (int(row["note_id"]), i.drug_a, i.drug_b,
                     i.severity, i.mechanism, i.evidence_span),
                )
                total += 1
        conn.commit()
    conn.close()
    print(f"Stored {total} interactions into drug_interactions")


if __name__ == "__main__":
    store_all_interactions()