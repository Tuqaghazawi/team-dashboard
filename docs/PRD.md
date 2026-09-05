# Surgical Oncology Patient Flow Dashboard — PRD

**Author:** Tuqa Al-Ghazawi
**Course:** CCI — Clinical AI / Prompt Engineering (Capstone 2)
**Status:** v1 built and working on synthetic data
**Version:** 1.1
**Last updated:** 5 September 2026
**Repository:** https://github.com/Tuqaghazawi/team-dashboard

> **What changed in 1.1.** Adds the safety, ethics and operations sections a
> clinical-facing tool needs: scope limits, human oversight, the override
> path, PHI handling, named owners and an incident path (§14); the ethics
> pillars and where they were load-bearing (§15); and hosting, secrets,
> versioning, rollback triggers and drift monitoring (§16). The tool is now
> labelled *not for clinical use* on every page and on every document it
> generates.
>
> **What changed in 1.0.** The previous version described a system to be built.
> This version describes the one that exists. Every requirement below is marked
> **Built**, **Partial** or **Not built**, and the "Done means" section reports
> what actually passes. Requirements that were planned and then deliberately
> dropped are recorded in §4 rather than deleted, so the reasoning survives.

---

## 1. Summary

A Django web application that follows a cancer patient through the surgical
oncology pathway at KHCC — registration at the preparatory clinic, workup, MDC
discussion, treatment, surgery, and post-operative re-discussion — and tells the
right people when something needs attention.

Today that coordination happens over WhatsApp, phone calls and memory. Patients
fall through the gaps: a workup finishes and nobody lists the patient for MDC; a
decision is made for surgery and nobody books theatre; a patient finishes
neoadjuvant chemotherapy and nobody orders restaging in time for the clinic.

The app makes each of those gaps visible and emails the team automatically. Five
AI modules assist at specific points — extracting structured fields from
pathology reports, answering guideline questions with citations, checking
peri-operative medications, and drafting an MDC recommendation for a physician to
approve or reject. **The governing rule is human-in-the-loop: AI drafts and
flags, the clinician decides. Nothing is auto-decided or auto-recorded.**

Synthetic data only. No real patient record has been near this repository, which
is public.

---

## 2. Problem

**What hurts today.** Coordination is informal and undocumented. Specifically:

- The prep clinic registers a patient and tells the team by phone or WhatsApp.
  There is no record that the handover happened.
- Nobody can see, in one place, which patients have all their investigations back
  and are therefore ready to present at MDC.
- After an MDC decision, the next step depends on somebody remembering it.
  Patients decided for surgery are not always booked; patients on neoadjuvant
  treatment are not always restaged before their next clinic.
- Post-operative patients must come back to MDC for their adjuvant plan. There is
  no list of who is waiting.
- Fellows rebuild MDC and planning slides by hand every week, retyping
  investigation results that already exist in the EHR.
- The prep-clinic coordinator and the chairman compile activity reports manually.

**Who has this problem.** Six roles across eleven consultant-led teams: the
prep-clinic coordinator, the chairman, each team's nurse coordinator, the fellows
rotating through each team, the consultants, and the four MDC coordinators.

**Why an app.** Most of this is bookkeeping a database does better than a person:
who is on which list, what is outstanding, who to email. That part needs no AI.

**Why an LLM, for the parts that need one.** Three tasks resist plain code:

1. Pathology and radiology reports are free text. Turning "moderately
   differentiated adenocarcinoma, 3 of 14 nodes positive, LVI present" into
   structured fields is a language task.
2. Guideline questions require reading several hundred pages of KHCC guidance and
   answering *for this patient's presentation*, with the passage cited.
3. Drafting an MDC recommendation from a case summary plus guideline findings.

---

## 3. Goals

**Primary goal.** No patient stalls silently. Every point where the pathway can
stop — workup complete but unlisted, decision made but unscheduled, treatment
finishing without restaging ordered, surgery done without an adjuvant plan —
raises a visible flag and an email to the team.

**Secondary goals.**

- Cut slide preparation from manual retyping to one click, using investigation
  results the system already holds.
- Give the prep-clinic coordinator and chairman weekly and monthly activity
  reports without manual counting.
- Make every AI output verifiable by a clinician before it affects anything.

---

## 4. Non-goals

**Out of scope for v1, deliberately:**

| Not doing | Why |
|---|---|
| Real patient data | Needs institutional approval, an in-hospital model, and an information-governance review. Synthetic only. |
| Deployment to a hospital server | Azure App Service + Azure DB for PostgreSQL is the intended target, but v1 runs locally. |
| A real EHR connector | `ehr/source.py` is the seam; behind it is a synthetic database. Swapping in HL7/FHIR is the whole migration. |
| Mobile app | The web pages are responsive enough for a course project. |
| Arabic interface | English only. Arabic can follow. |
| Fine-tuning any model | Prompting plus retrieval is sufficient and far cheaper. |
| WhatsApp notifications | In-app plus email only — decided early, and unchanged. |

**Planned earlier, then dropped from v1 (recorded so the reasoning survives):**

- **Pre-operative consult checklist** (anaesthesia / cardiology / internal
  medicine) gating a "ready for surgery" status. The peri-operative medication
  check covers the highest-risk part of this; the full consult tracker is
  deferred.
- **Statistics, KPI, M&M and Events modules.** These were always Modules 2–5 of
  the wider platform vision (§19). Module 1 had to work first.

---

## 5. Users

| Role | Sees | Can do | Status |
|---|---|---|---|
| **Prep-clinic coordinator** | The **handover queue** — patients the MDC has not yet discussed, grouped by team. Reports cover everyone. | Register a patient and assign them to a team; generate weekly/monthly reports and Excel | Built |
| **Chairman** | All patients, all teams | View everything; view and download all reports | Built |
| **Team nurse coordinator** | Their own team's patients | Assign that rotation's fellows; add patients to the MDC list; list patients for surgery; register a walk-in onto their own team | Built |
| **Fellow** | The team(s) they are **currently rotating through** | Run the workup, record results, pull from the EHR, build MDC and planning slides, record MDC decisions | Built |
| **Consultant** | Their own team's patients | View and follow their team; a dedicated team page | Built |
| **MDC coordinator** | Patients listed on their own MDC | See their MDC's list | Partial — no separate per-MDC Excel export |

**Rotation rule (built).** Fellows rotate in three-month blocks (Jan–Mar, Apr–Jun,
Jul–Sep, Oct–Dec). The nurse coordinator assigns fellows at the start of each
block. An assignment is what grants dashboard access, and **access ends
automatically when the rotation ends** — verified by test.

**Prep-clinic scoping (built).** Her working list holds patients the MDC has not
yet discussed, grouped by the team she assigned them to. Being *listed* is not
enough to drop off — a patient sitting on next week's list is still hers to
chase. Her *reports* deliberately use a wider query, so weekly and monthly
returns still count every patient she registered.

### The teams (all built and seeded)

| Consultant | Specialty |
|---|---|
| Dr. Mahmoud Al-Masri | General surgical oncology |
| Dr. Faiez Daoud | General surgical oncology |
| Dr. Mohd Basem Hamdan | Thyroid and breast |
| Dr. Mohammed Al-Qaisi | Thyroid and breast |
| Dr. Fade Alawneh | Thyroid and breast |
| Dr. Ali Al-Ebous | Thyroid and breast |
| Dr. Ali Dabous | HPB and general surgical oncology |
| Dr. Bilal Baker | HPB and upper GI |
| Dr. Motaz Makhamreh | HPB and upper GI |
| Dr. Basem Jalabneh | Colorectal cancer |
| Dr. Amro Mureb | Colorectal cancer |

> All general surgical oncology teams also handle **sarcoma** cases.

### The MDCs

**Breast** · **GI** (hepatobiliary, pancreatic, colon, rectum, gastric,
oesophageal, small bowel, appendix) · **Sarcoma** · **Thyroid**.

Each MDC has a meeting weekday, so listing a patient pre-fills the next meeting
date. A patient's specialty suggests their MDC; "General surgical oncology" is
deliberately unmapped, because those cases vary and the coordinator chooses.

---

## 6. User stories

- As a **prep-clinic nurse**, when a new patient is booked, I want to record their
  six details and assign a consultant, so the team is told automatically instead
  of by phone.
- As a **team coordinator**, when a patient comes straight to our clinic rather
  than through prep, I want to register them onto my own team myself.
- As a **fellow**, when I open a patient, I want to see exactly which
  investigations are still outstanding, so I know what to chase.
- As a **consultant**, when I open my team page, I want to see the patients who
  are stuck — ready for MDC but unlisted, or decided for surgery but unbooked.
- As a **team**, when a patient reaches the last cycle of neoadjuvant treatment,
  we want an email telling us to order restaging, and another when the reports
  land, so we are ready for the clinic.
- As a **fellow**, when the MDC list is set, I want the slide deck generated from
  the results already in the system, rather than retyping them.

---

## 7. Functional requirements

### 7.1 Registration and handover

| ID | Requirement | Status |
|---|---|---|
| FR-1.1 | Prep coordinator registers a patient with name, MRN, date of birth, diagnosis, specialty and consultant's team. MRN is unique. | Built |
| FR-1.2 | On registration, the team's coordinator, consultant and currently rotating fellows receive an in-app notification and an email. | Built |
| FR-1.3 | A team coordinator may register a patient directly, restricted to their own team. | Built |
| FR-1.4 | A patient leaves the prep coordinator's working list once the MDC has **discussed** them — being listed is not enough, since a patient on next week's list is still hers to chase. | Built |
| FR-1.5 | Her list is grouped **by team**, so she sees how her registrations are distributed rather than one flat list. | Built |

### 7.2 Workup

| ID | Requirement | Status |
|---|---|---|
| FR-2.1 | Starting a workup creates the standard checklist for that **diagnosis** — colon and rectum, gastric and oesophageal, pancreas/biliary/liver are separate. | Built |
| FR-2.6 | Conditional items apply per patient (breast staging by stage, genetics by age or family history, fertility counselling under 40, RAS/BRAF if metastatic), and each records why it was added. | Built |
| FR-2.2 | The checklist is visible to the whole team, showing what is outstanding. | Built |
| FR-2.3 | A patient is "ready for MDC" only when every **required baseline** item has a result. Restaging is tracked separately and does not affect this. | Built |
| FR-2.4 | Completing the last required result emails the team — **once**, not on every later edit or sync pass. | Built |
| FR-2.5 | A fellow can add or remove checklist items by hand. | Built |

### 7.3 EHR integration

| ID | Requirement | Status |
|---|---|---|
| FR-3.1 | Investigation results (baseline and restaging) are read from the EHR by the patient's own MRN. | Built |
| FR-3.2 | Only **finalised** reports are taken, so "all results are back" cannot become true on a preliminary one. | Built |
| FR-3.3 | A result is only taken for an investigation the team **requested**. A report nobody asked for is reported back, never silently added. | Built |
| FR-3.4 | An existing recorded result is never overwritten by the EHR. | Built |
| FR-3.5 | Medication orders are read from the EHR onto the patient. | Built |
| FR-3.6 | Runs on a schedule (`sync_ehr`) and on demand per patient. | Built |
| FR-3.7 | An unreachable EHR degrades to a message; no clinical page breaks. | Built |
| FR-3.8 | Real hospital connector (HL7 / FHIR) behind the same interface. | Not built |

### 7.4 MDC

| ID | Requirement | Status |
|---|---|---|
| FR-4.1 | A coordinator lists a patient for a specific MDC and meeting date, pre-filled from the specialty and that MDC's weekday. | Built |
| FR-4.2 | The MDC board groups listings by week and shows, per patient, whether their workup is complete. | Built |
| FR-4.3 | A decision is recorded as a **category**, which moves the patient: Surgery, NACT, TNT, Refer to medical oncology, Further workup, Surveillance, Watch & wait, Palliative. | Built |
| FR-4.4 | Recording a decision emails the team. | Built |
| FR-4.5 | Post-MDC, NACT and TNT patients remain on the team's list until the definitive decision. | Built |
| FR-4.6 | Per-MDC weekly/monthly Excel export for MDC coordinators. | Not built |

### 7.5 Treatment, surgery and the post-op loop

| ID | Requirement | Status |
|---|---|---|
| FR-5.1 | A NACT/TNT course records regimen, planned cycles and cycles completed. | Built |
| FR-5.2 | At the penultimate cycle, the team is emailed to order restaging, and the restaging checklist is created. Sent once per course. | Built |
| FR-5.3 | When every restaging report is back, the team is emailed to review before the next clinic. | Built |
| FR-5.4 | A coordinator lists a patient for surgery with a date and procedure. | Built |
| FR-5.5 | Recording the operation and its final pathology moves the patient to post-op and **flags them for MDC re-discussion**, which clears only when a post-op listing exists. | Built |
| FR-5.6 | Pre-operative consult checklist (anaesthesia / cardiology / IM) gating "ready for surgery". | Not built — see §4 |

### 7.6 Documents

| ID | Requirement | Status |
|---|---|---|
| FR-6.1 | MDC slide deck (`.pptx`) for one meeting, one slide per patient: name and MRN and genetic testing at the top, history line, `Case of …`, each investigation with its report, treatment given, restaging, and the decision line. | Built |
| FR-6.2 | Planning-round deck for a team's operative patients, ending `For: <procedure>`. | Built |
| FR-6.3 | Guideline evidence goes into the slide's **notes** field, never onto the slide. | Built |
| FR-6.4 | Weekly and monthly prep-clinic reports as `.xlsx`, broken down by specialty, consultant, age band and diagnosis, plus a full patient sheet. | Built |

### 7.7 Visibility

| ID | Requirement | Status |
|---|---|---|
| FR-7.1 | Every page is scoped to what the user may see; opening another team's patient returns 404, another team's page returns 403. | Built |
| FR-7.2 | A patient's progress is shown as a timeline visible to the whole team. | Built |
| FR-7.3 | A team page shows the consultant, coordinator, rotating fellows, and the patients who are stuck. | Built |

---

## 8. The AI layer

Five modules, each built and evaluated as its own course assignment, plus four
thin wrappers that connect them to the app. **The wrappers exist because the
original modules print their results and return `None`** — they were written as
scripts. No module was rewritten.

| Module | What it does | Wired in? |
|---|---|---|
| `ai/extraction/` (Capstone 1) | free-text pathology report → structured Pydantic fields + `needs_human_review` | **Yes** — as a reviewable draft |
| `ai/rag/` (Session 6) | RAG over six KHCC guidelines, 780 chunks in ChromaDB; grounded, cited answers | **Yes** — the guideline brain |
| `ai/pharmacy/` (Session 3) | peri-operative medication rules (KHCC GDLPT-25) | **Yes** — on the patient's own meds |
| `ai/agents/` (Session 5) | LangGraph workflow with an `interrupt()` physician gate | **Yes** — with durable pauses |
| `ai/eval/` (Session 7) | functional + LLM-judge evaluation, judge validation, safety metrics | Offline only, by design |

### 8.1 The guideline brain — `ai/guidelines/suggest.py`

- **Model:** `gpt-4o-mini`, temperature 0, over passages retrieved from ChromaDB.
- **Key:** `OPENAI_API_KEY` from `.env`, read with `python-dotenv`. `.env` is
  git-ignored. Never hardcoded.
- **Input → output:** the patient's case → a workup suggestion or a decision
  suggestion, plus the source labels of the passages used.
- **What the case contains — this is the important part.** It carries the
  diagnosis *and everything already done*: treatment given with cycle counts and
  whether it finished, any operation performed and its final pathology, and
  baseline findings labelled separately from restaging. The question also names
  which decision is being asked — primary plan, next step after neoadjuvant
  treatment, or post-operative adjuvant plan.

  > **Why this matters.** Version 0.9 sent only the diagnosis, so every patient
  > looked newly diagnosed. It offered TME as a primary plan to a patient five of
  > six cycles into TNT, and an oesophagectomy to a patient who had already had a
  > total gastrectomy. Both now answer correctly.

- **Coverage honesty.** A vector search always returns its nearest neighbours, so
  a disease that is not indexed still retrieves passages — from a different
  cancer. Coverage is therefore checked explicitly, and worked out from the
  patient's **diagnosis** rather than their specialty: "Upper GI" spans gastric
  and oesophageal cancer, and the gastric guideline does not answer for the
  oesophagus. The check reads the index itself, so
  `manage.py add_guideline` widens coverage with no code change.

  The KHCC set covers **Breast, Colon, Rectal, Thyroid, Gastric and Pancreatic**.
  **Sarcoma, hepatobiliary other than pancreatic, and oesophageal have no KHCC
  guideline** — NCCN is the agreed source for those, and the PDFs are still to be
  supplied and indexed.
- **On refusal.** When the model replies "Not found in the provided guidelines",
  no citations are shown and no slide note is written — listing the passages a
  search happened to return would make a refusal look researched.
- **On failure.** Missing key or missing index degrades to "unavailable" with a
  message. The clinical page still loads.

### 8.2 Clinical extraction

A report on the workup checklist can be run through the Capstone 1 extractor. The
result is stored as a **pending** extraction and shown as a review table. Fields
whose loss changes management — grade, margins, nodes, LVI, receptors, stage —
are marked **critical** and sorted to the top. The extractor's own
`needs_human_review` flag is shown. The clinician's corrections are stored
separately from what the model returned, so the audit trail survives.

Nothing reaches the patient record unconfirmed.

### 8.3 Peri-operative medication check

Deterministic rules, not a model. Reads the medications synced onto the patient
and applies the KHCC GDLPT-25 table. Three distinctions the page keeps separate,
because collapsing any of them is unsafe:

1. **Never read from the EHR** vs **read, and this patient is on nothing to
   hold.** Both produce an empty alert list; only one is safe.
2. A drug **named** in the guideline vs one matched only by its **class.** The
   rule table matches on drug name alone — naproxen, an NSAID it never names
   against an NSAID rule of DISCONTINUE, produced no alert at all. Class matching
   catches those, flagged as needing confirmation rather than stated as fact.
3. A drug the guideline covers vs one it says **nothing** about. The latter is
   listed under "not covered — not checked", never beside the ones it cleared.

### 8.4 The multi-agent MDC workflow

The Session 5 LangGraph workflow runs a guideline agent and a peri-op agent over
a case built from the patient record, drafts a recommendation, then stops at
`interrupt()` for physician sign-off. **Approve** records who signed it off;
**reject** sends their feedback back into the graph, which revises and pauses
again.

Compiled with `SqliteSaver` rather than `InMemorySaver`, so a case waiting for a
physician survives a server restart — verified by reading the checkpoint back
from a separate process.

**Approving a draft does not write an MDC decision.** The clinician still enters
that. A test asserts the listing's decision fields stay empty through both
approval and rejection.

> **Known limitation.** The two *tools* inside `mdc_workflow.py`
> (`guideline_lookup`, `drug_interaction_check`) are still the Session 5 stubs
> returning placeholder text. The workflow and its human gate are real; the
> dashboard reaches `ai/rag` and `ai/pharmacy` directly instead.

### 8.5 Cost

`gpt-4o-mini` at temperature 0, one call per suggestion, a handful of calls per
patient. Pennies for a course project. Suggestions are cached on the patient so a
page load never re-calls the API.

---

## 9. Data and storage

**Database:** SQLite (`db.sqlite3`) locally. PostgreSQL on Azure is the intended
production target and is not part of v1.

**14 models across six apps:**

| App | Models |
|---|---|
| `accounts` | `User` (custom, with role, team and MDC) |
| `teams` | `Team`, `MDC`, `FellowAssignment` |
| `patients` | `Patient`, `Investigation`, `TreatmentCourse`, `SurgeryBooking`, `Medication`, `ReportExtraction` |
| `mdc` | `MDCListing`, `GuidelineSuggestion`, `MDCAgentReview` |
| `notifications` | `Notification` |

Two further SQLite files are **external systems**, not application data:
`data/synthetic/ehr.sqlite3` (the synthetic EHR) and
`ai/agents/mdc_checkpoints.sqlite3` (LangGraph checkpoints). Both git-ignored and
rebuildable.

**Privacy.** Synthetic data only. The repository is public. Real PHI would require
an in-institution model and an information-governance review, and is out of scope.
`.env` is git-ignored; `.env.example` carries empty placeholders.

---

## 10. Tech stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.14 | course standard |
| Framework | **Django 6.0** | needs auth, roles, admin and 14 related models — Flask would mean rebuilding all of that |
| Database | SQLite | zero setup; PostgreSQL on Azure later |
| LLM | OpenAI API, `gpt-4o-mini` | direct calls, cheap, temperature 0 |
| Retrieval | ChromaDB, `text-embedding-3-small` | 780 guideline chunks, persisted to disk |
| Agents | LangChain 1.4 / LangGraph 1.2 + `SqliteSaver` | the `interrupt()` human gate, with durable pauses |
| Documents | `python-pptx`, `openpyxl` | slide decks and Excel reports |
| Frontend | Django templates, one shared `base.html`, hand-written CSS | no build step |
| Email | Django email framework — console backend in dev, SMTP via `.env` | nothing else changes to go live |
| Secrets | `.env` + `python-dotenv` | never in code or git |

---

## 11. App flow

1. Prep nurse (or a team coordinator) registers the patient → the team is emailed.
2. The coordinator lists the patient for next week's MDC → the team is emailed.
3. A fellow starts the workup → the specialty checklist is created.
4. `sync_ehr` runs on a schedule, filling in finalised results.
5. The last required result lands → the team is emailed that the patient is ready.
6. The fellow generates the MDC deck for that meeting.
7. The MDC decision is recorded as a category → the patient moves accordingly.
8. **Surgery** → the coordinator books theatre; the peri-op medication check runs.
   **NACT/TNT** → a course is opened and cycles recorded.
9. At the penultimate cycle → the team is emailed to order restaging.
10. Restaging reports land → the team is emailed to review before clinic.
11. Surgery is performed and final pathology recorded → the patient is flagged for
    post-operative MDC re-discussion.
12. A post-op listing clears the flag, and the loop closes.

---

## 12. Testing and "done means"

**Automated: 121 tests, all passing.** `python manage.py test`

| Area | Tests | What they hold to |
|---|---|---|
| `patients` | 47 | workup gating, each notification firing exactly once, decision routing, the post-op flag, rotation-scoped visibility, prep-clinic handover queue, coordinator registration, peri-op distinctions |
| `mdc` | 22 | MDC meeting dates, listings, slide contents, the agent sign-off gate |
| `teams` | 18 | team page routing and scoping, rotation expiry, both "stuck patient" gaps |
| `ehr` | 16 | finalised-only sync, unrequested reports refused, no overwriting, no duplicate emails on repeated passes |
| `ai/guidelines` | 12 | the case carries treatment history; the right decision is asked; coverage warnings |
| `reports` | 6 | counts, access control, real `.xlsx` output |

**Demo scenario (runs end to end).** Register a patient → team emailed → start
workup → `sync_ehr` fills results → "ready for MDC" email → list for MDC →
generate the deck → record TNT → record cycles → restaging alert at cycle 5 →
restaging results → "review before clinic" email → book surgery → peri-op check →
record operation → post-op flag raised → re-list → flag clears.

**Verified by hand, beyond the tests.**

- Every page loads for five roles with no 500s; cross-team access correctly 403s
  and 404s.
- The generated GI MDC deck matches the structure of the team's real decks.
- A LangGraph pause survives a process restart.
- The guideline brain returns clinically sensible answers for a mid-TNT patient
  and a post-gastrectomy patient (both wrong in v0.9).

**Evaluation of the AI layer** (`ai/eval`, 39 synthetic cases): functional
accuracy 85%, judge-semantic agreement 89%, hallucination rate 3.9%, judge
validated at κ 0.779 → 1.000. **Contradiction recall 62%** — the extractor can
silently drop grade, positive nodes and LVI. Refusal recall 100%, but it
over-flags (12 of 36 false alarms).

> That 62% is the single most important number in this document, and it is why
> every extracted field is shown for confirmation with the critical ones marked,
> and why nothing AI-generated is saved without a person.

**Edge cases handled:** missing API key, missing guideline index, unreachable EHR,
a report the team never requested, a preliminary result, a patient with no
checklist, a fellow with no current rotation, a coordinator with no team, a drug
absent from the guideline table.

---

## 13. Risks

| Risk | Mitigation | Status |
|---|---|---|
| The extractor drops a critical finding (62% contradiction recall) | Critical fields marked and sorted first; nothing saved unconfirmed; `needs_human_review` surfaced | Built |
| The guideline brain answers from the wrong cancer's guideline | Explicit coverage check; refusals carry no citations and write no slide note | Built |
| A clinician mistakes an AI suggestion for a recorded decision | Suggestions rendered in a visually distinct block; approving an agent draft does not write a decision | Built |
| "No medication record" read as "no medications to hold" | The two are separated in the API and on the page | Built |
| A polling job emails the team repeatedly | Each alert sent once; asserted by test | Built |
| Guidelines missing for sarcoma, HPB and oesophageal | Coverage checked per diagnosis and read from the index; warning names what is indexed. NCCN agreed as the source; PDFs still to be supplied | **Open** |
| API key leaked in a public repo | `.env` git-ignored, `.env.example` has placeholders only | Built |
| Scope outgrows the course | Modules 2–5 held in §16 until Module 1 was finished | Held |

---

## 14. Safety and governance

> **This tool is labelled NOT FOR CLINICAL USE.** The label appears on every
> page of the application, on the sign-in page, on every slide of every
> generated deck, and on both sheets of every exported workbook. It is removed
> only if and when the tool is formally validated and approved, which has not
> happened.

### 14.1 Scope limits — what this tool is allowed to do

| The tool may | The tool may not |
|---|---|
| Show which investigations are outstanding | Order an investigation |
| Say a patient's workup is complete | Decide a patient is ready for MDC |
| Draft a guideline suggestion with citations | Record an MDC decision |
| Draft an MDC recommendation for sign-off | Approve its own recommendation |
| Extract structured fields from a report | Save those fields to the record |
| Flag a medication against the guideline table | Stop, hold or change a medication |
| Email the team that something is due | Act on that alert itself |

Every row on the right is a clinician's action. The application has no code path
that performs any of them without a person.

**Out-of-scope uses.** This tool must not be used to: triage patients by
urgency; decide who is or is not offered surgery; replace the MDC discussion;
substitute for reading the primary report; or answer a guideline question about
a disease the index does not cover (§8.1).

### 14.2 Human oversight — where the person sits

| AI output | The gate | What happens without the person |
|---|---|---|
| Extracted report fields | `ReportExtraction` is created `PENDING`; a clinician confirms or rejects | Nothing. Unconfirmed extractions are read by nothing else in the app |
| Guideline suggestion | Rendered in a distinct block, marked "for the team to consider, not applied" | Nothing. It never writes to the patient record |
| Agent recommendation | LangGraph `interrupt()` — approve, or reject with feedback | The graph stays paused indefinitely |
| Peri-op medication alert | Displayed to the surgical team | Nothing. The tool cannot change a prescription |
| MDC decision | Typed by a clinician. **Approving an agent draft does not write a decision** | The patient does not move |

This is asserted by test, not just by design: `test_approval_records_the_physician_but_writes_no_decision` checks that the listing's decision fields stay empty through both approval and rejection.

### 14.3 The override path

Every automated output is editable by the clinical team, and overriding never
requires an administrator:

- **A checklist item** — a fellow adds or removes any investigation, including
  ones the conditional rules added. The rule's reason is shown so the fellow can
  see what it assumed (e.g. "clinical stage not recorded — fuller staging
  listed; remove if early").
- **An extracted field** — corrected in the review table before confirming. The
  correction is stored separately from what the model returned, so the record
  shows both.
- **A guideline suggestion** — ignored, or contradicted in the decision the
  clinician types. Nothing forces consistency between them.
- **An agent recommendation** — rejected with feedback, which is fed back into
  the workflow for a revision.
- **A stage or diagnosis the rules read wrongly** — edited on the clinical
  details page, which re-runs the conditional rules.

**No output is final until a person makes it so, and no override is logged as an
exception.** Disagreeing with the tool is the expected case, not an incident.

### 14.4 PHI handling

| Control | Status |
|---|---|
| Real patient data | **Never.** Synthetic only, generated by `seed_demo` and `build_ehr` |
| Repository visibility | Public — which is precisely why no real data may enter it |
| Secrets | `.env`, git-ignored. `.env.example` carries empty placeholders. No key is hardcoded |
| Licensed guideline PDFs (NCCN) | `data/guidelines/`, git-ignored. Only extracted chunks enter the index, and the index is git-ignored too |
| Built databases | `db.sqlite3`, `ehr.sqlite3`, `pharmacy.db`, `mdc_checkpoints.sqlite3` — all git-ignored and rebuildable |
| Identifiers sent to the LLM | The extractor is deliberately built to pull **clinical content, not identity**; its schema has no name, MRN or date of birth |

**What would have to change for real data.** An in-institution model (no data
leaving the hospital), an information-governance review, a private repository,
an audit log of every read, and role-based access reviewed by the department.
None of these exist. Until they do, this tool takes synthetic data only.

### 14.5 Named owners

| Area | Owner | Status |
|---|---|---|
| Clinical content — checklists, pathway rules, MDC categories | Tuqa Al-Ghazawi (author) | Acting |
| Clinical sign-off — is a suggestion safe to show | Consultant, per team | `[TBD — to be named per team]` |
| Departmental accountability | Chairman of Surgical Oncology | `[TBD — to be confirmed]` |
| Technical — code, deployment, secrets | Tuqa Al-Ghazawi | Acting |
| Guideline index — what is indexed, and when it is refreshed | `[TBD]` | Not assigned |
| Information governance — any move toward real data | KHCC IG / AIDI | `[TBD — not yet engaged]` |

> Most of these are `[TBD]` because the tool is a prototype with one author. They
> must be filled before it is shown to a clinical committee, and certainly before
> any real data. Naming an owner is a prerequisite for the incident path below
> working at all.

### 14.6 Incident path

An "incident" is any occasion where the tool showed something wrong, misleading,
or in a way that could have changed a decision.

1. **Stop relying on the affected feature.** No feature is load-bearing — the
   pathway works with every AI output ignored — so this costs nothing clinically.
2. **Record it.** Patient MRN (synthetic), what was shown, what was expected, and
   the page. While the tool is a prototype this is a GitHub issue on the
   repository; a real deployment needs a route that does not require a GitHub
   account.
3. **Reproduce it as a test.** Every clinical bug found so far became a test
   before it was fixed — the guideline brain offering an oesophagectomy to a
   post-gastrectomy patient, naproxen producing no peri-op alert, the workup
   "complete" email repeating. This is the mechanism that stops a fix regressing.
4. **Fix, or disable the feature.** Each AI feature degrades independently: the
   guideline brain, the extractor and the agent workflow all fail to
   "unavailable" without breaking a clinical page, so one can be switched off by
   removing `OPENAI_API_KEY` while the pathway keeps working.
5. **Tell the teams affected** if a wrong output reached a slide or an email.
6. **Roll back** if the fix is not immediate — see §16.3.

**Known open incidents:** none. **Closed:** the four in §12, each with a
regression test.

---

## 15. Ethics

### 15.1 The pillars, and what each one cost

| Pillar | What it required here |
|---|---|
| **Autonomy** | The clinician decides. Every AI output is a draft with a person between it and the record; the override path (§14.3) is always open and never logged as an exception |
| **Beneficence** | The tool exists to stop patients stalling silently between steps — the gap that motivated it (§2) |
| **Non-maleficence** | The safest failure is doing nothing. Every degradation path leaves the pathway working: an unavailable API, an unreachable EHR, an unindexed guideline |
| **Justice** | Every patient in a team's list gets the same checklist for their diagnosis. The rules are explicit and inspectable, not learned from historical practice — so they cannot reproduce a bias in who was previously investigated thoroughly |
| **Explicability** | Guideline answers carry citations; conditional checklist items carry their reason; extracted fields carry the model's own evidence spans; a refusal carries no citations, so it cannot look researched |

### 15.2 Where the ethics were actually load-bearing

Three decisions in this build came from these pillars rather than from
convenience, and each cost something:

1. **A refusal shows no citations.** The vector search always returns passages,
   so it would have been easy — and would have looked more thorough — to list
   them under "Not found in the provided guidelines". Explicability says a
   refusal must not look researched.
2. **"No medication record" is separated from "no medications to hold."** These
   produce an identical empty alert list. Collapsing them is simpler code and
   a cleaner page. Non-maleficence says a gap must not look like a clearance.
3. **An unrecorded stage gets the fuller staging.** The rule could have defaulted
   to "early" and shown a shorter checklist. Under-staging is the worse error,
   so it defaults the other way and says why.

### 15.3 Automation bias — the risk this design does not fully solve

The clearest residual risk is that a clinician, under time pressure, confirms an
extraction or accepts a suggestion without checking it. The controls are: the
critical fields are marked and sorted first; the AI blocks are visually distinct
from recorded fact; approving an agent draft deliberately does not write a
decision, so a second act of typing is required.

**None of this has been measured.** Whether clinicians actually catch the 38% of
critical findings the extractor drops (§12) is an open question that needs a
clinician-in-the-loop study, not a code change. It is the single most important
thing to evaluate before this tool goes anywhere near a real patient.

---

## 16. Deployment and operations

### 16.1 Hosting

| | v1 (now) | Intended |
|---|---|---|
| Runtime | `manage.py runserver`, local | Django on **Render**, over **HTTPS** |
| Database | SQLite file | PostgreSQL (managed) |
| Static files | Django dev server | WhiteNoise |
| `DEBUG` | `True` by default | `False`, enforced by environment |
| `ALLOWED_HOSTS` | empty (dev) | the deployed hostname, from the environment |
| Scheduled jobs | run by hand | `sync_ehr` and `send_due_alerts` on a scheduler |

**Status: not deployed.** There is no `render.yaml`, no `Procfile`, no
`STATIC_ROOT` and no WhiteNoise. The settings are already environment-driven
(`DEBUG`, `ALLOWED_HOSTS`, `SECRET_KEY`, email, `SITE_URL`), so the gap is
configuration and a deploy target, not a rewrite.

### 16.2 Secrets

All configuration comes from the environment, read from `.env` locally via
`python-dotenv`. Nothing is hardcoded, `.env` is git-ignored, and
`.env.example` documents every variable with empty values:
`OPENAI_API_KEY`, `DJANGO_SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `SITE_URL`,
and the six `EMAIL_*` variables. On Render these become dashboard environment
variables; `.env` is never deployed.

`SECRET_KEY` falls back to a development literal **only** when the environment
does not set it — and that fallback is why it is called
`django-insecure-…`. A real deployment must set it.

### 16.3 Versioning and rollback

**Versioning.** Git, on `master`, with one commit per coherent change and a
message explaining why. The deployed version is a commit SHA. The PRD carries
its own version number (this is 1.1), and the LangGraph runtime contract is
pinned (`langgraph-checkpoint-sqlite==3.1.1`) because a 2.x release silently
downgrades a dependency Django's agent workflow needs.

**Rollback triggers.** Roll back immediately, without discussion, if any of
these is observed:

| Trigger | Why immediate |
|---|---|
| An AI output is written to a patient record without a person confirming it | The core guarantee of the design has failed |
| A notification fires repeatedly for the same event | Teams stop reading the alerts, which is worse than no alerts |
| A user sees a patient outside their team | The access model has failed |
| The "not for clinical use" label is missing from any page or generated document | The tool can be mistaken for an approved one |
| A guideline answer cites a passage from the wrong disease | The grounding claim is false |
| The peri-op check reports "no holds" for a patient whose record was never read | A gap is being shown as a clearance |

**How.** `git revert` the offending commit and redeploy; the schema is
additive, so a revert does not strand data. A feature can also be disabled
without a deploy by removing `OPENAI_API_KEY` from the environment, which turns
every AI feature off and leaves the pathway intact.

### 16.4 Monitoring and drift

**What to watch.**

| Signal | Where it comes from | What it means |
|---|---|---|
| Guideline refusal rate | `GuidelineSuggestion.refused` | A rise means the index no longer covers what teams are asking about |
| Coverage warnings raised | `GuidelineSuggestion.coverage_note` | Which diseases are being asked about with no guideline indexed |
| Extraction rejection rate | `ReportExtraction.status` | A rise means the extractor is degrading, or report formats have changed |
| Extraction correction rate | `confirmed_fields` vs `raw_fields` | **The most useful drift signal there is** — which fields clinicians keep having to fix |
| Agent revision count | `MDCAgentReview.revisions` | How often physicians send a draft back |
| Alerts sent vs acted on | `Notification.read_at` | Alert fatigue |
| EHR sync failures | `sync_ehr` output | The interface has changed |

Every one of these is already recorded in the database. **None is yet surfaced
on a dashboard or alerted on** — that is the operational gap.

**Drift is expected from four directions:** the OpenAI model changes underneath
a pinned name; the KHCC guidelines are revised and the index goes stale; report
formats change and the extractor degrades; the EHR schema changes.

**The plan.** Re-run `python -m ai.eval.run` against the gold set on every
dependency bump and quarterly, and compare against the recorded baseline (§12).
A drop in contradiction recall or a rise in hallucination rate blocks the
release. The guideline index carries no version stamp today — it should record
which guideline edition each chunk came from, so a stale index is visible rather
than inferred.

---

## 17. Open questions

- [ ] **Prep-clinic queue.** Resolved: patients drop off once the MDC has
      discussed them, and her list is grouped by team. Still open — a patient
      who never reaches an MDC at all stays on her queue indefinitely.
- [ ] **Guideline coverage.** NCCN agreed as the source for hepatobiliary and
      oesophageal. The ingestion path is built (`manage.py add_guideline`); the
      PDFs still need to be supplied and indexed. Sarcoma is also uncovered —
      NCCN too?
- [ ] **Agent tools.** Should `guideline_lookup` and `drug_interaction_check` call
      `ai/rag` and `ai/pharmacy` for real, or is the direct route enough?
- [ ] **Confirmed extractions** are stored but not copied into the patient's
      structured fields. Which fields should populate automatically?
- [ ] **Per-MDC Excel export** for MDC coordinators — still open from v0.9.
- [ ] **Pre-operative consult checklist** — needed for v2?
- [ ] **Deployment.** Azure App Service + PostgreSQL is assumed
      `[assumed — change if you want]`. Nothing has been provisioned.
- [ ] **Real EHR access.** Which system, which interface, whose approval?

---

## 18. Appendix A — Workup checklists per diagnosis

The system shows the matching checklist per patient; items fill in as results
arrive from the EHR. The guideline brain *suggests* additions; it never edits the
checklist itself.

> **Status: signed off 5 September 2026 and fully encoded.**
> `patients/workup.py` implements these per **diagnosis group**, not per
> specialty — colon and rectum, gastric and oesophageal, and pancreas/biliary/liver
> are separate checklists, resolved from the diagnosis text by
> `patients/diagnosis.py`. The conditional rules below are live:
>
> | Rule | Condition |
> |---|---|
> | Fertility counselling | female and under 40 |
> | Breast: abdomen US + CXR | early — a stage is recorded and it is not T3/T4, node-positive or III/IV |
> | Breast: CAP CT + bone scan | locally advanced, node-positive, **or no stage recorded** |
> | Breast: genetic testing | under 65 **or** a positive family history |
> | Colorectal: RAS/BRAF | metastatic (M1, stage IV, or "metastatic" in the diagnosis) |
> | Thyroid: calcitonin, RET | optional — if medullary is suspected |
>
> An unrecorded stage deliberately gets the *fuller* staging, because
> under-staging is the worse error; the reason is written onto the investigation
> so the fellow can see it and change it. Every conditional item records why it
> was added.

### Baseline — applies to every patient
- Pathology/biopsy confirmation
- **Pathology review for all** (tumor-board review)
- CBC · CMP (LFTs + renal)
- Performance status
- Review of prior/outside imaging
- **Fertility counselling for all females < 40**

### Breast ✅ *(confirmed)*
- Diagnostic mammogram + breast US
- Core biopsy with **ER/PR/HER2 + Ki-67**
- Breast MRI (selected)
- **Staging imaging (conditional — overrides baseline CT):**
  - **Early breast cancer →** Abdomen US + CXR
  - **Locally advanced / node+ / symptomatic →** CAP CT
- **Genetic testing if age < 65 OR positive family history**

### Colon ✅ *(confirmed)*
- Colonoscopy + biopsy · **CAP CT for staging** · CEA · MMR/MSI · RAS/BRAF (if metastatic)

### Rectum ✅ *(confirmed)*
- **Pelvic MRI** (key) · Colonoscopy + biopsy · **DRE for tumour distance** · **CAP CT** · CEA · MMR/MSI

### Thyroid ✅
- Neck US · FNA (Bethesda) · TSH/thyroid function · Calcitonin if medullary suspected · Laryngoscopy · Genetic (RET) for medullary

### Gastric ✅
- EGD + biopsy · HER2 · EUS · Staging laparoscopy (selected) · CEA · CAP CT

### Oesophageal ✅
- EGD + biopsy · EUS · PET-CT · HER2 / PD-L1 · CAP CT

### Pancreas / HPB (biliary) ✅
- Pancreas-protocol CT · CA 19-9 · EUS + biopsy · MRCP

### Liver (HCC) ✅
- Triphasic CT or MRI · AFP · Hepatitis serology · Child-Pugh score

### Sarcoma ✅
- MRI of primary site · Core biopsy (ideally at a sarcoma centre) · CT chest

> ✅ = clinically confirmed. All nine signed off on 5 September 2026.

---

## 19. Appendix B — Platform vision (Modules 2–5)

Module 1 — the team and patient-flow dashboard — is the subject of this PRD and
is built. The wider Surgical Department Dashboard remains the direction of travel.

**The enabler, now in place:** the system records **dated events** — registration,
each result, each MDC decision, each cycle, the date of surgery. Statistics and
KPIs need exactly that, and it exists.

| Module | Scope | Status |
|---|---|---|
| **1 — Team / patient flow** | this PRD | **Built** |
| **2 — Statistics** | monthly and yearly new-patient and surgery counts by specialty, consultant, diagnosis | Not started |
| **3 — KPIs** | time from registration to MDC, MDC to surgery, surgery to post-op discussion | Not started |
| **4 — M&M** | morbidity and mortality review records | Not started |
| **5 — Events** | departmental calendar | Not started |

---

## 20. How to run it

```bash
python -m venv .venv
.venv/Scripts/activate            # source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
cp .env.example .env              # add OPENAI_API_KEY for the AI features
python manage.py migrate
python manage.py seed_demo        # teams, users, patients at every stage
python manage.py build_ehr        # synthetic EHR: results + medications
python manage.py sync_ehr         # pull them into the dashboard
python manage.py runserver
```

Demo logins, password `demo1234`: `prep1` (prep coordinator), `chair1`
(chairman), `coord2` (team coordinator), `cons2` (consultant), `fellow1`
(fellow), `mdc1` (MDC coordinator).

**Scheduled jobs** (Task Scheduler or cron):

```bash
python manage.py sync_ehr          # pull finalised results; email when complete
python manage.py send_due_alerts   # restaging due; post-op patients not re-listed
```

> These demo logins exist for the synthetic prototype only and must never be
> created in a real deployment.
