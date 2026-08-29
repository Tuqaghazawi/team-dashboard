"""
Accuracy run (Capstone 1 -> Session 7 warm-up).

Extract EVERY note in a gold file, compare to its gold label field by field,
and report agreement, misses, fabrications, and the human-review flag.

Run from PROJECT ROOT.
  Original mixed set:
      .venv\\Scripts\\python.exe -m ai.eval.accuracy
  Breast set (pass the gold file as an argument):
      .venv\\Scripts\\python.exe -m ai.eval.accuracy data/synthetic/breast/gold_breast.jsonl
"""

import json
import sys
from pathlib import Path

from ai.extraction.schemas import ClinicalExtraction
from ai.extraction.extract import extract_note

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GOLD = REPO_ROOT / "data" / "synthetic" / "gold.jsonl"

# scalar fields we score, as dotted paths. Fields absent from a given gold
# label are simply skipped, so this one list works for BOTH the mixed set
# and the breast set.
SCORED_FIELDS = [
    "document_type", "phase", "primary_site", "laterality", "histology",
    "tnm.t", "tnm.n", "tnm.m", "tnm.stage_group",
    # generic blocks (mixed set)
    "pathology.histology", "pathology.grade", "pathology.tumor_size_mm",
    "pathology.margins", "pathology.lymphovascular_invasion",
    "pathology.nodes_examined", "pathology.nodes_positive",
    "radiology.modality", "radiology.largest_lesion_mm", "radiology.impression",
    "discharge.admission_reason", "discharge.followup_plan",
    # breast diagnostic
    "breast_diagnostic.receptors.er.status", "breast_diagnostic.receptors.er.percent_positive",
    "breast_diagnostic.receptors.pr.status", "breast_diagnostic.receptors.pr.percent_positive",
    "breast_diagnostic.receptors.her2.status", "breast_diagnostic.receptors.her2.score",
    "breast_diagnostic.axilla_biopsy_present",
    # breast post-op
    "breast_postop.neoadjuvant_given", "breast_postop.procedure", "breast_postop.grade",
    "breast_postop.focality", "breast_postop.largest_invasive_size_mm",
    "breast_postop.dcis_present", "breast_postop.lymphovascular_invasion",
    "breast_postop.perineural_invasion", "breast_postop.margin_status",
    "breast_postop.node_type", "breast_postop.nodes_examined", "breast_postop.nodes_positive",
    "breast_postop.largest_nodal_deposit_mm", "breast_postop.extranodal_extension",
    "breast_postop.treatment_effect_breast", "breast_postop.pathologic_stage",
]

INFERABLE = {"primary_site"}   # fields we allow the model to infer -> not counted as fabrication


def get_path(obj: dict, path: str):
    cur = obj
    for part in path.split("."):
        if not isinstance(cur, dict) or cur.get(part) is None:
            return None
        cur = cur[part]
    return cur


def norm(value):
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    return str(value).strip().lower().rstrip(".")


def main():
    gold_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_GOLD
    if not gold_path.is_absolute():
        gold_path = REPO_ROOT / gold_path
    rows = [json.loads(l) for l in gold_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"Scoring against: {gold_path.name}")
    print(f"Loaded {len(rows)} notes. Extracting (one API call each)...\n")

    per_field = {f: {"checked": 0, "correct": 0} for f in SCORED_FIELDS}
    total_checked = total_correct = misses = fabrications = 0
    review_gold_true = review_caught = 0

    for i, row in enumerate(rows, 1):
        note_id = row.get("id", f"note_{i}")
        gold = row["label"]
        try:
            # mode="json" -> enums become their string values (e.g. "pathology"),
            # so they compare correctly against the gold JSON. This was the bug.
            pred = extract_note(row["text"]).model_dump(mode="json")
        except Exception as e:
            print(f"[{i:>2}/{len(rows)}] {note_id}: ERROR {e}")
            continue

        for f in SCORED_FIELDS:
            g = norm(get_path(gold, f))
            p = norm(get_path(pred, f))
            if g is not None:
                per_field[f]["checked"] += 1
                total_checked += 1
                if p == g:
                    per_field[f]["correct"] += 1
                    total_correct += 1
                elif p is None:
                    misses += 1
            elif p is not None and f not in INFERABLE:
                fabrications += 1

        # --- human-review flag: of the notes gold says need review, how many did we catch? ---
        if get_path(gold, "meta.needs_human_review") is True:
            review_gold_true += 1
            if get_path(pred, "meta.needs_human_review") is True:
                review_caught += 1
            else:
                print(f"    -> MISSED review flag: {note_id} | gold reason: {get_path(gold, 'meta.notes')}")

        print(f"[{i:>2}/{len(rows)}] {note_id}: done")

    print("\n================ FIELD-LEVEL ACCURACY ================")
    print(f"{'field':<44}{'correct/checked':>16}{'acc':>7}")
    for f in SCORED_FIELDS:
        c, k = per_field[f]["checked"], per_field[f]["correct"]
        if c:
            print(f"{f:<44}{f'{k}/{c}':>16}{k/c:>7.0%}")
    print("-" * 67)
    if total_checked:
        print(f"{'OVERALL':<44}{f'{total_correct}/{total_checked}':>16}{total_correct/total_checked:>7.0%}")
    print(f"\nMisses (gold had it, engine returned null): {misses}")
    print(f"Possible fabrications (engine filled a gold-null field): {fabrications}")
    if review_gold_true:
        print(f"Human-review flag caught: {review_caught}/{review_gold_true} of the notes that need review")


if __name__ == "__main__":
    main()