"""Turning a ClinicalExtraction into something a clinician can check line by line.

The evaluation in ``ai/eval`` found contradiction recall of 62% on 39 synthetic
cases: the extractor can silently drop a critical finding — grade, positive
nodes, LVI. So the dashboard never stores an extraction as fact. It shows every
field next to the snippet it came from, marks the fields whose loss would change
management, and asks a person to confirm.

This module does the flattening and the marking. It does not save anything.
"""

# Fields whose absence or error changes management. These are surfaced first and
# called out even when the extractor returned nothing for them.
CRITICAL = {
    "grade",
    "margins",
    "margin_status",
    "nodes_positive",
    "nodes_examined",
    "lvi",
    "lymphovascular_invasion",
    "pni",
    "perineural_invasion",
    "stage",
    "pt",
    "pn",
    "tnm",
    "er",
    "pr",
    "her2",
}


class ExtractionUnavailable(RuntimeError):
    """The extractor could not be reached or the model rejected the note."""


def extract(note_text):
    """Run the Capstone 1 extractor on one report."""
    try:
        from ai.extraction.extract import extract_note
    except Exception as exc:
        raise ExtractionUnavailable(str(exc)) from exc
    try:
        return extract_note(note_text)
    except Exception as exc:
        raise ExtractionUnavailable(str(exc)) from exc


def flatten(extraction):
    """A ClinicalExtraction as an ordered list of rows for the review table.

    Each row is {path, label, value, critical}. Empty values are kept, because
    "the extractor found nothing here" is exactly what a clinician needs to see.
    """
    data = extraction.model_dump() if hasattr(extraction, "model_dump") else dict(extraction)
    meta = data.pop("meta", None) or {}

    rows = []
    _walk(data, "", rows)
    rows.sort(key=lambda r: (not r["critical"], r["path"]))
    return rows, _meta_summary(meta)


def _walk(value, prefix, rows):
    for key, item in value.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(item, dict):
            _walk(item, path, rows)
            continue
        if isinstance(item, list):
            item = ", ".join(str(x) for x in item)
        rows.append(
            {
                "path": path,
                "label": key.replace("_", " ").capitalize(),
                "value": "" if item is None else str(item),
                "critical": key.lower() in CRITICAL,
            }
        )


def _meta_summary(meta):
    """The parts of meta the reviewer must see."""
    return {
        "needs_human_review": bool(meta.get("needs_human_review")),
        "confidence": meta.get("confidence"),
        "missing_fields": meta.get("missing_fields") or [],
        "evidence_spans": meta.get("evidence_spans") or [],
    }
