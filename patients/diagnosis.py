"""Working out which disease a patient actually has.

Specialty is too coarse to drive a workup. "Colorectal" covers colon and rectum,
whose workups differ — pelvic MRI and a DRE for tumour distance are rectal, not
colonic. "Upper GI" covers gastric and oesophageal. "HPB" covers pancreas,
biliary tree and liver, which share almost nothing.

So the diagnosis text decides, and the specialty is only the fallback. One module
does this because two things depend on it — the workup checklist
(``patients.workup``) and the guideline coverage check
(``ai.guidelines.suggest``) — and they must never disagree about what a patient
has.

The matching is deliberately plain keyword matching on free text. It is a
starting point a fellow can override, not a classifier.
"""


class Group:
    BREAST = "BREAST"
    COLON = "COLON"
    RECTUM = "RECTUM"
    THYROID = "THYROID"
    GASTRIC = "GASTRIC"
    ESOPHAGEAL = "ESOPHAGEAL"
    PANCREAS = "PANCREAS"
    BILIARY = "BILIARY"
    LIVER = "LIVER"
    SARCOMA = "SARCOMA"
    OTHER = "OTHER"


LABELS = {
    Group.BREAST: "Breast",
    Group.COLON: "Colon",
    Group.RECTUM: "Rectum",
    Group.THYROID: "Thyroid",
    Group.GASTRIC: "Gastric",
    Group.ESOPHAGEAL: "Oesophageal",
    Group.PANCREAS: "Pancreas",
    Group.BILIARY: "Biliary",
    Group.LIVER: "Liver",
    Group.SARCOMA: "Sarcoma",
    Group.OTHER: "Other",
}

# Order matters: the first match wins, so the more specific phrases come first.
# "Rectosigmoid" must reach RECTUM before "sigmoid" sends it to COLON.
KEYWORDS = [
    # Sarcoma first, because histology beats site here. A GIST of the stomach is
    # a sarcoma, not a gastric adenocarcinoma, and matching on "stomach" first
    # would send it to the wrong guideline entirely. Same for a
    # leiomyosarcoma of the rectum.
    (("sarcoma", "gist", "gastrointestinal stromal", "liposarc", "leiomyosarc",
      "rhabdomyosarc", "angiosarc", "fibrosarc", "synovial sarc",
      "desmoid", "mpnst"), Group.SARCOMA),
    (("rectosigmoid", "rectal", "rectum", "anal verge", "low rectal", "mid rectal"), Group.RECTUM),
    (("colon", "colonic", "sigmoid", "caecal", "cecal", "caecum", "appendiceal",
      "ascending", "descending", "transverse", "hepatic flexure", "splenic flexure"), Group.COLON),
    (("oesophag", "esophag", "gastro-oesophageal", "gastroesophageal", "goj", "gej"), Group.ESOPHAGEAL),
    (("gastric", "stomach"), Group.GASTRIC),
    (("pancrea", "ampullary", "periampullary"), Group.PANCREAS),
    (("cholangio", "biliary", "gallbladder", "bile duct", "klatskin"), Group.BILIARY),
    (("hepatocellular", "hcc", "liver", "hepatic tumour", "hepatic tumor"), Group.LIVER),
    (("thyroid", "papillary", "follicular carcinoma", "medullary"), Group.THYROID),
    (("breast",), Group.BREAST),
]

# Used only when the diagnosis text says nothing recognisable.
SPECIALTY_FALLBACK = {
    "BREAST": Group.BREAST,
    "THYROID": Group.THYROID,
    "COLORECTAL": Group.COLON,
    "UPPER_GI": Group.GASTRIC,
    "HPB": Group.PANCREAS,
    "SARCOMA": Group.SARCOMA,
    "GENERAL": Group.OTHER,
}

# The guideline topic each group needs answered, for the coverage check.
GROUP_TOPICS = {
    Group.BREAST: ["breast"],
    Group.COLON: ["colon"],
    Group.RECTUM: ["rectal"],
    Group.THYROID: ["thyroid"],
    Group.GASTRIC: ["gastric"],
    Group.ESOPHAGEAL: ["esophageal"],
    Group.PANCREAS: ["pancreatic"],
    Group.BILIARY: ["biliary"],
    Group.LIVER: ["liver"],
    Group.SARCOMA: ["sarcoma"],
    Group.OTHER: [],
}


def group_for(patient):
    """Which disease group this patient belongs to."""
    text = (patient.diagnosis or "").lower()
    for needles, group in KEYWORDS:
        if any(needle in text for needle in needles):
            return group
    return SPECIALTY_FALLBACK.get(patient.specialty, Group.OTHER)


def label_for(patient):
    return LABELS[group_for(patient)]


def topics_for(patient):
    """Guideline topics this patient's disease needs. Used by the coverage check."""
    return GROUP_TOPICS.get(group_for(patient), [])
