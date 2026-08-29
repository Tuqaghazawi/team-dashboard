#!/usr/bin/env python
"""Generate a synthetic oncology note corpus with gold-standard extraction labels.

Runs entirely offline: no API calls. Notes are built from templates with
randomised values, and each gold label is assembled from the *same* values that
were templated in, so labels are correct by construction rather than by
annotation.

Two properties the evaluation depends on:

1. Each label contains only what its note actually states. A radiology report
   carries no margin status or receptor results, so those stay null -- an
   extractor that invents them is wrong, not lucky.
2. Deliberately omitted fields are recorded in ``meta.missing_fields``, so
   "not found" can be scored separately from "found and wrong" (field-level
   recall vs precision).

Deterministic: the same SEED always produces the same corpus.

Outputs:
    data/synthetic/notes/<id>.txt
    data/synthetic/gold.jsonl      {"id", "text", "label"} per line
"""
from __future__ import annotations

import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

OUT_DIR = BASE_DIR / "data" / "synthetic"
NOTES_DIR = OUT_DIR / "notes"
GOLD_PATH = OUT_DIR / "gold.jsonl"

BANNER = "SYNTHETIC - not for clinical use"
SEED = 20260827
COPIES_PER_COMBINATION = 2

try:
    from ai.extraction.schemas import ClinicalExtraction
except (ModuleNotFoundError, ImportError) as exc:
    print(
        "ai/extraction/schemas.py is not there yet (or does not define "
        f"ClinicalExtraction).\n  -> {exc}\n\n"
        "Add the schema, then re-run:\n"
        "    python scripts/generate_synthetic.py\n\n"
        "Nothing was written."
    )
    sys.exit(0)


# --------------------------------------------------------------------------
# Site-specific clinical content
# --------------------------------------------------------------------------

SITES = {
    "breast": {
        "paired": True,
        "histologies": [
            "Invasive ductal carcinoma (IDC), NST",
            "Invasive lobular carcinoma (ILC)",
            "Mucinous carcinoma",
        ],
        "procedures": [
            "Right breast wide local excision with SLNB",
            "Left modified radical mastectomy",
            "Right simple mastectomy with axillary clearance",
        ],
        "study": "Bilateral diagnostic mammogram and breast US",
        "modality": "US",
        "body_region": "breast and axilla",
        "lesion": "spiculated mass in the upper outer quadrant",
        "nodal_basin": "axillary",
        "mets": ["liver", "bone", "lung"],
        "sex_bias": "F",
    },
    "colon": {
        "paired": False,
        "histologies": [
            "Adenocarcinoma, moderately differentiated",
            "Mucinous adenocarcinoma",
            "Adenocarcinoma, poorly differentiated",
        ],
        "procedures": ["Right hemicolectomy", "Sigmoid colectomy",
                       "Extended left hemicolectomy"],
        "study": "CT chest/abdomen/pelvis with IV contrast",
        "modality": "CT",
        "body_region": "chest/abdomen/pelvis",
        "lesion": "annular constricting lesion",
        "nodal_basin": "pericolic",
        "mets": ["liver", "lung", "peritoneum"],
        "sex_bias": None,
    },
    "rectum": {
        "paired": False,
        "histologies": ["Adenocarcinoma, moderately differentiated",
                        "Adenocarcinoma, well differentiated"],
        "procedures": ["Low anterior resection with TME",
                       "Abdominoperineal resection (APR)"],
        "study": "MRI pelvis, rectal protocol",
        "modality": "MRI",
        "body_region": "pelvis",
        "lesion": "circumferential mid-rectal tumour",
        "nodal_basin": "mesorectal",
        "mets": ["liver", "lung"],
        "sex_bias": None,
    },
    "thyroid": {
        "paired": False,
        "histologies": [
            "Papillary thyroid carcinoma, classical variant",
            "Papillary thyroid carcinoma, follicular variant",
            "Follicular thyroid carcinoma",
        ],
        "procedures": ["Total thyroidectomy",
                       "Total thyroidectomy with central neck dissection",
                       "Right hemithyroidectomy"],
        "study": "Neck ultrasound",
        "modality": "US",
        "body_region": "neck",
        "lesion": "hypoechoic nodule with microcalcifications",
        "nodal_basin": "central compartment",
        "mets": ["lung", "bone"],
        "sex_bias": "F",
    },
    "stomach": {
        "paired": False,
        "histologies": ["Adenocarcinoma, intestinal type",
                        "Poorly cohesive carcinoma with signet ring cells"],
        "procedures": ["Subtotal gastrectomy with D2 lymphadenectomy",
                       "Total gastrectomy with D2 lymphadenectomy"],
        "study": "CT chest/abdomen/pelvis with IV contrast",
        "modality": "CT",
        "body_region": "chest/abdomen/pelvis",
        "lesion": "thickened gastric antral wall",
        "nodal_basin": "perigastric",
        "mets": ["peritoneum", "liver"],
        "sex_bias": None,
    },
    "esophagus": {
        "paired": False,
        "histologies": ["Squamous cell carcinoma", "Adenocarcinoma"],
        "procedures": ["Ivor-Lewis oesophagectomy", "McKeown oesophagectomy"],
        "study": "PET-CT",
        "modality": "PET-CT",
        "body_region": "whole body",
        "lesion": "circumferential distal oesophageal thickening",
        "nodal_basin": "paraoesophageal",
        "mets": ["liver", "lung", "bone"],
        "sex_bias": "M",
    },
}

DOC_TYPES = ["pathology", "radiology", "discharge_summary"]

# A field can only be "omitted" if that document type would normally report it.
OMITTABLE = {
    "pathology": [None, None, "grade", "tumor_size_mm"],
    "radiology": [None, None, "largest_lesion_mm"],
    "discharge_summary": [None, None, "stage_group"],
}


# --------------------------------------------------------------------------
# Case generation
# --------------------------------------------------------------------------

def make_case(site, doc_type, rng, seq):
    """Randomised underlying truth for one case."""
    cfg = SITES[site]
    nodes_examined = rng.randint(8, 24)
    nodes_positive = rng.choice([0, 0, 1, 2, rng.randint(3, 6)])
    n_num = "N0" if nodes_positive == 0 else ("N1" if nodes_positive <= 3 else "N2")
    has_mets = rng.random() < 0.18

    case = {
        "id": f"{site}_{doc_type}_{seq:02d}",
        "site": site,
        "document_type": doc_type,
        "patient_ref": f"SYNTH-{rng.randint(1000, 9999)}",
        "accession": f"{rng.randint(100, 999)}-{rng.randint(10, 99)}",
        "doc_date": date(2026, 1, 1) + timedelta(days=rng.randint(0, 230)),
        "age": rng.randint(31, 79),
        "sex": cfg["sex_bias"] or rng.choice(["M", "F"]),
        "laterality": rng.choice(["right", "left"]) if cfg["paired"] else "not_applicable",
        "histology": rng.choice(cfg["histologies"]),
        "grade": rng.choice([1, 2, 3]),
        "tumor_size_mm": float(rng.choice([9, 14, 18, 22, 27, 35, 41, 55])),
        "t_num": rng.choice(["T1", "T2", "T3", "T4a"]),
        "n_num": n_num,
        "m_num": "M1" if has_mets else "M0",
        "nodes_examined": nodes_examined,
        "nodes_positive": nodes_positive,
        "margins": rng.choice(["negative", "negative",
                               "positive at deep margin", "close (1 mm)"]),
        "lvi": rng.choice([True, False]),
        "pni": rng.choice([True, False]),
        "procedure": rng.choice(cfg["procedures"]),
        "mets_sites": rng.sample(cfg["mets"], rng.randint(1, 2)) if has_mets else [],
    }
    case["stage_group"] = stage_group_for(case)
    case["omit"] = rng.choice(OMITTABLE[doc_type])

    if site == "breast":
        er_pct = rng.choice([0, 20, 60, 90, 95])
        case["er_value"] = f"{er_pct}% positive" if er_pct else "negative (<1%)"
        pr_pct = rng.choice([0, 15, 70, 85]) if er_pct else 0
        case["pr_value"] = f"{pr_pct}% positive" if pr_pct else "negative (<1%)"
        case["her2_value"] = rng.choice([
            "IHC 0 (negative)", "IHC 1+ (negative)",
            "IHC 2+, FISH amplified (positive)", "IHC 3+ (positive)",
        ])
    return case


def stage_group_for(case):
    if case["m_num"] == "M1":
        return "IV"
    if case["n_num"] != "N0":
        return "III"
    return "II" if case["t_num"] in ("T3", "T4a") else "I"


# --------------------------------------------------------------------------
# Note templates
# --------------------------------------------------------------------------

def _header(case, title):
    return [
        BANNER,
        f"=== {title} ===",
        f"Accession: {case['accession']}    Ref: {case['patient_ref']}",
        f"Date: {case['doc_date'].strftime('%d-%b-%Y')}",
        f"Age: {case['age']}   Sex: {case['sex']}",
        "",
    ]


def pathology_note(case, rng):
    lines = _header(case, "SURGICAL PATHOLOGY REPORT")
    lines += [f"SPECIMEN: {case['procedure']}", "", "MICROSCOPIC:",
              f"  {case['histology']}."]
    if case["omit"] != "grade":
        lines.append(f"  Grade {case['grade']} of 3.")
    if case["omit"] != "tumor_size_mm":
        lines.append(f"  Max tumour dimension {case['tumor_size_mm']:.0f} mm.")
    lines += [
        f"  LN: {case['nodes_positive']}/{case['nodes_examined']} involved "
        f"({SITES[case['site']]['nodal_basin']}).",
        f"  Margins {case['margins']}.",
        f"  LVI {'present' if case['lvi'] else 'not identified'}; "
        f"PNI {'present' if case['pni'] else 'not identified'}.",
    ]
    if case["site"] == "breast":
        lines += ["", "IHC:",
                  f"  ER {case['er_value']}; PR {case['pr_value']}; "
                  f"HER2 {case['her2_value']}."]
    lines += ["", f"DIAGNOSIS: {case['histology']}, "
                  f"p{case['t_num']} p{case['n_num']}."]
    return "\n".join(lines)


def radiology_note(case, rng):
    cfg = SITES[case["site"]]
    lines = _header(case, f"RADIOLOGY REPORT - {cfg['study'].upper()}")
    lines += ["CLINICAL: Staging.", "", "FINDINGS:"]
    if case["omit"] != "largest_lesion_mm":
        lines.append(f"  {cfg['lesion'].capitalize()} measuring "
                     f"{case['tumor_size_mm']:.0f} mm.")
    else:
        lines.append(f"  {cfg['lesion'].capitalize()}, not accurately measurable.")
    if case["n_num"] == "N0":
        lines.append(f"  No enlarged {cfg['nodal_basin']} nodes. NAD elsewhere.")
    else:
        lines.append(f"  Enlarged {cfg['nodal_basin']} nodes, c/w nodal disease.")
    if case["mets_sites"]:
        lines.append(f"  Lesions in {' and '.join(case['mets_sites'])}, "
                     "c/w metastatic disease.")
    else:
        lines.append("  No distant metastatic disease.")
    lines += ["", f"IMPRESSION: {case['impression']}" if case.get("impression")
              else f"IMPRESSION: c{case['t_num']} c{case['n_num']} c{case['m_num']}."]
    return "\n".join(lines)


def discharge_note(case, rng):
    lines = _header(case, "DISCHARGE SUMMARY")
    stage = (f"  Final stage p{case['t_num']} p{case['n_num']} c{case['m_num']}"
             + (f" (stage {case['stage_group']}, AJCC 8th)."
                if case["omit"] != "stage_group" else "."))
    lines += [
        f"ADMISSION: elective, for {case['procedure']}.",
        "",
        "COURSE:",
        f"  Pt s/p {case['procedure']}. Uneventful recovery, no complications.",
        f"  Histology confirmed {case['histology']}.",
        stage,
        "",
        "PLAN: MDC discussion; adjuvant therapy per board decision.",
    ]
    return "\n".join(lines)


WRITERS = {
    "pathology": pathology_note,
    "radiology": radiology_note,
    "discharge_summary": discharge_note,
}


# --------------------------------------------------------------------------
# Gold labels -- mapped onto the nested ClinicalExtraction schema
# --------------------------------------------------------------------------

def build_label(case):
    """Assemble the gold ClinicalExtraction dict for one templated case."""
    doc = case["document_type"]
    cfg = SITES[case["site"]]
    missing = [case["omit"]] if case["omit"] else []

    label = {
        "document_type": doc,
        "document_date": case["doc_date"].isoformat(),
        "synthetic_patient_ref": case["patient_ref"],
        "primary_site": case["site"],
        "laterality": case["laterality"],
        "histology": None,
        "tnm": None,
        "biomarkers": [],
        "pathology": None,
        "radiology": None,
        "discharge": None,
        "meta": {
            "model": None,
            "confidence": None,
            "evidence_spans": [],
            "missing_fields": missing,
            "needs_human_review": False,
            "notes": "Synthetic gold label, correct by construction.",
        },
    }

    if doc == "pathology":
        label["histology"] = case["histology"]
        label["tnm"] = {
            "t": f"p{case['t_num']}", "n": f"p{case['n_num']}",
            "m": None, "stage_group": None, "staging_system": None,
        }
        label["pathology"] = {
            "specimen": case["procedure"],
            "histology": case["histology"],
            "grade": None if case["omit"] == "grade" else str(case["grade"]),
            "tumor_size_mm": None if case["omit"] == "tumor_size_mm"
                             else case["tumor_size_mm"],
            "margins": case["margins"],
            "lymphovascular_invasion": case["lvi"],
            "nodes_examined": case["nodes_examined"],
            "nodes_positive": case["nodes_positive"],
        }
        if case["site"] == "breast":
            label["biomarkers"] = [
                {"name": "ER", "value": case["er_value"]},
                {"name": "PR", "value": case["pr_value"]},
                {"name": "HER2", "value": case["her2_value"]},
            ]

    elif doc == "radiology":
        impression = (f"c{case['t_num']} c{case['n_num']} c{case['m_num']}.")
        label["tnm"] = {
            "t": f"c{case['t_num']}", "n": f"c{case['n_num']}",
            "m": f"c{case['m_num']}", "stage_group": None,
            "staging_system": None,
        }
        label["radiology"] = {
            "modality": cfg["modality"],
            "body_region": cfg["body_region"],
            "largest_lesion_mm": None if case["omit"] == "largest_lesion_mm"
                                 else case["tumor_size_mm"],
            "impression": impression,
            "recist_target_lesions": None,
        }

    else:  # discharge_summary
        label["histology"] = case["histology"]
        label["tnm"] = {
            "t": f"p{case['t_num']}", "n": f"p{case['n_num']}",
            "m": f"c{case['m_num']}",
            "stage_group": None if case["omit"] == "stage_group"
                           else case["stage_group"],
            "staging_system": None if case["omit"] == "stage_group" else "AJCC 8th",
        }
        label["discharge"] = {
            "admission_reason": f"elective, for {case['procedure']}",
            "procedures": [case["procedure"]],
            "complications": [],
            "followup_plan": "MDC discussion; adjuvant therapy per board decision.",
        }

    return label


# --------------------------------------------------------------------------
# Ambiguous cases: primary site genuinely indeterminate -> "other"
# --------------------------------------------------------------------------

AMBIGUOUS = [
    {
        "id": "other_ambiguous_01",
        "text": "\n".join([
            BANNER,
            "=== SURGICAL PATHOLOGY REPORT ===",
            "Accession: 412-77    Ref: SYNTH-5310",
            "Date: 04-Feb-2026",
            "Age: 63   Sex: F",
            "",
            "SPECIMEN: Left axillary lymph node, excision",
            "",
            "MICROSCOPIC:",
            "  Metastatic adenocarcinoma in LN. CK7+, CK20-, TTF-1-, GATA3 equivocal.",
            "  Breast and lung primaries both considered; imaging NAD.",
            "",
            "DIAGNOSIS: Metastatic adenocarcinoma, primary site not established (CUP).",
        ]),
        "label": {
            "document_type": "pathology",
            "document_date": "2026-02-04",
            "synthetic_patient_ref": "SYNTH-5310",
            "primary_site": "other",
            "laterality": "left",
            "histology": "Metastatic adenocarcinoma",
            "biomarkers": [
                {"name": "CK7", "value": "positive"},
                {"name": "CK20", "value": "negative"},
                {"name": "TTF-1", "value": "negative"},
                {"name": "GATA3", "value": "equivocal"},
            ],
            "pathology": {
                "specimen": "Left axillary lymph node, excision",
                "histology": "Metastatic adenocarcinoma",
            },
            "meta": {
                "missing_fields": ["primary_site", "grade", "tumor_size_mm"],
                "needs_human_review": True,
                "notes": "Carcinoma of unknown primary; site not established.",
            },
        },
    },
    {
        "id": "other_ambiguous_02",
        "text": "\n".join([
            BANNER,
            "=== RADIOLOGY REPORT - PET-CT ===",
            "Accession: 518-24    Ref: SYNTH-7742",
            "Date: 19-Apr-2026",
            "Age: 68   Sex: M",
            "",
            "FINDINGS:",
            "  FDG-avid thickening at the gastro-oesophageal junction, 44 mm,",
            "  Siewert type II. Epicentre straddles the GEJ; cannot reliably be",
            "  assigned to distal oesophagus vs proximal stomach.",
            "  Avid paraoesophageal and perigastric nodes.",
            "",
            "IMPRESSION: GEJ tumour, cT3 cN1 cM0. Site of origin indeterminate.",
        ]),
        "label": {
            "document_type": "radiology",
            "document_date": "2026-04-19",
            "synthetic_patient_ref": "SYNTH-7742",
            "primary_site": "other",
            "laterality": "not_applicable",
            "tnm": {"t": "cT3", "n": "cN1", "m": "cM0"},
            "radiology": {
                "modality": "PET-CT",
                "body_region": "whole body",
                "largest_lesion_mm": 44.0,
                "impression": "GEJ tumour, cT3 cN1 cM0. Site of origin indeterminate.",
            },
            "meta": {
                "missing_fields": ["primary_site"],
                "needs_human_review": True,
                "notes": "Siewert II GEJ tumour: stomach vs esophagus unresolved.",
            },
        },
    },
    {
        "id": "other_ambiguous_03",
        "text": "\n".join([
            BANNER,
            "=== DISCHARGE SUMMARY ===",
            "Accession: 226-08    Ref: SYNTH-2984",
            "Date: 30-Jun-2026",
            "Age: 57   Sex: F",
            "",
            "COURSE:",
            "  Admitted with ascites. Diagnostic laparoscopy: widespread peritoneal",
            "  carcinomatosis. Bx: high-grade adenocarcinoma.",
            "  IHC pattern non-specific; GI vs gynae primary unresolved at discharge.",
            "",
            "PLAN: MDC discussion. Further workup for primary.",
        ]),
        "label": {
            "document_type": "discharge_summary",
            "document_date": "2026-06-30",
            "synthetic_patient_ref": "SYNTH-2984",
            "primary_site": "other",
            "laterality": "not_applicable",
            "histology": "High-grade adenocarcinoma",
            "tnm": {"m": "cM1", "stage_group": "IV"},
            "discharge": {
                "admission_reason": "ascites",
                "procedures": ["Diagnostic laparoscopy"],
                "complications": [],
                "followup_plan": "MDC discussion. Further workup for primary.",
            },
            "meta": {
                "missing_fields": ["primary_site", "t", "n"],
                "needs_human_review": True,
                "notes": "Peritoneal carcinomatosis; GI vs gynae primary unresolved.",
            },
        },
    },
]


# --------------------------------------------------------------------------

def validate(label, note_id):
    try:
        return ClinicalExtraction.model_validate(label)
    except Exception as exc:
        print(f"\nGold label for '{note_id}' does not match ClinicalExtraction.\n"
              f"{exc}\n\nNothing was written.")
        sys.exit(1)


def main():
    rng = random.Random(SEED)
    NOTES_DIR.mkdir(parents=True, exist_ok=True)

    # Clear notes from a previous run so the corpus matches gold.jsonl exactly.
    for stale in NOTES_DIR.glob("*.txt"):
        stale.unlink()

    records = []
    for site in SITES:
        for doc_type in DOC_TYPES:
            for n in range(1, COPIES_PER_COMBINATION + 1):
                case = make_case(site, doc_type, rng, n)
                text = WRITERS[doc_type](case, rng)
                validated = validate(build_label(case), case["id"])
                records.append({"id": case["id"], "text": text,
                                "label": validated.model_dump(mode="json")})

    for entry in AMBIGUOUS:
        validated = validate(entry["label"], entry["id"])
        records.append({"id": entry["id"], "text": entry["text"],
                        "label": validated.model_dump(mode="json")})

    for rec in records:
        assert rec["text"].startswith(BANNER), rec["id"]
        (NOTES_DIR / f"{rec['id']}.txt").write_text(rec["text"], encoding="utf-8")

    with GOLD_PATH.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"Wrote {len(records)} notes to {NOTES_DIR}")
    print(f"Wrote gold labels to {GOLD_PATH}")


if __name__ == "__main__":
    main()
