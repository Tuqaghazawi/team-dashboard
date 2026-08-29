"""
Generate a LABELED SYNTHETIC BREAST test set in KHCC report format.

Two report types:
  - diagnostic (tru-cut core biopsy)  -> fills breast_diagnostic
  - post_op    (resection)            -> fills breast_postop

Labels are built from the SAME randomized values used to write each note,
so they are correct by construction and validated against the schema.

Run from PROJECT ROOT:
    .venv\\Scripts\\python.exe scripts\\generate_breast.py
"""
import json
import random
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from ai.extraction.schemas import ClinicalExtraction  # noqa: E402

random.seed(42)  # reproducible set

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT_NOTES = REPO_ROOT / "data" / "synthetic" / "breast" / "notes"
OUT_GOLD = REPO_ROOT / "data" / "synthetic" / "breast" / "gold_breast.jsonl"

BOILERPLATE = (
    "Immunohistochemical stains were performed on formalin fixed paraffin embedded "
    "sections using automated immunostaining (LSAB). Antibody clones: ER: SP1; PR: 1E2; "
    "HER-2/neu: 4B5 (Ventana). ER/PR: any staining >=1% is positive. HER-2 per ASCO/CAP "
    "(Wolff 2013): Score 0 none/faint <=10%; Score 1 faint >10%; Score 2 weak-moderate "
    "circumferential >10% (equivocal); Score 3 intense complete >10% (positive)."
)

HISTOS = ["Invasive ductal carcinoma", "Invasive lobular carcinoma",
          "Invasive mammary carcinoma", "Invasive carcinoma of no special type"]
SITES = ["10:00 o'clock", "7:00 o'clock", "upper outer quadrant",
         "lower inner quadrant", "mid outer", "near nipple"]


def her2_from_score(score):
    return {"0": "negative", "1+": "negative", "2+": "equivocal", "3+": "positive"}[score]


def receptor_note_line(name, pct, intensity):
    if pct >= 1:
        return f"{name}: Positive, {intensity}, in {pct}% of tumor cell nuclei."
    return f"{name}: Negative (internal control present)."


def make_diagnostic(i):
    lat = random.choice(["left", "right"])
    histo = random.choice(HISTOS)
    grade = random.choice(["1", "2", "3"])
    site = random.choice(SITES)
    has_size = random.random() > 0.25
    size_cm = round(random.uniform(0.4, 3.4), 1) if has_size else None
    two_cores = random.random() > 0.5
    benign_second = two_cores and random.random() > 0.4

    er_pct = random.choice([0, 1, 30, 60, 80, 90, 95])
    pr_pct = random.choice([0, 1, 40, 70, 85, 90])
    er_int = random.choice(["weak", "moderate", "strong"])
    pr_int = random.choice(["weak", "moderate", "strong"])
    her2_score = random.choice(["0", "0", "1+", "2+", "3+"])
    her2_status = her2_from_score(her2_score)

    # ---- note text ----
    lines = ["=== SURGICAL PATHOLOGY REPORT ===", "SYNTHETIC - not for clinical use", ""]
    size_txt = f", {size_cm} cm in maximum linear extent" if size_cm else ""
    lines.append(f"1- {lat.upper()} BREAST MASS AT {site}; TRU CUT BIOPSY: {histo}; grade {grade}{size_txt}. See note.")
    if two_cores:
        site2 = random.choice(SITES)
        if benign_second:
            lines.append(f"2- {lat.upper()} BREAST MASS; {site2}; TRU CUT BIOPSY: Fragments of skin and connective tissue. No carcinoma present.")
        else:
            lines.append(f"2- {lat.upper()} BREAST MASS AT {site2}; TRU CUT BIOPSY: {histo}; grade {grade}. See note.")
    her2_txt = {"0": "Negative (Score 0)", "1+": "Negative, Score (1+)",
                "2+": "Equivocal, score (2+)", "3+": "Positive (Score 3+)"}[her2_score]
    lines += ["", "NOTE:",
              receptor_note_line("Estrogen receptors", er_pct, er_int),
              receptor_note_line("Progesterone receptors", pr_pct, pr_int),
              f"HER-2/neu over expression: {her2_txt}.", BOILERPLATE]
    text = "\n".join(lines)

    # ---- gold label ----
    def spec(site_, dx, hist, gr, benign=False):
        return {
            "label": f"{lat.upper()} BREAST MASS; TRU CUT BIOPSY",
            "laterality": lat, "site": site_, "procedure": "tru-cut biopsy",
            "diagnosis_text": dx, "histology": None if benign else hist,
            "grade": None if benign else gr,
            "tumor_size_verbatim": f"{size_cm} cm" if (size_cm and not benign) else None,
            "tumor_size_mm": (size_cm * 10) if (size_cm and not benign) else None,
            "carcinoma_present": (not benign),
        }
    specimens = [spec(site, f"{histo}; grade {grade}", histo, grade)]
    if two_cores:
        if benign_second:
            specimens.append(spec("second core", "Fragments of skin and connective tissue. No carcinoma present.", None, None, benign=True))
        else:
            specimens.append(spec("second core", f"{histo}; grade {grade}", histo, grade))

    def hr(pct, inten):
        return {"status": "positive" if pct >= 1 else "negative",
                "intensity": inten if pct >= 1 else "not_reported",
                "percent_positive": float(pct) if pct >= 1 else None,
                "verbatim": None}
    needs_review = (her2_score == "2+")
    label = {
        "document_type": "pathology", "phase": "diagnostic",
        "primary_site": "breast", "laterality": lat, "histology": histo,
        "breast_diagnostic": {
            "specimens": specimens,
            "receptors": {"er": hr(er_pct, er_int), "pr": hr(pr_pct, pr_int),
                          "her2": {"status": her2_status, "score": her2_score, "verbatim": None},
                          "ki67_percent": None},
            "axilla_biopsy_present": False,
        },
        "meta": {"needs_human_review": needs_review,
                 "notes": "Equivocal HER2 (2+): reflex ISH indicated." if needs_review else None,
                 "missing_fields": ([] if size_cm else ["tumor_size"])},
    }
    return f"breast_diag_{i:02d}", text, label


def make_postop(i):
    lat = random.choice(["left", "right"])
    neoadj = random.random() > 0.4
    procedure = random.choice(["Mastectomy", "Wide local excision"])
    histo = random.choice(HISTOS)
    grade = random.choice(["2", "3"])
    node_type = random.choice(["sentinel", "axillary clearance"])
    examined = random.randint(2, 5) if node_type == "sentinel" else random.randint(8, 22)
    positive = 0 if random.random() > 0.5 else random.randint(1, max(1, examined // 2))
    size_cm = round(random.uniform(0.4, 4.5), 1)
    lvi = random.random() > 0.6
    pni = random.random() > 0.6
    dcis = random.random() > 0.5
    # focality + deliberate macro/micro inconsistency in ~1/3
    micro_focality = random.choice(["unifocal", "multifocal", "bifocal"])
    force_mismatch = random.random() > 0.66
    macro_focality = "unifocal" if (force_mismatch and micro_focality != "unifocal") else micro_focality
    inconsistent = (macro_focality != micro_focality)   # flag follows the actual text, not the dice
    multi = micro_focality in ("multifocal", "bifocal")
    # T from size, N from nodes
    size_mm = size_cm * 10
    t = "T1" if size_mm <= 20 else ("T2" if size_mm <= 50 else "T3")
    n = "N0" if positive == 0 else ("N1" if positive <= 3 else ("N2" if positive <= 9 else "N3"))
    prefix = "yp" if neoadj else "p"
    t_full = f"{prefix}{t}" + ("(m)" if multi else "")
    n_full = f"{n}" + ("(sn)" if (node_type == "sentinel" and positive == 0) else "")
    stage = f"{t_full}{n_full}"

    ene = None if positive == 0 else (random.random() > 0.5)
    deposit_mm = round(random.uniform(0.2, 2.5), 1) if positive > 0 else None
    tx_breast = random.choice(["complete", "partial", "focal", "absent"]) if neoadj else None
    tx_nodes = random.choice(["present", "absent"]) if neoadj else None
    margin_status = random.choice(["free", "involved"])
    nearest = random.choice(["deep", "superior", "lateral"])
    dist = round(random.uniform(0.1, 2.5), 1)

    # ---- note text ----
    nact_clause = ", S/P neoadjuvant chemotherapy" if neoadj else ""
    residual = "Residual " if neoadj else ""
    lvi_txt = "Present" if lvi else "Not seen"
    pni_txt = "Present" if pni else "Not seen"
    dcis_txt = "Present" if dcis else "Not identified"
    ene_txt = ("Present" if ene else "Not identified") if positive > 0 else "Not applicable"
    deposit_txt = f"{deposit_mm} mm" if deposit_mm else "Not applicable"
    tx_txt = (f"In the Breast: {tx_breast}. In the Lymph Nodes: {tx_nodes}." if neoadj else "Not applicable.")
    lines = [
        "=== SURGICAL PATHOLOGY REPORT ===", "SYNTHETIC - not for clinical use", "",
        f"CLINICAL HISTORY: A case of {lat} breast carcinoma{nact_clause}.", "",
        "TISSUE ORIGIN:", f"A - {lat} axilla {node_type} lymph nodes.", f"B - {lat} breast.", "",
        "MACROSCOPIC DESCRIPTION:",
        f'B - "{procedure.upper()}". Procedure: {procedure}. Side: {lat}. Focality: {macro_focality}. Nearest margin: {nearest}, distance {dist} cm.', "",
        "MICROSCOPIC DESCRIPTION:",
        f"Histologic type: {residual}{micro_focality} {histo.lower()}.",
        f"Grade: {grade}.", f"DCIS component: {dcis_txt}.",
        f"Size of largest invasive component: {size_cm} cm.",
        f"Margins: nearest {nearest}, {dist} cm; overall {margin_status}.",
        f"Lymphovascular invasion: {lvi_txt}.", f"Perineural invasion: {pni_txt}.",
        f"{node_type.title()} lymph nodes: Number examined ({examined}), Number involved ({positive}).",
        f"Size of largest metastatic deposit: {deposit_txt}.",
        f"Extranodal invasion: {ene_txt}.", f"Treatment effect: {tx_txt}", "",
        "DIAGNOSIS:",
        f"B - {lat.upper()} BREAST; {procedure.upper()}: {residual}{micro_focality} {histo.lower()}, grade {grade}, {size_cm} cm.",
        f"Pathologic stage: {stage}.",
    ]
    text = "\n".join(lines)

    label = {
        "document_type": "pathology", "phase": "post_op",
        "primary_site": "breast", "laterality": lat, "histology": histo,
        "tnm": {"t": t_full, "n": n_full, "m": None, "stage_group": None, "staging_system": None},
        "breast_postop": {
            "neoadjuvant_given": neoadj, "procedure": procedure, "histologic_type": histo,
            "grade": grade, "focality": micro_focality,
            "largest_invasive_size_verbatim": f"{size_cm} cm", "largest_invasive_size_mm": size_mm,
            "dcis_present": dcis, "lymphovascular_invasion": lvi, "perineural_invasion": pni,
            "margin_status": margin_status, "nearest_margin": nearest,
            "nearest_margin_distance_verbatim": f"{dist} cm", "node_type": node_type,
            "nodes_examined": examined, "nodes_positive": positive,
            "largest_nodal_deposit_mm": deposit_mm, "extranodal_extension": ene,
            "treatment_effect_breast": tx_breast, "treatment_effect_nodes": tx_nodes,
            "pathologic_stage": stage,
        },
        "meta": {"needs_human_review": inconsistent,
                 "notes": "Macro/micro focality inconsistency; microscopic used." if inconsistent else None,
                 "missing_fields": []},
    }
    return f"breast_postop_{i:02d}", text, label


def main():
    OUT_NOTES.mkdir(parents=True, exist_ok=True)
    records = []
    for i in range(1, 13):        # 12 diagnostic
        records.append(make_diagnostic(i))
    for i in range(1, 9):         # 8 post-op
        records.append(make_postop(i))

    for note_id, text, label in records:
        ClinicalExtraction.model_validate(label)   # correctness guarantee
        (OUT_NOTES / f"{note_id}.txt").write_text(text, encoding="utf-8")

    with open(OUT_GOLD, "w", encoding="utf-8") as f:
        for note_id, text, label in records:
            f.write(json.dumps({"id": note_id, "text": text, "label": label}) + "\n")

    diag = sum(1 for r in records if r[0].startswith("breast_diag"))
    print(f"Wrote {len(records)} breast notes ({diag} diagnostic, {len(records)-diag} post-op)")
    print(f"Notes: {OUT_NOTES}")
    print(f"Gold:  {OUT_GOLD}")


if __name__ == "__main__":
    main()