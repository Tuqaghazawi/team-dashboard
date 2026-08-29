"""
Clinical Extraction System - the extractor (Capstone 1).
Turns ONE unstructured oncology note into a validated ClinicalExtraction.

Run a quick test from your PROJECT ROOT:
    .venv\\Scripts\\python.exe -m ai.extraction.extract
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from ai.extraction.schemas import ClinicalExtraction

# --- config ---
MODEL = "gpt-5.6"   # change to whatever model your course used / your key can access

# --- load the API key from .env, then open a client ---
load_dotenv()        # reads .env into the environment
client = OpenAI()    # automatically picks up OPENAI_API_KEY

# --- the instruction that makes extraction safe ---
SYSTEM_PROMPT = """You extract structured data from oncology clinical notes for a tumor board.

Fill the provided schema from the note. Follow these rules exactly:
1. Only use information explicitly stated in the note. If a field is not
   stated, leave it null/empty. Never infer, guess, or add a "typical" value.
2. For every field you DO fill, copy the exact text snippet it came from into
   meta.evidence_spans.
3. If a field you would clinically expect is not present, list its name in
   meta.missing_fields.
4. Set meta.needs_human_review to true if the note is ambiguous or you are
   unsure which document_type it is.
5. Copy biomarker results verbatim (e.g. "positive (95%)", "3+", "MSI-high").
6. Choose document_type from what the note actually is (pathology, radiology,
   discharge_summary, or other).
"""


def extract_note(note_text: str) -> ClinicalExtraction:
    """Send one note to the model and get back a validated extraction."""
    completion = client.chat.completions.parse(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": note_text},
        ],
        response_format=ClinicalExtraction,    # <-- your schema, handed to OpenAI
    )
    return completion.choices[0].message.parsed


# --- quick manual test: run this file directly to try one note ---
if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parents[2]
    note_path = repo_root / "data" / "synthetic" / "notes" / "breast_postop_01.txt"
    note_text = note_path.read_text(encoding="utf-8")

    result = extract_note(note_text)
    print(result.model_dump_json(indent=2))