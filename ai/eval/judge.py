"""
judge.py — LLM-as-judge evaluator (Session 7).

Your accuracy.py does EXACT-match (functional evaluator). It marks
"invasive lobular carcinoma" wrong when gold says "ILC" — even though they
are the same thing. This judge grades SEMANTIC equivalence, catching those.

For each case it extracts the note, then asks an LLM judge whether each key
clinical field is clinically equivalent to gold. Writes per-field verdicts.

Run from PROJECT ROOT:
  .venv\\Scripts\\python.exe -m ai.eval.judge 8      # first 8 cases (quick test)
  .venv\\Scripts\\python.exe -m ai.eval.judge         # all 39 cases
Output: ai/eval/judge_verdicts.jsonl
"""
import json
import sys
from pathlib import Path

from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv

from ai.extraction.extract import extract_note

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLD = REPO_ROOT / "data" / "synthetic" / "gold.jsonl"
OUT = Path(__file__).parent / "judge_verdicts.jsonl"
JUDGE_MODEL = "gpt-4o-mini"          # the judge — its reliability is what Step 2 validates
client = OpenAI()

# focused, semantically-meaningful fields (where exact-match is blind)
KEY_FIELDS = [
    "histology",
    "pathology.grade",
    "pathology.margins",
    "pathology.lymphovascular_invasion",
    "tnm.t",
    "tnm.n",
]


def get_path(obj: dict, path: str):
    cur = obj
    for part in path.split("."):
        if not isinstance(cur, dict) or cur.get(part) is None:
            return None
        cur = cur[part]
    return cur


class Verdict(BaseModel):
    field: str
    verdict: str          # "correct" | "incorrect"
    reason: str


class JudgeResult(BaseModel):
    verdicts: list[Verdict]


JUDGE_SYSTEM = (
    "You are a pathology data QA reviewer. For each field you are given the GOLD "
    "value and the EXTRACTED value. Decide whether the extracted value is CLINICALLY "
    "EQUIVALENT to the gold value. Accept synonyms, abbreviations, and formatting "
    "differences (e.g. 'ILC' == 'invasive lobular carcinoma'; 'grade 3 of 3' == '3'; "
    "'negative' == 'not involved'; 'pT2' == 'T2'). Mark 'incorrect' only for a real "
    "clinical mismatch or a missing (null) extracted value. Give a short reason per field."
)


def judge_case(fields):
    listing = "\n".join(
        f"- {f['field']}: GOLD={f['gold']!r}  EXTRACTED={f['pred']!r}" for f in fields
    )
    resp = client.responses.parse(
        model=JUDGE_MODEL,
        input=[
            {"role": "system", "content": JUDGE_SYSTEM},
            {"role": "user", "content": f"Grade each field:\n{listing}"},
        ],
        text_format=JudgeResult,
    )
    return resp.output_parsed.verdicts


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    rows = [json.loads(l) for l in GOLD.read_text(encoding="utf-8").splitlines() if l.strip()]
    if limit:
        rows = rows[:limit]

    n_correct = n_total = 0
    with open(OUT, "w", encoding="utf-8") as out:
        for i, row in enumerate(rows, 1):
            gold = row["label"]
            pred = extract_note(row["text"]).model_dump(mode="json")

            fields = []
            for f in KEY_FIELDS:
                g = get_path(gold, f)
                if g is None:
                    continue                       # only grade fields gold actually has
                fields.append({"field": f, "gold": g, "pred": get_path(pred, f)})
            if not fields:
                print(f"[{i}/{len(rows)}] {row.get('id')}: no key fields"); continue

            for v in judge_case(fields):
                n_total += 1
                if v.verdict.lower().startswith("correct"):
                    n_correct += 1
                out.write(json.dumps({
                    "id": row.get("id"), "field": v.field,
                    "verdict": v.verdict.lower(), "reason": v.reason,
                }) + "\n")
            print(f"[{i}/{len(rows)}] {row.get('id')}: {len(fields)} fields graded")

    print(f"\nJudge: {n_correct}/{n_total} field extractions judged correct "
          f"({n_correct/n_total:.0%})" if n_total else "no fields graded")
    print(f"Verdicts -> {OUT.name}")


if __name__ == "__main__":
    main()
