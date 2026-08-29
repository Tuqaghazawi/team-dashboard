# Surgical Oncology Patient Flow Dashboard

A dashboard that automates the new-patient journey in the surgical oncology department —
from first registration at the preparatory clinic, through MDC discussion, to surgery and
post-operative follow-up.

> **Status:** Dashboard in planning (building the PRD first — see [`docs/PRD.md`](docs/PRD.md)).
> The first AI module, a clinical extraction system, is built and evaluated — see below.

## What this project is

The manual process today relies on WhatsApp messages, phone calls, and memory. This app
turns that process into a single shared dashboard where every role — prep-clinic
coordinator, team coordinators, fellows, consultants, MDC coordinators, and the chairman —
sees the right patients and gets notified automatically at each step.

## How we are building it

- **Phased**: one working slice at a time, tested with the team before the next is added.
- **English** interface (Arabic can be added later).
- **Synthetic (fake) patient data first** — a safe prototype, no real patient records yet.
- **AI arrives in two parts** — a clinical extraction layer (working now, see below) and an
  NCCN-guidelines brain in a later phase, after the core dashboard works.

## The AI layer — Clinical Extraction System

The dashboard needs patient data as **structured fields**, not free-text reports. The
Clinical Extraction System is the first AI component that provides them: it reads a
free-text breast pathology report and returns a structured, checked record — histology,
grade, size, ER/PR/HER2, node counts, stage — ready to fill in a patient's dashboard entry.

It is built as a **self-contained module** (CCI Capstone 1) so it can be tested on its own
before it plugs into the dashboard, through a non-identifying patient reference. The same
schema that checks the extraction is the shape the dashboard consumes — one contract, both
ends.

**Result on the 20-note labeled breast set:** 313/313 fields correct (100%), 0 misses, 0
made-up values, and all 4 cases that needed a human were flagged. Ambiguous or
safety-relevant cases (equivocal HER2 pending reflex ISH, macroscopic/microscopic
disagreement, involved margins) are routed to a person rather than treated as final.

Full build story and error analysis: [`docs/capstone1_writeup.md`](docs/capstone1_writeup.md).

## Folder map (what each folder is for)

```
team dashboard/
├── README.md                   <- this file: the project's front door
├── docs/                       <- all written planning documents
│   ├── PRD.md                  <- the product requirements document (what we build & why)
│   └── capstone1_writeup.md    <- clinical extraction system: build + evaluation
├── ai/
│   ├── extraction/             <- the schema (the contract) + the LLM extraction engine
│   └── eval/                   <- accuracy scoring + single-note inspection
├── scripts/                    <- synthetic (fake) data generator
└── (dashboard app folders will be added as each slice is built)
```

## Project glossary (plain-language terms)

- **PRD** — Product Requirements Document. A written plan describing *what* the app does
  and *why*, before any code. Like an operative plan before surgery.
- **Dashboard** — the web page each user logs into to see their patients and tasks.
- **Role** — what a user is allowed to see and do (e.g. fellow vs. chairman).
- **Notification** — an automatic alert (in-app and email) when something needs attention.
- **MDC** — Multidisciplinary Conference / tumor board.
- **Workup** — the set of investigations a patient needs before MDC discussion.
- **Synthetic data** — invented patients used to test the app safely.
- **Clinical extraction** — reading a free-text report and pulling out the specific fields
  (grade, size, receptors, nodes) as structured data the app can use.
- **Schema** — the fixed list of fields and their allowed shapes. Like a structured
  reporting proforma: it defines exactly what a valid record looks like.