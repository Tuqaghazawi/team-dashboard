"""Standard workup checklists, per diagnosis, with conditional items.

Two things this has to get right that a flat list per specialty could not:

* **Colon and rectum are different workups.** Pelvic MRI and a DRE for tumour
  distance are rectal. Oesophageal is not gastric. Liver is not pancreas. So the
  checklist is keyed on the *diagnosis group* (``patients.diagnosis``), not the
  specialty.

* **Some items depend on the patient.** Breast staging is conditional — an early
  cancer gets abdomen ultrasound and a chest X-ray, a locally advanced or
  node-positive one gets a CAP CT instead. Genetic testing is offered under 65 or
  with a family history. Fertility counselling is for women under 40.

Every conditional item records **why** it was added, on the investigation itself,
so the fellow can see the reasoning and change it. Nothing here is enforced: a
fellow can add or remove any item by hand.

Clinical source: PRD Appendix A, signed off 5 September 2026.
"""

import re
from dataclasses import dataclass, field

from .diagnosis import Group, group_for
from .models import Investigation

K = Investigation.Kind


@dataclass(frozen=True)
class Item:
    """One checklist line, and the rule that decides whether it applies."""

    kind: str
    required: bool = True
    when: object = None       # callable(patient) -> bool, or None for "always"
    why: str = ""             # recorded on the investigation when conditional

    def applies_to(self, patient):
        return True if self.when is None else bool(self.when(patient))


# --- the conditions -----------------------------------------------------------

# T3/T4, any positive node, or stage III/IV reads as locally advanced.
ADVANCED = re.compile(r"(T\s*[34]|N\s*[123]|N\s*\+|\bIII\b|\bIV\b)", re.I)


def stage_recorded(patient):
    return bool((patient.clinical_stage or "").strip())


def locally_advanced(patient):
    """True when the recorded clinical stage reads as locally advanced or node+."""
    return bool(ADVANCED.search(patient.clinical_stage or ""))


def early_stage(patient):
    """Early only when a stage is recorded *and* it is not advanced.

    An unrecorded stage is not treated as early — see ``full_staging`` below.
    """
    return stage_recorded(patient) and not locally_advanced(patient)


def full_staging(patient):
    """Locally advanced, or no stage recorded yet.

    With no stage on file we cannot tell, so the fuller staging is listed and the
    reason says so. Under-staging a patient is the worse error.
    """
    return not stage_recorded(patient) or locally_advanced(patient)


def female_under_40(patient):
    return patient.sex == "F" and patient.age < 40


def breast_genetics(patient):
    return patient.age < 65 or bool((patient.family_history or "").strip())


# No leading word boundary: in "T3N1M1" the M follows a digit, so \bM1 would
# never match. The trailing boundary is enough to pin it.
METASTATIC = re.compile(r"(M1\b|\bIV\b|metasta)", re.I)


def metastatic(patient):
    return bool(
        METASTATIC.search(patient.clinical_stage or "")
        or METASTATIC.search(patient.diagnosis or "")
    )


def _why_staging(patient):
    if not stage_recorded(patient):
        return "clinical stage not recorded — fuller staging listed; remove if early"
    return f"locally advanced or node-positive ({patient.clinical_stage})"


# --- the checklists -----------------------------------------------------------

# Applies to every patient, whatever the diagnosis.
UNIVERSAL = [
    Item(K.PATHOLOGY),
    Item(K.PATH_REVIEW, why="tumour-board pathology review for every patient"),
    Item(K.CBC),
    Item(K.CMP),
    Item(K.PERFORMANCE_STATUS),
    Item(K.PRIOR_IMAGING),
    Item(K.FERTILITY, when=female_under_40, why="female patient under 40"),
]

BY_GROUP = {
    Group.BREAST: [
        Item(K.MAMMOGRAM),
        Item(K.BREAST_US),
        Item(K.BIOMARKERS, why="ER/PR/HER2 and Ki-67 on the core biopsy"),
        Item(K.BREAST_MRI, required=False, why="selected cases"),
        # Conditional staging — one of these two, never both.
        Item(K.ABDOMEN_US, when=early_stage, why="early breast cancer — abdomen US and CXR replace CAP CT"),
        Item(K.CXR, when=early_stage, why="early breast cancer — abdomen US and CXR replace CAP CT"),
        Item(K.CAP_CT, when=full_staging, why=_why_staging),
        Item(K.BONE_SCAN, when=full_staging, why=_why_staging),
        Item(K.GENETICS, when=breast_genetics, why="under 65, or a positive family history"),
    ],
    Group.COLON: [
        Item(K.COLONOSCOPY),
        Item(K.CAP_CT),
        Item(K.CEA),
        Item(K.MMR_MSI),
        Item(K.RAS_BRAF, when=metastatic, why="metastatic disease"),
    ],
    Group.RECTUM: [
        Item(K.PELVIC_MRI, why="the key rectal staging investigation"),
        Item(K.COLONOSCOPY),
        Item(K.DRE, why="tumour distance from the anal verge"),
        Item(K.CAP_CT),
        Item(K.CEA),
        Item(K.MMR_MSI),
        Item(K.RAS_BRAF, when=metastatic, why="metastatic disease"),
    ],
    Group.THYROID: [
        Item(K.NECK_US),
        Item(K.FNA, why="Bethesda category"),
        Item(K.THYROID_FUNCTION),
        Item(K.LARYNGOSCOPY, why="vocal cord assessment before thyroid surgery"),
        Item(K.CALCITONIN, required=False, why="if medullary carcinoma is suspected"),
        Item(K.RET_GENETIC, required=False, why="for medullary carcinoma"),
    ],
    Group.GASTRIC: [
        Item(K.GASTROSCOPY),
        Item(K.HER2),
        Item(K.EUS),
        Item(K.CAP_CT),
        Item(K.CEA),
        Item(K.STAGING_LAP, required=False, why="selected cases"),
    ],
    Group.ESOPHAGEAL: [
        Item(K.GASTROSCOPY),
        Item(K.EUS),
        Item(K.PET_CT),
        Item(K.CAP_CT),
        Item(K.HER2),
        Item(K.PD_L1),
    ],
    Group.PANCREAS: [
        Item(K.PANCREAS_CT, why="pancreas-protocol CT"),
        Item(K.CA_19_9),
        Item(K.EUS, why="EUS with biopsy"),
        Item(K.MRCP),
    ],
    Group.BILIARY: [
        Item(K.MRCP),
        Item(K.PANCREAS_CT),
        Item(K.CA_19_9),
        Item(K.EUS, required=False, why="EUS with biopsy where accessible"),
    ],
    Group.LIVER: [
        Item(K.TRIPHASIC, why="triphasic CT or MRI"),
        Item(K.AFP),
        Item(K.HEPATITIS),
        Item(K.CHILD_PUGH),
    ],
    Group.SARCOMA: [
        Item(K.LOCAL_MRI, why="MRI of the primary site"),
        Item(K.FNA, why="core biopsy, ideally at a sarcoma centre"),
        Item(K.CAP_CT, why="chest screening for metastases"),
    ],
    Group.OTHER: [
        Item(K.CAP_CT),
    ],
}

# What gets repeated after NACT / TNT, before the team re-discusses the patient.
RESTAGING = {
    Group.BREAST: [Item(K.MAMMOGRAM), Item(K.BREAST_US), Item(K.CAP_CT)],
    Group.COLON: [Item(K.CAP_CT), Item(K.CEA)],
    Group.RECTUM: [Item(K.PELVIC_MRI), Item(K.CAP_CT), Item(K.CEA)],
    Group.THYROID: [Item(K.NECK_US)],
    Group.GASTRIC: [Item(K.CAP_CT), Item(K.GASTROSCOPY)],
    Group.ESOPHAGEAL: [Item(K.CAP_CT), Item(K.PET_CT)],
    Group.PANCREAS: [Item(K.PANCREAS_CT), Item(K.CA_19_9)],
    Group.BILIARY: [Item(K.PANCREAS_CT), Item(K.CA_19_9)],
    Group.LIVER: [Item(K.TRIPHASIC), Item(K.AFP)],
    Group.SARCOMA: [Item(K.LOCAL_MRI), Item(K.CAP_CT)],
    Group.OTHER: [Item(K.CAP_CT)],
}


# --- building a patient's checklist -------------------------------------------

def baseline_items(patient):
    """The baseline checklist this patient should have, conditions applied."""
    group = group_for(patient)
    return [
        item for item in UNIVERSAL + BY_GROUP.get(group, BY_GROUP[Group.OTHER])
        if item.applies_to(patient)
    ]


def restaging_items(patient):
    group = group_for(patient)
    return [
        item for item in RESTAGING.get(group, RESTAGING[Group.OTHER])
        if item.applies_to(patient)
    ]


def create_baseline_workup(patient):
    """Create the baseline checklist for a patient. Returns the new items.

    Safe to call twice — existing items are left exactly as they are, results
    and all.
    """
    return _create(patient, baseline_items(patient), Investigation.Purpose.BASELINE)


def create_restaging_workup(patient):
    """Create the restaging checklist after neoadjuvant treatment."""
    return _create(patient, restaging_items(patient), Investigation.Purpose.RESTAGING)


def _create(patient, items, purpose):
    existing = set(
        patient.investigations.filter(purpose=purpose).values_list("kind", flat=True)
    )
    created = []
    for item in items:
        if item.kind in existing:
            continue
        why = item.why(patient) if callable(item.why) else item.why
        created.append(
            Investigation.objects.create(
                patient=patient,
                kind=item.kind,
                purpose=purpose,
                required=item.required,
                rationale=why,
            )
        )
        existing.add(item.kind)
    return created


# Kept so older callers and the EHR builder keep working: the plain list of kinds
# a patient of this group would be given, with no conditions applied.
def kinds_for_group(group, purpose=Investigation.Purpose.BASELINE):
    source = BY_GROUP if purpose == Investigation.Purpose.BASELINE else RESTAGING
    universal = UNIVERSAL if purpose == Investigation.Purpose.BASELINE else []
    return [item.kind for item in universal + source.get(group, source[Group.OTHER])]
