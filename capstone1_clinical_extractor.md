# Clinical Extraction System — Capstone 1

**Turning free-text breast pathology reports into structured, schema-valid data with an LLM.**

Author: Tuqa Saleh Al-Ghazawi · KHCC · CCI Prompt Engineering & Clinical AI Development
Scope: breast pathology — diagnostic (core biopsy) and post-operative (resection) reports.

---

## 1. The one-paragraph version

A pathology report is prose written for a human reader. My tumor-board dashboard, and any downstream research or audit, needs it as *structured fields* — histology, grade, size in mm, ER/PR/HER2, node counts, stage. This system reads a report and returns those fields as a validated object, so the same note can populate a database, a checklist, or a research table without anyone re-typing it. It runs the extraction, scores itself against a labeled test set, and flags the cases a human should still review before sign-off.

---

## 2. The problem I was solving

Free text is easy to write and hard to compute on. Three concrete pains:

- **The dashboard needs fields, not paragraphs.** A tumor-board view can't filter or summarize prose.
- **Manual extraction is slow and inconsistent.** Two people transcribe the same report differently; nobody has time to do it at scale.
- **Real reports carry PHI.** Any solution has to be demonstrable *without* touching patient identity.

So the goal: read a report, emit a fixed set of clinical fields, prove it's accurate, and do it all on synthetic data.

---

## 3. How it works — the pipeline

```
   generate_breast.py                 extract_note()                  accuracy.py / inspect.py
  ┌──────────────────┐   note text  ┌────────────────────┐   record  ┌────────────────────────┐
  │ synthetic report │ ───────────▶ │ OpenAI structured  │ ────────▶ │ compare field-by-field │
  │  + gold label    │              │ output, bound to   │           │ vs gold → accuracy,    │
  │ (same random     │              │ the Pydantic schema│           │ misses, fabrications,  │
  │  values → both)  │              └────────────────────┘           │ human-review recall    │
  └──────────────────┘                        ▲                       └────────────────────────┘
                                               │
                                        schemas.py
                          (types the model's output AND validates the gold labels)
```

The single most important idea in the whole system: **`schemas.py` sits under both ends.** It defines what the model is allowed to emit *and* what a valid label looks like. That shared role is the heart of the design — and, as it turned out, the source of the biggest bug.

---

## 4. Building it, step by step (the part I'd teach)

### Step 1 — Define the schema first (the contract)

Before any prompting, I wrote down the exact shape of the output as a Pydantic model (`ClinicalExtraction`). This is the opposite of asking the model "please give me the fields" and hoping. The schema *is* the specification.

Key decisions baked in here:

- **One record per document**, with `document_type` and `phase` routing which block gets filled.
- **Two breast blocks, not one:** `breast_diagnostic` (core biopsy — receptors, specimens, axilla) and `breast_postop` (resection — margins, nodes, treatment effect, stage). A biopsy and a resection support genuinely different fields; forcing them into one block would mean half the fields are always empty.
- **Every clinical field is Optional.** The model degrades gracefully on messy input instead of hard-failing.
- **No patient identifiers.** The schema pulls clinical *content*, never name/MRN/DOB — a deliberate governance choice.

### Step 2 — Bind the LLM to the schema (structured output)

`extract_note()` sends the report text to the model with the schema attached, using structured outputs. The model can only return fields that exist in the schema.

**The lesson that cost me the most time:** the schema is a *ceiling*, not a suggestion. If a field isn't in the schema, the model literally cannot emit it — the information just falls on the floor, silently. The engine was never the bottleneck; the schema's completeness was.

### Step 3 — Make labeled data without touching PHI

I can't evaluate accuracy without knowing the right answers, and I can't use real reports. So `generate_breast.py` writes synthetic KHCC-format reports where the label is built from the *same* random values used to write the note — the answer key is correct by construction. 20 notes: 12 diagnostic, 8 post-op, seeded so the set is reproducible.

### Step 4 — Evaluate honestly

`accuracy.py` extracts every note and compares to gold field-by-field, reporting four different things — because "accuracy" alone hides too much:

| Metric | Question it answers |
|---|---|
| Field accuracy | When gold has a value, did we get it right? |
| Misses | Did we return null where gold had a value? (recall) |
| Fabrications | Did we fill a field gold left empty? (precision) |
| Human-review recall | Of the notes that *need* a human, how many did we flag? |

### Step 5 — Iterate: read the errors, fix, re-run

This is where the real work happened — not writing the system, but debugging it against its own scoreboard. Each failing number pointed at one specific defect.

---

## 5. Key design decisions, at a glance

| Decision | Why |
|---|---|
| Schema-first, everything Optional | Graceful degradation on real-world variability |
| `document_type` + `phase` routing | Diagnostic vs resection need different fields |
| Sizes stored in **mm**, convert cm→mm | One canonical unit; comparison can't drift |
| Booleans are three-state: `true` / `false` / `null` | Distinguish "explicitly absent" from "not mentioned" — clinically real |
| Biomarker values kept as verbatim strings | ER/PR/HER2 results are too heterogeneous to normalize early |
| No PHI in the schema | Governance: extract content, not identity |

---

## 6. Results

| | Result |
|---|---|
| Field accuracy | **313 / 313 (100%)** across 30 scored fields |
| Misses (recall) | **0** |
| Fabrications (precision) | **0** |
| Human-review recall | **4 / 4** genuine review cases caught |

Every value the gold set contains, the engine extracts correctly, and it fills nothing it shouldn't.

---

## 7. What went wrong, and what it taught me (error analysis)

This is the part I'm proudest of, because the failures were more instructive than the final score.

**a) A "94%" that was hollow.** The schema I started with had no breast blocks. The generator and the scorer both referenced `breast_postop.*`, `phase`, and receptor fields the schema didn't contain — so the model had nowhere to put correct answers, and every breast field scored as a silent miss. The headline number was carried by four shared fields. *Lesson: a missing schema field is invisible — it looks like the model failed, not like the plumbing is incomplete.*

**b) Two safeguards were quietly disarmed.** The generator called `model_validate()` on every label to guarantee it was schema-valid — but Pydantic ignores unknown keys by default, so it silently dropped the entire breast structure and validated the hollow remainder. And the scorer counted a missing field as a "miss," never an error. Both safeguards passed while the gap sat in plain sight. *Lesson: a check that can't fail isn't a check.*

**c) Conventions have to agree in three places.** A tumor size in cm in the note but mm in the label, or a boolean that's `false` on silence in gold but `null` on silence from the model, produces a mismatch even when everyone is "right." The unit and the true/false/null convention have to be identical across the schema description, the generator, and the comparator.

**d) The evaluation caught a bug in its own ground truth.** The system kept "missing" the review flag on one post-op note. When I inspected it, the note's macroscopic and microscopic focality *agreed* — there was nothing to flag. The model was correct; the **gold label was wrong.** The generator had set the "needs review" flag from a coin flip instead of from whether the two focality values actually differed. The model's disagreement is what exposed the off-by-one in my label logic. *Lesson: don't blindly trust the answer key — a confident model that disagrees with gold is sometimes the model catching your bug.*

---

## 8. Governance and safety

- **No PHI** is ever extracted or stored; the link to a patient is a non-identifying synthetic token.
- **Synthetic data only** for development and evaluation.
- **Human-in-the-loop by design:** the `needs_human_review` flag routes ambiguous or safety-relevant cases (equivocal HER2 pending reflex ISH, macro/micro discrepancies, involved margins) to a person before sign-off, rather than pretending the model's answer is final.

---

## 9. Limitations and next steps

- **Synthetic, small (n=20).** A real validation needs de-identified real reports and a larger, clinician-reviewed set.
- **The review flag is the soft spot.** It works on the current set, but escalation is a judgment call and the hardest thing to make reliable — the honest ceiling of the project.
- **Hardening:** set the schema to reject unknown keys (`extra="forbid"`) so a schema/label drift can never silently pass again — the direct fix for the failure that started this whole build.
- **Integration:** wire the extractor into the surgical-oncology dashboard so a pasted report auto-populates the tumor-board record.
