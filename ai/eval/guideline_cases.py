"""Realistic cases for evaluating the guideline brain.

These are not sampled at random. Each one probes a failure this system has
actually shown, or a failure the design predicts:

* **History blindness.** The brain was told only the diagnosis, so it offered
  TME to a patient five of six cycles into TNT, and an oesophagectomy to a
  patient whose stomach had already been removed. Cases 3-6 re-run exactly that
  shape.
* **Wrong-guideline answers.** A vector search always returns its nearest
  neighbours, so a disease with no indexed guideline still retrieves passages —
  from a different cancer. Every specialty is now covered, so this is tested by
  checking the answer comes from the *right* guideline rather than by expecting
  a refusal.
* **Answering from the right neighbour.** Liver, biliary and oesophageal became
  covered when the NCCN guidelines were indexed. They stay in the set because
  each has a plausible wrong neighbour already indexed — pancreatic for biliary,
  gastric for oesophageal — so the check is now that the answer comes from the
  right one, not that it is refused.
* **Near-miss retrieval.** Oesophageal cancer sits next to gastric in embedding
  space and shares a specialty, so `oesophageal-near-miss` checks the answer
  comes from the oesophageal guideline and not the gastric one.

Synthetic throughout. `forbidden` lists what the answer must not propose — the
operation already performed, or the treatment already completed.
"""

# Pathway stages, matching patients.models.Patient.Stage
MDC = "MDC"
TNT = "TNT"
NACT = "NACT"
POSTOP = "POSTOP"

CASES = [
    # --- 1-2: treatment-naive, covered. The straightforward path. ---
    {
        "id": "rectal-naive",
        "diagnosis": "Mid rectal cancer",
        "specialty": "COLORECTAL",
        "stage": MDC,
        "clinical_stage": "T3N2",
        "sex": "M", "age": 64,
        "results": {
            "PELVIC_MRI": "T3N2 rectal cancer 8 cm from the anal verge. Mesorectal fascia intact.",
            "CAP_CT": "No distant metastasis.",
            "PATHOLOGY": "Moderately differentiated adenocarcinoma.",
        },
        "should_refuse": False,
        "expect_sources": ["Rectal"],
        "forbidden": [],
        "asks_about": "primary treatment for a treatment-naive T3N2 rectal cancer",
    },
    {
        "id": "breast-naive",
        "diagnosis": "Right breast cancer",
        "specialty": "BREAST",
        "stage": MDC,
        "clinical_stage": "cT2N0",
        "sex": "F", "age": 52,
        "results": {
            "MAMMOGRAM": "Spiculated mass 2.4 cm, upper outer quadrant.",
            "BIOMARKERS": "ER 95%, PR 80%, HER2 negative, Ki-67 18%.",
        },
        "should_refuse": False,
        "expect_sources": ["Breast"],
        "forbidden": [],
        "asks_about": "primary treatment for an early, hormone-positive breast cancer",
    },

    # --- 3-6: the history cases. These are the ones that were wrong. ---
    {
        "id": "rectal-mid-tnt",
        "diagnosis": "Mid rectal cancer",
        "specialty": "COLORECTAL",
        "stage": TNT,
        "clinical_stage": "T3N2",
        "sex": "M", "age": 78,
        "courses": [{"kind": "TNT", "regimen": "XELOX x 6", "total": 6, "done": 5}],
        "results": {
            "PELVIC_MRI": "T3N2 rectal cancer 8.6 cm from the anal verge.",
            "CAP_CT": "No distant metastasis.",
        },
        "should_refuse": False,
        "expect_sources": ["Rectal"],
        # It must not propose starting the treatment he is already most of the way through.
        "forbidden": ["start neoadjuvant", "commence tnt", "begin total neoadjuvant"],
        "asks_about": "the next step for a patient already 5 of 6 cycles into TNT",
    },
    {
        "id": "gastric-post-gastrectomy",
        "diagnosis": "Gastric cancer",
        "specialty": "UPPER_GI",
        "stage": POSTOP,
        "clinical_stage": "cT3N1",
        "sex": "M", "age": 71,
        "surgeries": [{
            "procedure": "Total gastrectomy",
            "pathology": "ypT2N1a, negative margins, 2 of 14 nodes positive, +LVI.",
        }],
        "results": {"CAP_CT": "No distant metastasis."},
        "should_refuse": False,
        "expect_sources": ["Gastric"],
        # The organ is gone. Proposing to remove it, or the oesophagus, is the
        # exact error this system made.
        "forbidden": ["oesophagectomy", "esophagectomy", "gastrectomy"],
        "asks_about": "the adjuvant plan after a completed total gastrectomy",
    },
    {
        "id": "breast-post-mastectomy",
        "diagnosis": "Left breast cancer",
        "specialty": "BREAST",
        "stage": POSTOP,
        "clinical_stage": "cT2N1",
        "sex": "F", "age": 58,
        "surgeries": [{
            "procedure": "Modified radical mastectomy",
            "pathology": "ypT2N1a, 3 of 15 nodes positive, ER 95%, HER2 negative.",
        }],
        "results": {},
        "should_refuse": False,
        "expect_sources": ["Breast"],
        "forbidden": ["mastectomy", "wide local excision", "lumpectomy"],
        "asks_about": "the adjuvant plan after a completed mastectomy",
    },
    {
        "id": "breast-mid-nact",
        "diagnosis": "Left breast cancer",
        "specialty": "BREAST",
        "stage": NACT,
        "clinical_stage": "cT3N+",
        "sex": "F", "age": 47,
        "courses": [{"kind": "NACT", "regimen": "AC-T", "total": 8, "done": 7}],
        "results": {"BIOMARKERS": "ER 5%, PR negative, HER2 negative. Triple negative."},
        "should_refuse": False,
        "expect_sources": ["Breast"],
        "forbidden": ["start neoadjuvant", "commence neoadjuvant"],
        "asks_about": "the next step for a patient nearly through neoadjuvant chemotherapy",
    },

    # --- 7-8: covered diseases, less common shapes. ---
    {
        "id": "colon-metastatic",
        "diagnosis": "Ascending colon cancer",
        "specialty": "COLORECTAL",
        "stage": MDC,
        "clinical_stage": "T3N1M1",
        "sex": "F", "age": 66,
        "results": {
            "CAP_CT": "Three hepatic metastases, largest 2.1 cm, segments 4 and 6.",
            "RAS_BRAF": "KRAS wild type.",
        },
        "should_refuse": False,
        "expect_sources": ["Colon"],
        "forbidden": [],
        "asks_about": "treatment for metastatic colon cancer with liver metastases",
    },
    {
        "id": "thyroid-naive",
        "diagnosis": "Papillary thyroid carcinoma",
        "specialty": "THYROID",
        "stage": MDC,
        "clinical_stage": "cT2N1a",
        "sex": "M", "age": 44,
        "results": {"FNA": "Papillary thyroid carcinoma (Bethesda VI)."},
        "should_refuse": False,
        "expect_sources": ["Thyroid"],
        "forbidden": [],
        "asks_about": "primary treatment for node-positive papillary thyroid carcinoma",
    },

    # --- 9: sarcoma, covered by NCCN since its guideline was indexed. ---
    {
        "id": "sarcoma-nccn",
        "diagnosis": "Soft tissue sarcoma, thigh",
        "specialty": "SARCOMA",
        "stage": MDC,
        "clinical_stage": "T2bN0",
        "sex": "F", "age": 46,
        "results": {"LOCAL_MRI": "Deep soft-tissue mass 9 cm, posterior thigh."},
        "should_refuse": False,
        "expect_sources": ["Sarcoma"],
        "forbidden": [],
        "asks_about": "primary treatment for a deep soft-tissue sarcoma of the thigh",
    },
    {
        # Histology beats site. A GIST of the stomach must reach the sarcoma
        # guideline, not the gastric one — matching on "stomach" first sent it
        # to gastric adenocarcinoma guidance, which is a different disease.
        "id": "gist-not-gastric",
        "diagnosis": "GIST of stomach",
        "specialty": "GENERAL",
        "stage": MDC,
        "clinical_stage": "T2N0",
        "sex": "M", "age": 58,
        "results": {"GASTROSCOPY": "Submucosal mass 4 cm at the gastric body."},
        "should_refuse": False,
        "expect_sources": ["Sarcoma"],
        "forbidden": [],
        "asks_about": "a gastric GIST, where the gastric adenocarcinoma guideline is the wrong neighbour",
    },
    # --- Diseases with no indexed guideline. These keep the refusal path under
    # test: once every case in the set is answerable, refusal calibration passes
    # trivially and stops meaning anything. A surgical oncology service sees all
    # of these, and none is in the index.
    {
        "id": "melanoma-uncovered",
        "diagnosis": "Cutaneous melanoma, back",
        "specialty": "GENERAL",
        "stage": MDC,
        "clinical_stage": "T3bN0",
        "sex": "M", "age": 54,
        "results": {"PATHOLOGY": "Melanoma, Breslow 3.2 mm, ulcerated."},
        "should_refuse": True,
        "expect_sources": [],
        "forbidden": [],
        "asks_about": "a melanoma, for which no guideline is indexed",
    },
    {
        "id": "neuroendocrine-uncovered",
        "diagnosis": "Small bowel neuroendocrine tumour",
        "specialty": "GENERAL",
        "stage": MDC,
        "clinical_stage": "T3N1",
        "sex": "F", "age": 61,
        "results": {"CAP_CT": "Mesenteric mass with desmoplastic reaction."},
        "should_refuse": True,
        "expect_sources": [],
        "forbidden": [],
        # Colon and pancreatic are both indexed and both plausible neighbours.
        "asks_about": "a small bowel NET, with colon and pancreatic guidelines nearby",
    },

    # --- 10-12: covered by NCCN, each with a plausible wrong neighbour indexed. ---
    {
        "id": "biliary-nccn",
        "diagnosis": "Hilar cholangiocarcinoma",
        "specialty": "HPB",
        "stage": MDC,
        "clinical_stage": "T2N0",
        "sex": "M", "age": 69,
        "results": {"MRCP": "Bismuth type IIIa hilar stricture."},
        "should_refuse": False,
        # Pancreatic is indexed and sits close by, so the answer must come from
        # the biliary guideline rather than that one.
        "expect_sources": ["Biliary"],
        "forbidden": [],
        "asks_about": "a biliary cancer, with the pancreatic guideline nearby",
    },
    {
        "id": "oesophageal-near-miss",
        "diagnosis": "Distal oesophageal cancer",
        "specialty": "UPPER_GI",
        "stage": MDC,
        "clinical_stage": "cT3N1",
        "sex": "M", "age": 61,
        "results": {"GASTROSCOPY": "Ulcerated mass at 34 cm, crossing the GOJ."},
        "should_refuse": False,
        # Covered by NCCN since the guideline was indexed. The case stays because
        # it is still the hardest one: same specialty as gastric and adjacent in
        # embedding space, so the answer must come from the oesophageal guideline
        # and not the gastric one.
        "expect_sources": ["Esophageal"],
        "forbidden": [],
        "asks_about": "an oesophageal cancer, where the gastric guideline is a plausible-looking wrong answer",
    },
    {
        "id": "liver-nccn",
        "diagnosis": "Hepatocellular carcinoma",
        "specialty": "HPB",
        "stage": MDC,
        "clinical_stage": "T2N0",
        "sex": "M", "age": 63,
        "results": {"TRIPHASIC": "3.1 cm arterially enhancing lesion, segment VII, LI-RADS 5."},
        "should_refuse": False,
        "expect_sources": ["Hepatocellular"],
        "forbidden": [],
        "asks_about": "hepatocellular carcinoma, answered from the NCCN guideline",
    },
]
