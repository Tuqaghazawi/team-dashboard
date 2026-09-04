"""
kappa.py — Cohen's kappa between the LLM judge and your human verdicts (Session 7).

Compares judge_verdicts.jsonl vs human_verdicts.jsonl on the items you labeled,
and reports agreement + Cohen's kappa (chance-corrected agreement).

Run from PROJECT ROOT:
  .venv\\Scripts\\python.exe -m ai.eval.kappa
"""
import json
from pathlib import Path

HERE = Path(__file__).parent
JUDGE = HERE / "judge_verdicts.jsonl"
HUMAN = HERE / "human_verdicts.jsonl"


def load(path):
    return {(r["id"], r["field"]): (r.get("verdict") or r.get("human"))
            for r in (json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip())}


def cohen_kappa(pairs):
    """pairs = list of (judge_label, human_label), each 'correct'/'incorrect'."""
    n = len(pairs)
    labels = ["correct", "incorrect"]
    # observed agreement
    agree = sum(1 for j, h in pairs if j == h)
    po = agree / n
    # expected agreement by chance
    pe = 0.0
    for lab in labels:
        pj = sum(1 for j, _ in pairs if j == lab) / n
        ph = sum(1 for _, h in pairs if h == lab) / n
        pe += pj * ph
    kappa = (po - pe) / (1 - pe) if pe != 1 else 1.0
    return po, pe, kappa, agree, n


def interpret(k):
    if k < 0: return "less than chance"
    if k < 0.20: return "slight"
    if k < 0.40: return "fair"
    if k < 0.60: return "moderate"
    if k < 0.80: return "substantial"
    return "almost perfect"


def main():
    judge, human = load(JUDGE), load(HUMAN)
    keys = sorted(set(human) & set(judge))       # only items you labeled
    if not keys:
        print("No overlapping items — run label_human first."); return
    pairs = [(judge[k], human[k]) for k in keys]
    po, pe, kappa, agree, n = cohen_kappa(pairs)

    print(f"Items compared: {n}")
    print(f"Raw agreement:  {agree}/{n} = {po:.0%}")
    print(f"Chance agreement (pe): {pe:.3f}")
    print(f"Cohen's kappa:  {kappa:.3f}  ({interpret(kappa)})")
    # show disagreements — useful for improving the judge prompt
    print("\nDisagreements (judge vs you):")
    any_dis = False
    for k in keys:
        if judge[k] != human[k]:
            any_dis = True
            print(f"  {k[0]} · {k[1]}: judge={judge[k]}  you={human[k]}")
    if not any_dis:
        print("  none")


if __name__ == "__main__":
    main()
