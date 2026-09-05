"""Evaluate the guideline brain on the cases in ai/eval/guideline_cases.py.

    python manage.py eval_guidelines
    python manage.py eval_guidelines --judge      # adds the LLM-judge metric
    python manage.py eval_guidelines --case rectal-mid-tnt

The cases are built as real Patient objects inside a transaction that is always
rolled back, so the evaluation exercises exactly the code path the app uses —
the same `_case_block`, the same coverage check — without leaving anything in
the database.

Re-run this on every dependency bump and quarterly, and compare against the
baseline recorded in PRD §12. A fall in refusal calibration, source correctness
or history safety blocks the release.
"""

import json
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from ai.eval.guideline_cases import CASES
from ai.eval.guideline_eval import evaluate_case, summarise
from ai.guidelines import suggest
from patients.models import Investigation, Patient, SurgeryBooking, TreatmentCourse
from teams.models import Team


class Rollback(Exception):
    """Raised to undo the evaluation's throwaway data."""


class Command(BaseCommand):
    help = "Evaluate the guideline brain's suggestions on realistic cases."

    def add_arguments(self, parser):
        parser.add_argument("--judge", action="store_true",
                            help="Also run the LLM-judge appropriateness metric.")
        parser.add_argument("--case", help="Run one case by id.")
        parser.add_argument("--json", help="Write the full results to this path.")

    def handle(self, *args, **options):
        cases = CASES
        if options["case"]:
            cases = [c for c in CASES if c["id"] == options["case"]]
            if not cases:
                self.stderr.write(self.style.ERROR(f"No case {options['case']!r}"))
                return

        self.stdout.write(f"Indexed guidelines: {', '.join(suggest.indexed_guidelines())}")
        self.stdout.write(f"Evaluating {len(cases)} case(s)"
                          + (" with judge" if options["judge"] else "") + "...\n")

        results = []
        try:
            with transaction.atomic():
                team = Team.objects.create(consultant="Eval Team", specialty="Evaluation")
                for case in cases:
                    patient = self._build(case, team)
                    result = evaluate_case(case, patient, use_judge=options["judge"])
                    results.append(result)
                    self._report(result)
                raise Rollback
        except Rollback:
            pass

        self._summary(results)
        if options["json"]:
            self._write(results, options["json"])

    # --- building a case as real model objects ---

    def _build(self, case, team):
        today = timezone.localdate()
        patient = Patient.objects.create(
            name=f"Eval {case['id']}",
            mrn=f"EVAL-{case['id']}"[:20],
            date_of_birth=date(today.year - case["age"], 1, 1),
            diagnosis=case["diagnosis"],
            specialty=case["specialty"],
            team=team,
            stage=case["stage"],
            sex=case.get("sex", ""),
            clinical_stage=case.get("clinical_stage", ""),
            genetic_testing=case.get("genetics", ""),
            family_history=case.get("family_history", ""),
        )
        for kind, report in case.get("results", {}).items():
            Investigation.objects.create(
                patient=patient, kind=kind, status=Investigation.Status.READY,
                result_text=report, resulted_on=today - timedelta(days=14),
            )
        for course in case.get("courses", []):
            TreatmentCourse.objects.create(
                patient=patient, kind=course["kind"], regimen=course["regimen"],
                total_cycles=course["total"], completed_cycles=course["done"],
                start_date=today - timedelta(days=90),
            )
        for surgery in case.get("surgeries", []):
            SurgeryBooking.objects.create(
                patient=patient, procedure=surgery["procedure"],
                planned_date=today - timedelta(days=30),
                performed=True, performed_on=today - timedelta(days=30),
                final_pathology=surgery.get("pathology", ""),
            )
        return patient

    # --- reporting ---

    def _report(self, r):
        if r.error:
            self.stdout.write(self.style.ERROR(f"  {r.case_id}: {r.error}"))
            return

        marks = []
        marks.append(self._mark("refusal", r.refusal_correct))
        marks.append(self._mark("sources", r.sources_correct))
        if not r.refused:
            marks.append(self._mark("history", r.history_safe))
        if r.judge_verdict:
            marks.append(self._mark("judge", r.judge_verdict == "APPROPRIATE"))

        state = "refused" if r.refused else f"answered [{', '.join(r.sources) or 'no sources'}]"
        self.stdout.write(f"  {r.case_id:<26} {state:<34} {'  '.join(marks)}")

        for violation in r.history_violations:
            self.stdout.write(self.style.ERROR(f"      proposes something already done: {violation}"))
        if r.judge_verdict == "INAPPROPRIATE":
            self.stdout.write(self.style.WARNING(f"      judge: {r.judge_reason}"))
        if not r.refusal_correct:
            expected = "a refusal" if r.should_refuse else "an answer"
            self.stdout.write(self.style.ERROR(f"      expected {expected}"))

    def _mark(self, label, ok):
        return (self.style.SUCCESS if ok else self.style.ERROR)(
            f"{label} {'PASS' if ok else 'FAIL'}"
        )

    def _summary(self, results):
        summary = summarise(results)
        self.stdout.write("\n" + "=" * 66)
        for key, value in summary.items():
            self.stdout.write(f"  {key.replace('_', ' '):<24} {value}")
        self.stdout.write("=" * 66)

        failures = [r for r in results if not r.error and (
            not r.refusal_correct or not r.sources_correct or not r.history_safe
        )]
        if failures:
            self.stdout.write(self.style.ERROR(
                f"\n{len(failures)} case(s) failed a deterministic check — "
                f"do not release on this."
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                "\nEvery deterministic check passed."
            ))

    def _write(self, results, path):
        rows = [
            {
                "case": r.case_id, "refused": r.refused, "should_refuse": r.should_refuse,
                "sources": r.sources, "refusal_correct": r.refusal_correct,
                "sources_correct": r.sources_correct, "history_safe": r.history_safe,
                "history_violations": r.history_violations,
                "judge": r.judge_verdict, "judge_reason": r.judge_reason,
                "answer": r.answer, "error": r.error,
            }
            for r in results
        ]
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"summary": summarise(results), "cases": rows}, handle, indent=2)
        self.stdout.write(f"\nWrote {path}")
