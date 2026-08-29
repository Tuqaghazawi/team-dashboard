"""
Inspect ONE note: show the source, the model's extraction, and the gold label
side by side, plus a field-by-field diff. Read it with your own eyes.

Run from PROJECT ROOT (pass a note id):
    .venv\\Scripts\\python.exe -m ai.eval.inspect breast_postop_02
"""
import json
import sys
from pathlib import Path

from ai.extraction.extract import extract_note

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLD = REPO_ROOT / "data" / "synthetic" / "breast" / "gold_breast.jsonl"


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m ai.eval.inspect <note_id>   e.g. breast_diag_01")
        return
    note_id = sys.argv[1]

    rows = [json.loads(l) for l in GOLD.read_text(encoding="utf-8").splitlines() if l.strip()]
    row = next((r for r in rows if r["id"] == note_id), None)
    if row is None:
        print(f"No note with id '{note_id}'. Available ids:")
        print(", ".join(r["id"] for r in rows))
        return

    print("=" * 70)
    print("THE NOTE (what the model reads):")
    print("=" * 70)
    print(row["text"])

    print("\n" + "=" * 70)
    print("THE MODEL'S EXTRACTION:")
    print("=" * 70)
    pred = extract_note(row["text"]).model_dump(mode="json")
    print(json.dumps(pred, indent=2, ensure_ascii=False))

    print("\n" + "=" * 70)
    print("THE GOLD LABEL (what we score against):")
    print("=" * 70)
    print(json.dumps(row["label"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()