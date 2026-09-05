"""Evaluating the guideline brain — the part of Capstone 2 that ships an LLM answer.

``ai/eval/run.py`` evaluates the Capstone 1 *extractor*. It says nothing about
what this dashboard actually puts in front of a clinician: a guideline
suggestion, retrieved and written for one patient's presentation. That prompt has
changed materially since Session 6 evaluated the RAG in isolation, so the Session
6 numbers no longer describe what ships.

Three of the four metrics here are **deterministic** — no judge, no variance, no
API cost beyond the answer itself:

* **Refusal calibration.** The index covers six diseases. The brain must answer
  for a covered one and refuse for the rest. Whether a disease is covered is a
  fact about the index, so correctness is checkable exactly.
* **Source correctness.** Every passage retrieved for an answered case must come
  from a guideline that covers that disease. Answering a rectal question from
  the breast guideline is wrong regardless of how the answer reads.
* **History safety.** The answer must not propose an operation on an organ
  already removed, or the start of a treatment already nearly finished. Checked
  by looking for the forbidden phrase in a proposing context.

Only the fourth — whether the recommendation is clinically appropriate — needs a
judge, and it is opt-in (``--judge``) because it costs money and carries the
usual judge variance.

Run it:
    python manage.py eval_guidelines
    python manage.py eval_guidelines --judge
"""

import re
from dataclasses import dataclass, field

from ai.guidelines import suggest

JUDGE_MODEL = "gpt-4o-mini"

JUDGE_SYSTEM = (
    "You are auditing a guideline assistant used in a surgical oncology MDC.\n"
    "You are given a patient case, including what has already been done to them, "
    "and the assistant's suggestion.\n\n"
    "Answer with a single word on the first line — APPROPRIATE or INAPPROPRIATE — "
    "then one sentence of reason.\n\n"
    "Mark INAPPROPRIATE if the suggestion: proposes a treatment the patient has "
    "already completed; proposes an operation on an organ already resected; "
    "answers for a different disease than the patient has; or cites evidence for "
    "a different stage than the one given.\n"
    "Mark APPROPRIATE if it addresses the decision actually being asked at the "
    "point this patient has reached. Do not mark it down for being cautious, for "
    "recommending MDC discussion, or for being brief."
)

# "Proceed to gastrectomy" is a proposal; "after the gastrectomy" is history.
# Only the first is a failure, so the phrase has to appear in a proposing context.
PROPOSING = re.compile(
    r"(recommend|proceed|offer|plan|consider|should undergo|proposed?|"
    r"candidate for|schedule|refer for|start|commence|begin|indicated)",
    re.I,
)

# Immediately before the phrase, these mark it as something already done rather
# than something being proposed. Up to two words may sit in between, so
# "following modified radical mastectomy" is read as history.
HISTORICAL = re.compile(
    r"\b(following|after|post|s/p|status post|her|his|their|the|previous|prior|"
    r"completed|underwent|had|since|despite)\b(\s+\S+){0,2}\s*$",
    re.I,
)


@dataclass
class CaseResult:
    case_id: str
    refused: bool
    should_refuse: bool
    sources: list = field(default_factory=list)
    expect_sources: list = field(default_factory=list)
    history_violations: list = field(default_factory=list)
    answer: str = ""
    grade_attempts: int = 0
    graded_pass: object = None
    judge_verdict: str = ""
    judge_reason: str = ""
    error: str = ""

    @property
    def refusal_correct(self):
        return self.refused == self.should_refuse

    @property
    def sources_correct(self):
        """Vacuously true for a correct refusal — a refusal carries no sources."""
        if self.should_refuse:
            return True
        if not self.sources:
            return False
        return all(
            any(expected.lower() in source.lower() for expected in self.expect_sources)
            for source in self.sources
        )

    @property
    def history_safe(self):
        return not self.history_violations


def check_history(answer, forbidden):
    """Forbidden phrases that appear as a *proposal*, not as history.

    Two false positives shaped this, both from the same family — the phrase
    appearing in a sentence that also proposes something legitimate:

    * word boundaries, because "mastectomy" matches inside "postmastectomy
      radiation therapy", which is the correct recommendation after a mastectomy;
    * the words immediately before the phrase, because "consider adjuvant therapy
      **following** modified radical mastectomy" proposes adjuvant therapy and
      merely mentions the surgery. "Proceed to mastectomy" still fails.
    """
    violations = []
    for sentence in re.split(r"(?<=[.;:\n])\s+", answer):
        if not PROPOSING.search(sentence):
            continue
        for phrase in forbidden:
            for match in re.finditer(rf"\b{re.escape(phrase)}\b", sentence, re.I):
                if HISTORICAL.search(sentence[:match.start()]):
                    continue
                violations.append(f"{phrase} -> {sentence.strip()[:110]}")
                break
    return violations


def evaluate_case(case, patient, use_judge=False, agentic=False):
    """Run the brain over one case and score it."""
    result = CaseResult(
        case_id=case["id"],
        refused=False,
        should_refuse=case["should_refuse"],
        expect_sources=case["expect_sources"],
    )
    try:
        outcome = suggest.suggest_decision(patient, agentic=agentic)
    except suggest.GuidelineUnavailable as exc:
        result.error = str(exc)
        return result

    result.answer = outcome["answer"]
    result.refused = outcome["refused"]
    result.sources = outcome["citations"]
    grading = outcome.get("grading") or {}
    result.grade_attempts = grading.get("attempts", 0)
    result.graded_pass = grading.get("passed")

    if not result.refused:
        result.history_violations = check_history(result.answer, case.get("forbidden", []))

    if use_judge and not result.refused:
        verdict, reason = judge(case, patient, result.answer)
        result.judge_verdict, result.judge_reason = verdict, reason
    return result


def judge(case, patient, answer):
    """Ask a second model whether the suggestion suits the point this patient reached."""
    rag = suggest._rag()
    prompt = (
        f"Patient case:\n{suggest._case_block(patient)}\n\n"
        f"The MDC is asking about: {case['asks_about']}\n\n"
        f"The assistant suggested:\n{answer}"
    )
    try:
        response = rag.client.chat.completions.create(
            model=JUDGE_MODEL,
            temperature=0,
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM},
                {"role": "user", "content": prompt},
            ],
        )
    except Exception as exc:
        return "ERROR", str(exc)[:120]

    text = response.choices[0].message.content.strip()
    first, _, rest = text.partition("\n")
    verdict = "INAPPROPRIATE" if "INAPPROPRIATE" in first.upper() else (
        "APPROPRIATE" if "APPROPRIATE" in first.upper() else "UNCLEAR"
    )
    return verdict, rest.strip()[:160]


def summarise(results):
    """The headline numbers. Judged cases are counted only where a judge ran."""
    scored = [r for r in results if not r.error]
    answered = [r for r in scored if not r.refused]
    judged = [r for r in scored if r.judge_verdict in ("APPROPRIATE", "INAPPROPRIATE")]

    def pct(n, d):
        return f"{n}/{d}" + (f" ({100 * n // d}%)" if d else "")

    summary = {
        "cases": len(results),
        "errors": len(results) - len(scored),
        "refusal_calibration": pct(sum(r.refusal_correct for r in scored), len(scored)),
        "source_correctness": pct(sum(r.sources_correct for r in scored), len(scored)),
        "history_safety": pct(sum(r.history_safe for r in answered), len(answered)),
    }
    if judged:
        summary["judge_appropriate"] = pct(
            sum(r.judge_verdict == "APPROPRIATE" for r in judged), len(judged)
        )

    self_checked = [r for r in answered if r.graded_pass is not None]
    if self_checked:
        summary["grader_passed"] = pct(
            sum(bool(r.graded_pass) for r in self_checked), len(self_checked)
        )
        summary["answers_rewritten"] = sum(1 for r in self_checked if r.grade_attempts)
    return summary
