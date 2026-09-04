"""
label_human.py — capture YOUR expert verdicts to validate the judge (Session 7).

Shows a sample of (field, gold, extracted) items and asks you, the clinician,
to rate each: correct or incorrect. Your labels are the human ground truth that
Cohen's kappa measures the judge against.

Run from PROJECT ROOT:
  .venv\\Scripts\\python.exe -m ai.eval.label_human          # default 25 items
  .venv\\Scripts\\python.exe -m ai.eval.label_human 30       # 30 items
Output: ai/eval/human_verdicts.jsonl
"""
import json
import sys
import random
from pathlib import Path

from ai.extraction.extract import extract_note

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLD = REPO_ROOT / "data" / "synthetic" / "gold.jsonl"
VERDICTS = Path(__file__).parent / "judge_verdicts.jsonl"     # to sample the SAME items
OUT = Path(__file__).parent / "human_verdicts.jsonl"

KEY_FIELDS = ["histology", "pathology.grade", "pathology.margins",
              "pathology.lymphovascular_invasion", "tnm.t", "tnm.n"]


def get_path(obj, path):
    cur = obj
    for part in path.split("."):
        if not isinstance(cur, dict) or cur.get(part) is None:
            return None
        cur = cur[part]
    return cur


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 25
    # sample the exact (id, field) items the judge already scored, so kappa compares like-for-like
    judged = [json.loads(l) for l in VERDICTS.read_text(encoding="utf-8").splitlines() if l.strip()]
    random.seed(7)
    sample = random.sample(judged, min(n, len(judged)))

    gold_rows = {r["id"]: r for r in
                 (json.loads(l) for l in GOLD.read_text(encoding="utf-8").splitlines() if l.strip())}

    # re-extract each needed note once, cache
    preds = {}
    def pred_for(nid):
        if nid not in preds:
            preds[nid] = extract_note(gold_rows[nid]["text"]).model_dump(mode="json")
        return preds[nid]

    print(f"Rating {len(sample)} items. For each: is the EXTRACTED value clinically correct vs GOLD?")
    print("Type  c = correct,  i = incorrect,  q = quit & save.\n")

    out = []
    for k, item in enumerate(sample, 1):
        nid, field = item["id"], item["field"]
        gold_val = get_path(gold_rows[nid]["label"], field)
        pred_val = get_path(pred_for(nid), field)
        print(f"[{k}/{len(sample)}] {nid} · {field}")
        print(f"      GOLD:      {gold_val!r}")
        print(f"      EXTRACTED: {pred_val!r}")
        ans = ""
        while ans not in ("c", "i", "q"):
            ans = input("      your verdict (c/i/q): ").strip().lower()
        if ans == "q":
            break
        out.append({"id": nid, "field": field,
                    "human": "correct" if ans == "c" else "incorrect"})
        print()

    OUT.write_text("\n".join(json.dumps(o) for o in out) + "\n", encoding="utf-8")
    print(f"\nSaved {len(out)} human verdicts -> {OUT.name}")


if __name__ == "__main__":
    main()
