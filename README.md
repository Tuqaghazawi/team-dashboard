# Surgical Oncology Patient Flow Dashboard

A dashboard that follows a patient through the surgical oncology pathway — from
registration at the preparatory clinic, through workup and MDC discussion, to
surgery and post-operative re-discussion — and tells the right people when
something needs attention.

> **Status:** the pathway is built and working end to end on synthetic data.
> See [What works today](#what-works-today) for the honest list, and
> [Not built yet](#not-built-yet) for what is still open.

## What this project is

The manual process today relies on WhatsApp messages, phone calls, and memory.
This app turns that process into a single shared dashboard where every role —
prep-clinic coordinator, team coordinators, fellows, consultants, MDC
coordinators, and the chairman — sees the right patients and is notified
automatically at each step.

**Synthetic data only.** No real patient record goes near this repository, which
is public.

## Running it

```bash
python -m venv .venv
.venv/Scripts/activate          # Windows;  source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
cp .env.example .env            # then fill in OPENAI_API_KEY if you want the guideline brain
python manage.py migrate
python manage.py seed_demo      # synthetic teams, users and patients at every stage
python manage.py runserver
```

Then open http://127.0.0.1:8000 and sign in. Demo logins (password `demo1234`):

| Login | Role | Sees |
|---|---|---|
| `prep1` | Prep-clinic coordinator | every patient; registers new ones; reports |
| `chair1` | Chairman | every patient; reports |
| `coord2` | Team nurse coordinator | Dr. Amro Mureb's team; MDC and surgery lists; rotations |
| `cons2` | Consultant | Dr. Amro Mureb's team |
| `fellow1` | Fellow | whichever team they are rotating through |
| `mdc1` | MDC coordinator | patients listed on the Breast MDC |

These demo logins exist for the synthetic prototype only and must never be
created in a real deployment.

### Tests

```bash
python manage.py test
```

### The daily alert job

Two alerts are time-based rather than triggered by a click. Run this once a day
from Task Scheduler or cron:

```bash
python manage.py send_due_alerts
```

It emails teams whose NACT/TNT patients have reached their last cycle (so
restaging gets ordered), and reminds them about post-operative patients that have
not been re-listed for MDC.

### Email

With `EMAIL_HOST` unset, notification emails print to the console — useful for a
demo. Set `EMAIL_HOST` and the rest in `.env` to send real mail; nothing else
changes.

## What works today

**The pathway**

1. The prep-clinic nurse registers a patient (name, MRN, date of birth,
   diagnosis, specialty, consultant's team). The team coordinator, consultant and
   the fellows currently rotating through that team are emailed.
2. The coordinator lists the patient on an MDC for the following week.
3. The fellow starts the workup. Each specialty has a standard checklist, visible
   to the whole team, that fills in as reports come back.
4. When the last required result lands, the team is emailed that the patient is
   ready to present. Until then the MDC board shows them as not ready.
5. The MDC decision is recorded as a category, which moves the patient:
   surgery → the surgery schedule; NACT or TNT → the follow-up page; referral →
   medical oncology, still tracked by the team.
6. On a NACT/TNT course, one email goes out at the penultimate cycle to order
   restaging, and a second once every restaging report is back.
7. Recording an operation flags the patient for post-operative MDC
   re-discussion, and the flag clears only when a post-op listing exists.

**Views by role** — every page is scoped to what the user may see. A fellow
reaches a team through a three-month rotation, so access ends when the rotation
does.

**Documents**

- MDC and planning-round slide decks (`.pptx`), laid out like the decks the teams
  already present: name, MRN and genetic testing at the top, then the history
  line, the case line, each investigation with its report, treatment given, and
  the decision at the bottom.
- Weekly and monthly prep-clinic reports (`.xlsx`) broken down by specialty,
  consultant, age band and diagnosis.

**The guideline brain** — suggests the workup a presentation needs, and the
treatment the guideline supports, with citations. It reuses the Session 6 RAG
index over the KHCC guidelines. Suggestions are rendered distinctly from recorded
clinical fact, never change the patient record, and their evidence is written
into the slide's *notes* field so it supports the discussion instead of
pre-empting it.

## Not built yet

- **The `ai/agents` LangGraph MDC workflow is not wired into the MDC screen.**
  Decisions are recorded by a person; the guideline brain informs them. The
  `interrupt()` / approve / reject-with-feedback loop is still standalone.
- **`ai/extraction` is not wired in.** Investigation reports are typed or pasted;
  they are not yet run through the extractor for structured fields.
- **`ai/pharmacy` peri-op medication checks** are not surfaced on surgical
  patients.
- **The MDC decision suggestion is not offered per-patient in bulk** — it is
  requested one patient at a time.
- Post-MDC decisions do not yet open a treatment course automatically; a fellow
  opens it.

## The AI layer

Four modules, each built and evaluated as its own course assignment, live under
`ai/`:

| Module | What it does |
|---|---|
| `ai/extraction/` | free-text pathology report → structured fields, with a `needs_human_review` flag |
| `ai/pharmacy/` | peri-operative medication checks against the KHCC guideline |
| `ai/rag/` | RAG over six KHCC oncology guidelines; grounded, cited answers |
| `ai/agents/` | LangGraph MDC workflow with a physician approval gate |
| `ai/eval/` | functional and LLM-judge evaluation, judge validation, safety metrics |

`ai/guidelines/` is the dashboard's wrapper over `ai/rag`: it returns the answer
and its citations instead of printing them, and degrades to "unavailable" rather
than breaking a clinical page when the API key or index is missing.

Evaluation on 39 synthetic cases found contradiction recall of 62% — the
extractor can silently drop critical findings. That is why every extracted or
suggested value in this app is shown for a clinician to confirm, and why nothing
AI-generated is saved to a patient record on its own.

## Folder map

```
team dashboard/
├── config/            <- Django settings and root URLs
├── accounts/          <- the User model and its roles
├── teams/             <- teams, MDCs, and fellow rotations
├── patients/          <- Patient, Investigation, TreatmentCourse, SurgeryBooking
│   ├── flow.py        <- what happens next at each step of the pathway
│   ├── categories.py  <- the buckets the dashboard counts
│   └── workup.py      <- the standard checklist per specialty
├── mdc/               <- MDC listings, decisions, and slide generation
├── notifications/     <- one row per alert per person, plus the email that goes with it
├── reports/           <- the prep-clinic Excel reports
├── templates/         <- the shared base template
├── ai/                <- the five AI modules (see above)
└── docs/              <- PRD, architecture, per-session write-ups
```

## Glossary

- **MDC** — Multidisciplinary Conference / tumour board.
- **Workup** — the investigations a patient needs before MDC discussion.
- **NACT** — neoadjuvant chemotherapy, given before surgery.
- **TNT** — total neoadjuvant therapy, used in rectal cancer.
- **Restaging** — repeating imaging after neoadjuvant treatment to decide what to
  do next.
- **Rotation** — a three-month block during which a fellow is attached to a team.
- **Role** — what a user is allowed to see and do.
- **Synthetic data** — invented patients used to test the app safely.
