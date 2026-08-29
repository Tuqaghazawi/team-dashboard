# Breast workup checklist — DRAFT for clinical review

> **Status: unreviewed draft.** Assembled from standard NCCN-style breast workup as a
> starting point for correction by the department. **Not clinical guidance.** No item here
> is authoritative until signed off. Correct, delete, add, and reorder freely — this file is
> the source the system will be seeded from.

## How the colours work

| Colour | Meaning |
|---|---|
| 🟢 Green | The result exists in the database (or a manual item has been ticked) |
| 🔴 Red | **Required** for this tumour type, and still missing |
| ⚪ Grey | **If indicated** — only needed in some cases, so absence is not a problem |

"If indicated" exists so that a patient who never needed a bone scan doesn't sit with a red
item forever. A grey item turns green if a result arrives, or can be marked *not required*.

**Source column:** `result` = turns green automatically when the report lands in the database ·
`manual` = a person ticks it, because there is no electronic result to detect.

---

## Imaging

| # | Item | Required? | Source |
|---|---|---|---|
| 1 | Bilateral diagnostic mammogram | Required | result |
| 2 | Breast ultrasound (± axillary ultrasound) | Required | result |
| 3 | Breast MRI | If indicated | result |

## Tissue diagnosis

| # | Item | Required? | Source |
|---|---|---|---|
| 4 | Core needle biopsy — histopathology report | Required | result |
| 5 | Histological type and grade | Required | result |
| 6 | Axillary node sampling (US-guided FNA / core) of suspicious node | If indicated | result |

## Biomarkers

| # | Item | Required? | Source |
|---|---|---|---|
| 7 | ER (oestrogen receptor) | Required | result |
| 8 | PR (progesterone receptor) | Required | result |
| 9 | HER2 (IHC, with FISH if equivocal) | Required | result |
| 10 | Ki-67 | If indicated | result |

## Laboratory

| # | Item | Required? | Source |
|---|---|---|---|
| 11 | CBC (complete blood count) | Required | result |
| 12 | Liver function tests + alkaline phosphatase | Required | result |
| 13 | Renal function | If indicated | result |

## Staging (systemic)

| # | Item | Required? | Source |
|---|---|---|---|
| 14 | CT chest / abdomen / pelvis | If indicated | result |
| 15 | Bone scan | If indicated | result |
| 16 | PET-CT | If indicated | result |

> **[QUESTION]** Systemic staging is listed as "if indicated" on the assumption it is done for
> stage III / clinically node-positive / symptomatic patients rather than everyone. If your
> department stages everyone, these become Required.

## Cardiac / fitness

| # | Item | Required? | Source |
|---|---|---|---|
| 17 | ECHO or MUGA (if anthracycline or HER2-targeted therapy planned) | If indicated | result |

## Genetics

| # | Item | Required? | Source |
|---|---|---|---|
| 18 | Genetic counselling referral | If indicated | manual |
| 19 | BRCA / panel testing result | If indicated | result |

## Team / patient-facing

| # | Item | Required? | Source |
|---|---|---|---|
| 20 | History and clinical examination documented | Required | manual |
| 21 | Discussed with patient | Required | manual |
| 22 | Breast care nurse seen | If indicated | manual |
| 23 | Fertility preservation discussed (premenopausal) | If indicated | manual |

---

## Open questions for the department

1. **Is anything above wrong, missing, or misnamed?** Local naming matters — the item labels
   here become what the whole team sees, and what the MDC slide prints.
2. **Systemic staging** — everyone, or only selected patients? (see question above)
3. **Ki-67** — routine in your practice, or selected?
4. **"Ready for MDC"** — should this mean *all Required items green*? That definition drives
   the readiness flag on the patient list and the coordinator's "not ready" warnings.
5. **Who may tick the manual items** — fellow, team coordinator, or anyone on the team?
6. Should an "if indicated" item be explicitly markable as **not required for this patient**,
   so it reads as a decision taken rather than something forgotten?

---

## Note on the MDC slides

Result text will be stored **verbatim** and reproduced on the MDC PowerPoint **exactly as
written, never summarised**. This is a hard design rule: the system must never store a
shortened version of a report, because the original could not then be recovered for the slide.
