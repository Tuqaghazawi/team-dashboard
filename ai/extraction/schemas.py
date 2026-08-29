"""
Clinical Extraction System - core schema (Capstone 1).
Pydantic v2. Schema-bound structured output for MIXED oncology documents.

Design decisions (each one is defensible in your PRD):

1. One `ClinicalExtraction` object per source document. `document_type`
   and `phase` route which type-specific block gets filled, but ALL
   blocks are Optional so the model degrades gracefully on messy /
   mixed input instead of hard-failing. That is the "real-world
   variability" the capstone asks you to demonstrate.

2. Breast is modelled in TWO phase-specific blocks - `breast_diagnostic`
   (core biopsy) and `breast_postop` (resection) - because the fields a
   diagnostic report can support are a different set from a resection.
   `phase` tells the model which one to fill.

3. Every clinical field is Optional, and the model records what it
   could NOT find in `meta.missing_fields`. Missing is not the same as
   wrong - separating them is what lets you report field-level RECALL,
   not just accuracy.

4. `meta.confidence`, `meta.evidence_spans`, and `meta.needs_human_review`
   exist to support the human-review path (Session 5 sign-off) and the
   error analysis the capstone and Session 7 eval require.

5. NO patient identifiers here (name / MRN / DOB). The extractor pulls
   CLINICAL CONTENT, not identity - a deliberate governance choice you
   can point to. Link to the dashboard's synthetic patient via a
   non-PHI `synthetic_patient_ref` token only.

6. Field names here MATCH the gold-label keys exactly, because the
   evaluator (`ai/eval/accuracy.py`) compares by dotted path. A rename
   here is a silent miss there.

7. `ClinicalExtraction` sets extra="forbid": any key not defined below
   is rejected, so a schema/label drift can never silently pass again.
   This re-arms the model_validate() check that was previously a no-op.

This same class is reused as the GOLD-LABEL type when you build the
synthetic dataset, so your labels are guaranteed schema-valid by
construction.
"""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class DocumentType(str, Enum):
    pathology = "pathology"
    radiology = "radiology"
    discharge_summary = "discharge_summary"
    other = "other"


class Phase(str, Enum):
    diagnostic = "diagnostic"      # core / tru-cut biopsy
    post_op = "post_op"            # resection specimen
    not_applicable = "not_applicable"


class PrimarySite(str, Enum):
    breast = "breast"
    colon = "colon"
    rectum = "rectum"
    thyroid = "thyroid"
    stomach = "stomach"        # upper GI
    esophagus = "esophagus"    # upper GI
    other = "other"


class Laterality(str, Enum):
    left = "left"
    right = "right"
    bilateral = "bilateral"
    not_applicable = "not_applicable"
    unknown = "unknown"


class TNM(BaseModel):
    t: Optional[str] = Field(None, description="T category verbatim, e.g. 'pT2', 'cT3', 'ypT2(m)'")
    n: Optional[str] = Field(None, description="N category verbatim, e.g. 'pN1', 'cN0', 'N0(sn)'")
    m: Optional[str] = Field(None, description="M category verbatim, e.g. 'cM0', 'pM1'")
    stage_group: Optional[str] = Field(None, description="e.g. 'IIA', 'IV'")
    staging_system: Optional[str] = Field(None, description="e.g. 'AJCC 8th'")


class Biomarker(BaseModel):
    # Keep `value` a string - biomarker results are wildly heterogeneous
    # (positive / 3+ / MSI-high / p.G12D / 15%). Normalize later, not here.
    name: str = Field(..., description="e.g. 'ER', 'PR', 'HER2', 'Ki67', 'MMR', 'MSI', 'KRAS', 'BRAF'")
    value: str = Field(..., description="verbatim result")


class PathologyDetails(BaseModel):
    specimen: Optional[str] = None
    histology: Optional[str] = Field(None, description="e.g. 'invasive ductal carcinoma'")
    grade: Optional[str] = None
    tumor_size_mm: Optional[float] = Field(
        None,
        description="Largest invasive dimension in MILLIMETRES. If the report states cm, convert (cm x 10).",
    )
    margins: Optional[str] = Field(None, description="e.g. 'negative', 'positive at deep margin'")
    lymphovascular_invasion: Optional[bool] = Field(
        None,
        description="true = explicitly identified; false = explicitly 'not identified'; "
                    "null = not mentioned. Do not infer false from silence.",
    )
    nodes_examined: Optional[int] = None
    nodes_positive: Optional[int] = None


class RadiologyDetails(BaseModel):
    modality: Optional[str] = Field(None, description="e.g. 'CT', 'MRI', 'US', 'PET-CT'")
    body_region: Optional[str] = None
    largest_lesion_mm: Optional[float] = Field(
        None,
        description="Largest lesion dimension in MILLIMETRES. If the report states cm, convert (cm x 10).",
    )
    impression: Optional[str] = Field(None, description="short summary of the read")
    recist_target_lesions: Optional[int] = None


class DischargeDetails(BaseModel):
    admission_reason: Optional[str] = None
    procedures: list[str] = Field(default_factory=list)
    complications: list[str] = Field(default_factory=list)
    followup_plan: Optional[str] = None


# ----------------------------------------------------------------------
# Breast-specific blocks. Field names mirror the gold labels exactly.
# ----------------------------------------------------------------------

class HormoneReceptor(BaseModel):
    """ER / PR result."""
    status: Optional[str] = Field(None, description="'positive' or 'negative' (>=1% staining = positive)")
    intensity: Optional[str] = Field(
        None, description="'weak' / 'moderate' / 'strong'; 'not_reported' if positive without intensity"
    )
    percent_positive: Optional[float] = Field(
        None, description="percent of tumour-cell nuclei staining; null if negative or not stated"
    )
    verbatim: Optional[str] = Field(None, description="source phrase, if you want to keep it")


class Her2(BaseModel):
    status: Optional[str] = Field(None, description="'negative' / 'equivocal' / 'positive'")
    score: Optional[str] = Field(None, description="IHC score verbatim: '0', '1+', '2+', '3+'")
    verbatim: Optional[str] = None


class BreastReceptors(BaseModel):
    er: Optional[HormoneReceptor] = None
    pr: Optional[HormoneReceptor] = None
    her2: Optional[Her2] = None
    ki67_percent: Optional[float] = Field(None, description="Ki-67 labelling index as a percent; null if not reported")


class BreastSpecimen(BaseModel):
    """One core / part from a diagnostic breast biopsy."""
    label: Optional[str] = Field(None, description="specimen header, e.g. 'LEFT BREAST MASS; TRU CUT BIOPSY'")
    laterality: Optional[str] = None
    site: Optional[str] = Field(None, description="clock position or quadrant, e.g. '10:00 o'clock'")
    procedure: Optional[str] = Field(None, description="e.g. 'tru-cut biopsy'")
    diagnosis_text: Optional[str] = Field(None, description="verbatim diagnosis line for this specimen")
    histology: Optional[str] = Field(None, description="null if the specimen is benign / no carcinoma")
    grade: Optional[str] = Field(None, description="null if benign")
    tumor_size_verbatim: Optional[str] = Field(None, description="size as written, e.g. '2.5 cm'; null if not given")
    tumor_size_mm: Optional[float] = Field(
        None,
        description="Largest dimension in MILLIMETRES. If the report states cm, convert (cm x 10). "
                    "Null if no size is reported.",
    )
    carcinoma_present: Optional[bool] = Field(
        None,
        description="true if carcinoma is present in THIS specimen; false if benign / 'no carcinoma present'.",
    )


class BreastDiagnostic(BaseModel):
    """Core-biopsy phase."""
    specimens: list[BreastSpecimen] = Field(default_factory=list)
    receptors: Optional[BreastReceptors] = None
    axilla_biopsy_present: Optional[bool] = Field(
        None,
        description="Is an axillary / sentinel-node specimen part of THIS report? "
                    "false = a complete report with no axillary tissue submitted (typical for a core biopsy); "
                    "true = present; null only if the report is truncated / ambiguous. "
                    "Do NOT leave null merely because the axilla is unmentioned in an otherwise complete report.",
    )


class BreastPostop(BaseModel):
    """Resection phase."""
    neoadjuvant_given: Optional[bool] = Field(
        None,
        description="true = report states neoadjuvant / 'S/P chemotherapy' or gives a treatment-effect result; "
                    "false = a complete resection report that is treatment-naive (treatment effect N/A); "
                    "null only if genuinely indeterminate. Do NOT infer false from silence.",
    )
    procedure: Optional[str] = Field(None, description="e.g. 'Mastectomy', 'Wide local excision'")
    histologic_type: Optional[str] = Field(
        None, description="tumour type WITHOUT modifiers like 'residual'/'bifocal', e.g. 'Invasive lobular carcinoma'"
    )
    grade: Optional[str] = None
    focality: Optional[str] = Field(
        None, description="'unifocal' / 'bifocal' / 'multifocal'. If macroscopic and microscopic disagree, use microscopic."
    )
    largest_invasive_size_verbatim: Optional[str] = Field(None, description="size as written, e.g. '2.9 cm'")
    largest_invasive_size_mm: Optional[float] = Field(
        None,
        description="Largest invasive focus in MILLIMETRES. If the report states cm, convert (cm x 10).",
    )
    dcis_present: Optional[bool] = Field(
        None, description="true = 'Present'; false = 'Not identified'; null = not mentioned."
    )
    lymphovascular_invasion: Optional[bool] = Field(
        None, description="true = 'Present'; false = 'Not seen'/'Not identified'; null = not mentioned."
    )
    perineural_invasion: Optional[bool] = Field(
        None, description="true = 'Present'; false = 'Not seen'/'Not identified'; null = not mentioned."
    )
    margin_status: Optional[str] = Field(None, description="overall margin: 'free' or 'involved'")
    nearest_margin: Optional[str] = Field(None, description="e.g. 'deep', 'superior', 'lateral'")
    nearest_margin_distance_verbatim: Optional[str] = Field(None, description="e.g. '2.3 cm'")
    node_type: Optional[str] = Field(None, description="'sentinel' or 'axillary clearance'")
    nodes_examined: Optional[int] = None
    nodes_positive: Optional[int] = None
    largest_nodal_deposit_mm: Optional[float] = Field(
        None,
        description="Largest nodal metastatic deposit in MILLIMETRES. If the report states cm, convert (cm x 10). "
                    "Null if no positive nodes.",
    )
    extranodal_extension: Optional[bool] = Field(
        None, description="true / false when nodes are positive; null when not applicable (no positive nodes)."
    )
    treatment_effect_breast: Optional[str] = Field(
        None, description="'complete' / 'partial' / 'focal' / 'absent'; null if no neoadjuvant therapy."
    )
    treatment_effect_nodes: Optional[str] = Field(
        None, description="'present' / 'absent'; null if no neoadjuvant therapy."
    )
    pathologic_stage: Optional[str] = Field(None, description="full stage string, e.g. 'ypT2(m)N0(sn)'")


class ExtractionMetadata(BaseModel):
    model: Optional[str] = Field(None, description="model + version that produced this")
    confidence: Optional[float] = Field(None, ge=0, le=1, description="model self-rated 0-1")
    evidence_spans: list[str] = Field(
        default_factory=list,
        description="verbatim snippets from the source that justify key fields",
    )
    missing_fields: list[str] = Field(
        default_factory=list,
        description="fields expected for this doc type but not found - for recall",
    )
    needs_human_review: bool = Field(
        False,
        description="Set true when the report needs a human before sign-off. ALWAYS true when: "
                    "the macroscopic and microscopic descriptions state DIFFERENT focality "
                    "(e.g. macro 'unifocal' but micro 'bifocal'/'multifocal') - flag it even "
                    "though you record the microscopic value; HER2 IHC is equivocal (2+) pending "
                    "reflex ISH; margins are positive/involved; or there is any safety-relevant ambiguity.",
    )


class ClinicalExtraction(BaseModel):
    """One structured record per source document."""

    model_config = ConfigDict(extra="forbid")

    # --- provenance / routing ---
    document_type: DocumentType
    phase: Optional[Phase] = Field(
        None, description="'diagnostic' (core biopsy) or 'post_op' (resection); null if not applicable"
    )
    document_date: Optional[str] = Field(None, description="ISO date if stated, else null")
    synthetic_patient_ref: Optional[str] = Field(
        None, description="non-PHI link to the dashboard's synthetic patient"
    )

    # --- shared oncology core ---
    primary_site: Optional[PrimarySite] = None
    laterality: Laterality = Laterality.unknown
    histology: Optional[str] = Field(
        None,
        description="tumour type WITHOUT modifiers like 'residual' / 'bifocal', e.g. 'Invasive lobular carcinoma'",
    )
    tnm: Optional[TNM] = None
    biomarkers: list[Biomarker] = Field(default_factory=list)

    # --- type-specific blocks: fill the one matching document_type + phase ---
    pathology: Optional[PathologyDetails] = Field(
        None,
        description="Generic fallback for NON-breast sites only. "
                    "For breast, leave null and use breast_diagnostic / breast_postop.",
    )
    radiology: Optional[RadiologyDetails] = None
    discharge: Optional[DischargeDetails] = None
    breast_diagnostic: Optional[BreastDiagnostic] = None
    breast_postop: Optional[BreastPostop] = None

    # --- extraction metadata: human review + evaluation ---
    meta: ExtractionMetadata = Field(default_factory=ExtractionMetadata)