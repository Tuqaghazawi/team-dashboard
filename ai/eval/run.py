"""
run.py — end-to-end evaluation pipeline for the extraction tool (Session 7).

ONE command runs the whole suite over the gold set, extracting each case once:
  - Functional evaluator   (exact-match field accuracy, misses, fabrications)
  - LLM-as-judge           (semantic correctness on key clinical fields)
  - Clinical safety metrics (contraindication recall, refusal calibration,
                             hallucination rate)
  - Cohen's kappa          (aligned judge vs your human verdicts, if present)

Run from PROJECT ROOT:
  .venv\\Scripts\\python.exe -m ai.eval.run
"""
import json
from pathlib import Path

from ai.extraction.extract import extract_note
from ai.eval.accuracy import SCORED_FIELDS, INFERABLE, get_path, norm
from ai.eval.judge import judge_case, KEY_FIELDS
from ai.eval.safety_metrics import CRITICAL_RULES
from ai.eval.kappa import load as load_verdicts, cohen_kappa, interpret

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLD = REPO_ROOT / "data" / "synthetic" / "gold.jsonl"
JUDGE_OUT = Path(__file__).parent / "judge_verdicts.jsonl"
HUMAN = Path(__file__).parent / "human_verdicts.jsonl"


def main():
    rows = [json.loads(l) for l in GOLD.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"Evaluating {len(rows)} cases (one extraction each)...\n")

    f_checked = f_correct = misses = fabs = fab_opps = 0
    j_correct = j_total = 0
    crit_total = crit_caught = 0
    crit_miss = []
    rev_t = rev_caught = rev_f = rev_fa = 0
    judge_lines = []

    for i, row in enumerate(rows, 1):
        gold = row["label"]
        try:
            pred = extract_note(row["text"]).model_dump(mode="json")
        except Exception as e:
            print(f"[{i}/{len(rows)}] {row.get('id')}: ERROR {e}"); continue

        # --- functional evaluator + hallucination opportunities ---
        for f in SCORED_FIELDS:
            gv, pv = get_path(gold, f), get_path(pred, f)
            if gv is not None:
                f_checked += 1
                if norm(pv) == norm(gv):
                    f_correct += 1
                elif pv is None:
                    misses += 1
            else:
                fab_opps += 1
                if pv is not None and f not in INFERABLE:
                    fabs += 1

        # --- LLM judge (key fields) ---
        jf = [{"field": f, "gold": get_path(gold, f), "pred": get_path(pred, f)}
              for f in KEY_FIELDS if get_path(gold, f) is not None]
        if jf:
            for v in judge_case(jf):
                j_total += 1
                if v.verdict.lower().startswith("correct"):
                    j_correct += 1
                judge_lines.append(json.dumps({
                    "id": row.get("id"), "field": v.field,
                    "verdict": v.verdict.lower(), "reason": v.reason}))

        # --- contraindication recall ---
        for field, is_crit in CRITICAL_RULES:
            g = get_path(gold, field)
            if g is not None and is_crit(g):
                crit_total += 1
                if norm(get_path(pred, field)) == norm(g):
                    crit_caught += 1
                else:
                    crit_miss.append((row.get("id"), field, g, get_path(pred, field)))

        # --- refusal calibration ---
        if get_path(gold, "meta.needs_human_review") is True:
            rev_t += 1
            rev_caught += 1 if get_path(pred, "meta.needs_human_review") is True else 0
        else:
            rev_f += 1
            rev_fa += 1 if get_path(pred, "meta.needs_human_review") is True else 0

        print(f"[{i}/{len(rows)}] {row.get('id')}: done")

    JUDGE_OUT.write_text("\n".join(judge_lines) + "\n", encoding="utf-8")

    # ---------------- report ----------------
    print("\n" + "=" * 60)
    print("EVALUATION REPORT — clinical extraction tool")
    print("=" * 60)

    print("\n[1] FUNCTIONAL EVALUATOR (exact match)")
    if f_checked:
        print(f"    field accuracy: {f_correct}/{f_checked} = {f_correct/f_checked:.0%}")
    print(f"    misses (gold had it, tool null): {misses}")

    print("\n[2] LLM-AS-JUDGE (semantic, key fields)")
    if j_total:
        print(f"    judged correct: {j_correct}/{j_total} = {j_correct/j_total:.0%}")

    print("\n[3] CLINICAL SAFETY METRICS")
    if crit_total:
        print(f"    contraindication recall: {crit_caught}/{crit_total} = {crit_caught/crit_total:.0%}")
    for nid, f, g, p in crit_miss:
        print(f"       MISSED: {nid} · {f}  gold={g!r} tool={p!r}")
    if rev_t:
        print(f"    refusal recall: {rev_caught}/{rev_t} = {rev_caught/rev_t:.0%}"
              f"   false alarms: {rev_fa}/{rev_f}")
    if fab_opps:
        print(f"    hallucination rate: {fabs}/{fab_opps} = {fabs/fab_opps:.1%}")

    print("\n[4] JUDGE VALIDATION (Cohen's kappa vs human verdicts)")
    if HUMAN.exists():
        judge, human = load_verdicts(JUDGE_OUT), load_verdicts(HUMAN)
        keys = sorted(set(judge) & set(human))
        if keys:
            pairs = [(judge[k], human[k]) for k in keys]
            po, pe, kappa, agree, n = cohen_kappa(pairs)
            print(f"    items: {n}   agreement: {agree}/{n}   kappa: {kappa:.3f} ({interpret(kappa)})")
        else:
            print("    (no overlapping labeled items)")
    else:
        print("    (no human_verdicts.jsonl — run label_human to validate)")

    print("\nDone.")


if __name__ == "__main__":
    main()
