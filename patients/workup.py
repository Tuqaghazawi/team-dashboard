"""Standard workup checklists.

Each specialty has a baseline set of investigations the team expects before a
patient can be discussed at MDC. This is the starting checklist; the guideline
brain (``ai/guidelines``) can suggest extras, and a fellow can always add or
remove items by hand — nothing here is enforced against the clinician.
"""

from .models import Investigation

K = Investigation.Kind

BASELINE_WORKUP = {
    "BREAST": [K.MAMMOGRAM, K.BREAST_US, K.PATHOLOGY, K.CAP_CT, K.BONE_SCAN, K.GENETICS],
    "THYROID": [K.NECK_US, K.FNA, K.PATHOLOGY, K.THYROID_FUNCTION],
    "COLORECTAL": [K.COLONOSCOPY, K.PATHOLOGY, K.CEA, K.CAP_CT, K.PELVIC_MRI],
    "HPB": [K.CAP_CT, K.ABDOMEN_MRI, K.PATHOLOGY, K.TUMOR_MARKERS],
    "UPPER_GI": [K.GASTROSCOPY, K.PATHOLOGY, K.CAP_CT, K.PET_CT],
    "SARCOMA": [K.LOCAL_MRI, K.PATHOLOGY, K.CAP_CT],
    "GENERAL": [K.PATHOLOGY, K.CAP_CT],
}

# What gets re-done after NACT / TNT, before the team re-discusses the patient.
RESTAGING_WORKUP = {
    "BREAST": [K.MAMMOGRAM, K.BREAST_US, K.CAP_CT],
    "COLORECTAL": [K.PELVIC_MRI, K.CAP_CT, K.CEA],
    "HPB": [K.CAP_CT, K.ABDOMEN_MRI],
    "UPPER_GI": [K.CAP_CT, K.PET_CT],
    "SARCOMA": [K.LOCAL_MRI, K.CAP_CT],
    "GENERAL": [K.CAP_CT],
    "THYROID": [K.NECK_US],
}


def create_baseline_workup(patient):
    """Create the baseline checklist for a patient. Returns the new items.

    Safe to call twice — existing items are left exactly as they are.
    """
    return _create(patient, BASELINE_WORKUP, Investigation.Purpose.BASELINE)


def create_restaging_workup(patient):
    """Create the restaging checklist after neoadjuvant treatment."""
    return _create(patient, RESTAGING_WORKUP, Investigation.Purpose.RESTAGING)


def _create(patient, template, purpose):
    kinds = template.get(patient.specialty, template["GENERAL"])
    existing = set(
        patient.investigations.filter(purpose=purpose).values_list("kind", flat=True)
    )
    created = []
    for kind in kinds:
        if kind in existing:
            continue
        created.append(
            Investigation.objects.create(patient=patient, kind=kind, purpose=purpose)
        )
    return created
