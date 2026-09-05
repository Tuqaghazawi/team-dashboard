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
python manage.py build_ehr      # synthetic EHR: results + medication orders
python manage.py sync_ehr       # pull those into the dashboard
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

### The scheduled jobs

Two jobs run on a schedule (Task Scheduler or cron). Neither needs a click.

```bash
python manage.py sync_ehr
```

Reads the EHR and fills in any investigation whose report has been finalised
since the last pass — baseline or restaging. Completing a patient's workup emails
the team that they are ready to present; completing their restaging emails the
team to review before the next clinic. Both go through the same code path a
manually typed result uses, and each is announced once, not once per pass.

```bash
python manage.py send_due_alerts
```

Emails teams whose NACT/TNT patients have reached their last cycle (so restaging
gets ordered), and reminds them about post-operative patients not re-listed for
MDC.

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
3. The fellow starts the workup. Each **diagnosis** has its own checklist —
   colon and rectum, gastric and oesophageal, pancreas/biliary/liver are
   separate — visible to the whole team and filling in as reports come back.
   Some items are conditional on the patient: early breast cancer gets abdomen
   ultrasound and a chest X-ray where a locally advanced one gets a CAP CT,
   genetic testing is offered under 65 or with a family history, fertility
   counselling to women under 40. Each conditional item records why it was
   added, and a fellow can change any of it.
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
treatment the guideline supports, with citations. Coverage is worked out from
the patient's **diagnosis**, not their specialty — "Upper GI" covers gastric and
oesophageal cancer, and a guideline for one does not answer the other — and it
is read from the index itself, so adding a guideline widens it with no code
change:

```bash
python manage.py add_guideline --pdf data/guidelines/nccn_esophageal.pdf     --label "Esophageal (NCCN)"
```

Keep licensed PDFs (NCCN) in `data/guidelines/`, which is git-ignored, and never
commit them. Only the extracted chunks enter the index, and that is git-ignored too. It reuses the Session 6 RAG
index over the KHCC guidelines. Suggestions are rendered distinctly from recorded
clinical fact, never change the patient record, and their evidence is written
into the slide's *notes* field so it supports the discussion instead of
pre-empting it.

**Structured extraction** — a report on the workup checklist can be run through
the Capstone 1 extractor. The result is a *pending* extraction, shown as a review
table: fields whose loss changes management (grade, margins, nodes, LVI,
receptors, stage) are marked critical and sorted first, the extractor's own
`needs_human_review` flag is shown, and the clinician's corrections are stored
separately from what the model returned. Nothing reaches the record unconfirmed.

**The EHR integration** — `ehr/source.py` is the whole surface the app uses to
read the hospital: results and medication orders for one MRN. Behind it today is
a synthetic SQLite database keyed by the patients' own MRNs; replacing it with a
real connector (HL7/FHIR, a linked-server view) is the entire migration.

Two rules shape the sync. A result is only taken for an investigation the team
actually asked for — a report the EHR holds that nobody requested is reported
back, never silently added. And only finalised reports are taken, so "all results
are back" never becomes true on the strength of a preliminary one.

**Peri-operative medication check** — a patient booked for surgery is checked
against the KHCC GDLPT-25 rules, using the medications synced onto that patient.
Three distinctions the page keeps separate, because collapsing any of them is
unsafe:

- *never read from the EHR* vs *read, and this patient is on nothing to hold*;
- a drug **named** in the guideline vs one matched only by its **class**. The
  rule table matches on drug name alone, so naproxen — an NSAID it never names —
  was invisible to it. Class matching catches those, flagged as needing
  confirmation rather than presented as a firm rule;
- a drug the guideline covers vs one it says nothing about. The latter is listed
  under "not covered", never under "continue".

**The multi-agent MDC workflow** — the Session 5 LangGraph workflow runs a
guideline agent and a peri-op medication agent over a case, drafts a
recommendation, and stops at `interrupt()` for physician sign-off. Approve
records who signed it off; reject sends feedback back into the graph, which
revises and pauses again. It is compiled with `SqliteSaver`, so a case waiting
for a physician survives a server restart. **Approving a draft does not write an
MDC decision** — the clinician still enters that themselves.

## Not built yet

- **The two agent tools inside `ai/agents/mdc_workflow.py` are still the Session 5
  stubs.** The workflow is wired into the dashboard and its human gate is real,
  but `guideline_lookup` and `drug_interaction_check` return placeholder text
  rather than calling `ai/rag` and `ai/pharmacy`. The dashboard reaches those two
  modules directly instead (the guideline brain and the peri-op page).
- **A confirmed extraction is stored but not yet copied into the patient's
  structured fields** — a clinician still types the clinical detail.
- **The MDC decision suggestion is requested one patient at a time**, not in bulk
  for a whole meeting.
- Post-MDC decisions do not open a treatment course automatically; a fellow
  opens it.
- **Nothing here is validated for clinical use.** It runs on synthetic data.

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

Three thin wrappers connect these to the app, because the originals print
their results instead of returning them: `ai/guidelines/suggest.py` over
`ai/rag`, `ai/pharmacy/periop_api.py` over `periop_flag`, and
`ai/agents/dashboard_workflow.py` over `mdc_workflow` (adding durable pauses).
`ai/extraction/review.py` flattens an extraction into a reviewable table.

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
├── ehr/               <- reading the hospital EHR: results and medication orders
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
