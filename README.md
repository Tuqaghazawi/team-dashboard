# Surgical Oncology Patient Flow Dashboard

A dashboard that automates the new-patient journey in the surgical oncology department —
from first registration at the preparatory clinic, through MDC discussion, to surgery and
post-operative follow-up.

> **Status:** Planning phase. Building the PRD (product requirements document) first.
> See [`docs/PRD.md`](docs/PRD.md).

## What this project is

The manual process today relies on WhatsApp messages, phone calls, and memory. This app
turns that process into a single shared dashboard where every role — prep-clinic
coordinator, team coordinators, fellows, consultants, MDC coordinators, and the chairman —
sees the right patients and gets notified automatically at each step.

## How we are building it

- **Phased**: one working slice at a time, tested with the team before the next is added.
- **English** interface (Arabic can be added later).
- **Synthetic (fake) patient data first** — a safe prototype, no real patient records yet.
- **AI "NCCN guidelines brain" comes in a later phase**, after the core dashboard works.

## Folder map (what each folder is for)

```
team dashboard/
├── README.md          <- this file: the project's front door
├── docs/              <- all written planning documents (PRD, examples, decisions)
│   └── PRD.md         <- the product requirements document (what we are building & why)
└── (app code folders will be added when we start building — explained at that step)
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
