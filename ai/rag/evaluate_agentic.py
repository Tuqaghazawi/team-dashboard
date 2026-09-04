"""
evaluate_agentic.py — score the grade-and-retry system (the 'after' scorecard).

Identical to evaluate_rag.py, but each answer comes from answer_agentic().
Run this, compare the summary table to your baseline = your metric deltas.
"""
import os
os.environ.setdefault("DEEPEVAL_PER_ATTEMPT_TIMEOUT_SECONDS_OVERRIDE", "300")
os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")

import json
from pathlib import Path
from agentic_rag import answer_agentic

from deepeval.test_case import LLMTestCase
from deepeval.metrics import (
    FaithfulnessMetric, AnswerRelevancyMetric,
    ContextualPrecisionMetric, ContextualRecallMetric,
)

QA = json.loads((Path(__file__).parent / "qa_pairs.json").read_text(encoding="utf-8"))
JUDGE = "gpt-4o"
COLS = ["Faithfulness", "AnswerRelevancy", "ContextualPrecision", "ContextualRecall"]


def build_test_case(pair):
    output, chunks = answer_agentic(pair["input"], verbose=False)
    return LLMTestCase(
        input=pair["input"],
        actual_output=output,
        expected_output=pair["expected_output"],
        retrieval_context=[c["text"] for c in chunks],
    )


def main():
    metrics = [
        FaithfulnessMetric(model=JUDGE),
        AnswerRelevancyMetric(model=JUDGE),
        ContextualPrecisionMetric(model=JUDGE),
        ContextualRecallMetric(model=JUDGE),
    ]
    print("Scoring the grade-and-retry system...\n")
    results = []
    for pair in QA:
        case = build_test_case(pair)
        print("Q:", pair["input"])
        row = {"q": pair["input"][:38]}
        for m in metrics:
            name = m.__class__.__name__.replace("Metric", "")
            try:
                m.measure(case)
                row[name] = m.score
                print(f"   {name:20} {m.score:.2f}")
            except Exception as e:
                row[name] = None
                print(f"   {name:20} ERROR: {str(e)[:70]}")
        results.append(row)
        print()

    print("=" * 78)
    print(f'{"question":40}' + "".join(f'{c[:7]:>9}' for c in COLS))
    for r in results:
        print(f'{r["q"]:40}' + "".join(
            f'{(f"{r[c]:.2f}" if r.get(c) is not None else "-"):>9}' for c in COLS))

    def avg(c):
        vals = [r[c] for r in results if r.get(c) is not None]
        return sum(vals) / len(vals) if vals else 0
    print("-" * 78)
    print(f'{"AVERAGE (agentic)":40}' + "".join(f'{avg(c):>9.2f}' for c in COLS))


if __name__ == "__main__":
    main()
