# Clinical Extraction System (Breast Pathology) — PRD

**Author:** Tuqa Saleh Al-Ghazawi
**Course:** CCI — Clinical AI / Prompt Engineering (Capstone 1)
**Status:** v1 complete — built and evaluated
**Version:** 1.0
**Last updated:** 29 Aug 2026

> This is the PRD for the **Clinical Extraction System**, the first AI module of the
> Surgical Oncology Patient Flow Dashboard. The dashboard has its own PRD
> (`docs/PRD.md`); this document covers the extraction module only.

---

## 1. Summary

The Clinical Extraction System reads a free-text breast pathology report — either a
diagnostic core biopsy or a post-operative resection — and returns a structured,
schema-validated record: histology, grade, size in mm, ER/PR/HER2, node counts, margins,
stage, and a human-review flag. It exists so the dashboard can hold patient data as
*fields it can filter and act on*, not as prose. v1 targets breast pathology, runs and
scores itself against a 20-note synthetic labeled set, and is built as a self-contained
module that can be tested before it plugs into the dashboard.

## 2. Problem

- **What hurts today:** Pathology reports are free text written for a human reader. The
  tumor-board dashboard, and any downstream audit or research, needs specific fields.
  Pulling them by hand is slow and inconsistent — two people transcribe the same report
  differently, and nobody has time to do it at scale.
- **Who has this problem:** The surgical oncology service at KHCC — fellows and
  coordinators who would otherwise re-type report data into the dashboard.
- **Why an app (and why an LLM):** The reports vary in wording, order, and completeness.
  A rules/regex parser breaks on that variability; an LLM reads intent ("Not seen" =
  absent, "S/P chemotherapy" = neoadjuvant given) and maps it onto a fixed schema.

## 3. Goals

- **Primary goal:** Turn a breast pathology report into a structured, schema-valid record
  with measurable, high field-level accuracy on a labeled test set.
- **Secondary goals:**
  - Flag ambiguous or safety-relevant cases for human review instead of treating the
    model's answer as final.
  - Stay a self-contained, independently testable module with no PHI.

## 4. Non-goals (v1)

Pushed out of v1 deliberately, to keep it finishable:

- **Non-breast sites.** The schema has generic stubs (colon, thyroid, etc.) but only
  breast is modelled and evaluated.
- **Other document types.** Radiology and discharge blocks are scaffolded in the schema
  but not a v1 target.
- **Real patient data.** Synthetic reports only.
- **Live dashboard integration UI.** The contract (schema) is defined; wiring the output
  into dashboard screens is a later phase.
- **Deployment, accounts, multi-language.** Out of scope for the capstone.

## 5. Users

| Role | Who | What they do with the module |
|------|-----|------------------------------|
| Primary consumer | The dashboard | Receives a structured record to populate a patient entry |
| Operator | Fellow / coordinator | Runs the extraction on a report; reviews flagged cases |
| Evaluator | Project author | Runs the accuracy harness against the labeled set |

## 6. User stories

- As a **coordinator**, when a breast pathology report arrives, I want it turned into
  structured fields, so that the patient's dashboard entry fills in without re-typing.
- As a **fellow**, when a report is ambiguous (equivocal HER2, conflicting focality,
  involved margins), I want it flagged for review, so that a human checks it before it's
  treated as final.
- As the **author**, when I change the schema or prompt, I want to score every note
  against a known answer key, so that I can see exactly which fields improved or broke.
- As a **downstream researcher**, when I query the dashboard, I want consistent fields
  (size always in mm, receptors as status + percent), so that the data is analysable.

## 7. Functional requirements

### 7.1 Input
- FR-1.1 Accept the full text of one breast pathology report (diagnostic core biopsy or
  post-operative resection).
- FR-1.2 No patient identifiers are required or read; the module works on clinical content
  only.

### 7.2 LLM processing
- FR-2.1 Send the report text to the LLM with the `ClinicalExtraction` schema attached as a
  structured-output contract.
- FR-2.2 Route on `document_type` + `phase`: fill `breast_diagnostic` for a biopsy,
  `breast_postop` for a resection.
- FR-2.3 Normalise on extraction: sizes to millimetres (convert cm × 10); booleans as
  three-state (true = stated present, false = explicitly negated, null = not mentioned).
- FR-2.4 Set `needs_human_review = true` on equivocal HER2 (2+) pending reflex ISH,
  macroscopic/microscopic focality disagreement, involved margins, or safety-relevant
  ambiguity.

### 7.3 Output
- FR-3.1 Return one `ClinicalExtraction` record per report, schema-valid by construction.
- FR-3.2 Populate `meta.evidence_spans` (source snippets) and `meta.missing_fields` (for
  recall) alongside the clinical fields.
- FR-3.3 Link to a dashboard patient via a non-PHI `synthetic_patient_ref` token only.

### 7.4 Storage / evaluation
- FR-4.1 The synthetic generator writes both the note text and its gold label from the same
  random values (correct by construction) to a JSONL file.
- FR-4.2 The accuracy harness extracts every note and scores field-by-field against gold,
  reporting accuracy, misses (recall), fabrications (precision), and human-review recall.

## 8. The LLM call (the heart of the project)

- **Model:** OpenAI model with structured-output support, called directly via the `openai`
  Python package. `[TBD — confirm the exact model used; template default is gpt-4.1-mini]`
- **API key:** read from `.env` via environment; `.env` is in `.gitignore`. Never
  hardcoded, never committed. (Confirmed: `.env` is untracked in the repo.)
- **What the prompt does:** extraction — read a report, emit the schema's fields.
- **Input → output shape:** report text (string) → `ClinicalExtraction` JSON object
  (routing fields, shared oncology core, one breast block, and `meta`).
- **Structured output:** bound to a Pydantic v2 schema (`ai/extraction/schemas.py`). The
  top-level model sets `extra="forbid"`, so any key not in the schema is rejected — this
  re-arms the label-validation check that was previously a silent no-op.
- **When the API call fails:** the accuracy harness catches the exception per note, prints
  an error line for that note, and continues the batch — one failed call never crashes the
  run. (Observed: on exhausted credits, notes return a 429 and are reported, not fatal.)
- **Cost sanity check:** one call per note × 20 notes = pennies per full evaluation run.

Example call skeleton (structured output against the schema):

```python
from openai import OpenAI
from dotenv import load_dotenv
from ai.extraction.schemas import ClinicalExtraction

load_dotenv()
client = OpenAI()  # reads OPENAI_API_KEY from environment

# extract_note() sends the report text with the ClinicalExtraction schema
# attached, and returns a validated ClinicalExtraction object.
```

## 9. Data & storage

- **Development data:** synthetic KHCC-format breast reports — 12 diagnostic + 8 post-op —
  generated with a fixed random seed for reproducibility.
- **Gold labels:** built from the same random values used to write each note, so the answer
  key is correct by construction, and validated against the schema on generation.
- **Files:** notes as `.txt`, labels as `gold_breast.jsonl` under `data/synthetic/breast/`.
- **Dashboard storage:** the extractor's output maps to the dashboard's Django models;
  the module itself does not own a database. `[assumed — confirm the dashboard mapping]`
- **Privacy note:** no real patient data. The extractor pulls clinical content, never
  identity; synthetic data only for development and evaluation.

## 10. Tech stack

| Layer | Choice | Why |
|-------|--------|-----|
| Language | Python 3.11+ | course standard |
| Framework | Django (dashboard host) | dashboard needs admin, auth, multiple models |
| Schema / validation | Pydantic v2 | typed contract; `extra="forbid"` guards against drift |
| LLM | OpenAI API, structured outputs | maps free text onto a fixed schema; exact model `[TBD]` |
| Eval data | JSONL files (not a DB) | synthetic set + gold labels, versionable alongside code |
| Secrets | `.env` + environment | key never in code or git (`.env` gitignored, confirmed) |

## 11. App flow

Build / evaluation flow:

1. `generate_breast.py` writes 20 synthetic reports + matching gold labels.
2. `accuracy.py` extracts every note (one API call each) and scores it field-by-field
   against gold.
3. `inspect.py` shows one note's source, model extraction, and gold label side by side for
   error analysis.

Runtime flow (per report):

1. Report text goes to `extract_note()`.
2. The LLM returns a schema-valid `ClinicalExtraction` object (routed by document_type +
   phase).
3. The record — plus the `needs_human_review` flag — is available to populate the
   dashboard patient entry; flagged cases go to a human first.

## 12. Testing & "done means"

- **Demo scenario:** run `generate_breast.py`, then `accuracy.py` on the breast gold set;
  the field table prints 100% with the summary counts below.
- **Test set:** 20 notes (12 diagnostic, 8 post-op), 30 scored fields.
- **Success criteria (achieved):**
  - Field accuracy: **313/313 (100%)**
  - Misses (recall): **0**
  - Fabrications (precision): **0**
  - Human-review recall: **4/4** genuine review cases caught
- **Edge cases handled:** mixed size units (cm in text, mm in schema), absence vs explicit
  negation (null vs false), phase routing (diagnostic vs post-op), a redundant generic
  block that had to be steered off for breast, and API failure (per-note, non-fatal).

## 13. Risks

| Risk | Mitigation |
|------|------------|
| Schema and gold labels drift apart (missing fields score as silent zeros) | Top-level `extra="forbid"` rejects unknown keys; re-arms the label-validation tripwire that was previously a no-op |
| "Accuracy" hides recall/precision problems | Report misses and fabrications separately, not just accuracy |
| Unit inconsistency (cm vs mm) | One canonical unit (mm) enforced in schema description, generator, and comparator |
| Absence-vs-negation confusion | Three-state booleans (true/false/null) with "do not infer false from silence" in the field descriptions |
| Gold labels themselves are wrong | The evaluation caught exactly this — a focality flag set from a coin flip rather than the text; fixed the generator so the flag follows the actual values |
| API key leak | `.env` in `.gitignore`, verified untracked before pushing |
| API cost / exhausted credits | ~pennies per run; harness reports 429s per note instead of crashing |
| Scope creep to other sites/doc types | Kept in Non-goals; v1 is breast only |

## 14. Milestones

| Milestone | Done when | Status |
|-----------|-----------|--------|
| Schema defined (the contract) | `ClinicalExtraction` types the output and the labels | Done |
| Extraction engine | `extract_note()` returns schema-valid records | Done |
| Synthetic labeled set | 20 reports + correct-by-construction gold | Done |
| Evaluation harness | field-level accuracy, misses, fabrications, review recall | Done |
| Iterate to target | 313/313, 0 misses, 0 fabrications, 4/4 review | Done |
| Hardening | `extra="forbid"` re-arms drift protection | Done |
| Documentation | README (dashboard + AI layer) + build/error-analysis writeup | Done |

## 15. Open questions

- [ ] `[TBD]` Confirm the exact OpenAI model used (template default is `gpt-4.1-mini`).
- [ ] `[assumed — change if you want]` Exact mapping from `ClinicalExtraction` fields to the
  dashboard's Django patient models.
- [ ] Later: validate on de-identified **real** reports and a larger, clinician-reviewed
  set (synthetic-only is the v1 limit).
- [ ] Later: human-review recall is the soft spot — escalation is a judgment call and the
  hardest thing to make fully reliable.
- [ ] Later: extend beyond breast to the other sites the schema stubs out.
