# PRD — Surgical Oncology Patient Flow Dashboard

**Document owner:** Department lead (you)
**Author of draft:** Claude Code (with you)
**Date:** 2026-06-16
**Status:** Draft v0.1 — for your review
**Decisions locked in:** Phased build · English interface · Synthetic-data prototype first · AI guidelines brain in a later phase

> **How to read this document:** This is the plan in plain English. Nothing here is code.
> Read it, then tell me what to change. The sections marked **[OPEN QUESTION]** are things
> I need you to confirm. We will only start building after you approve this.

---

## 1. The problem (why we are building this)

Today, the new-patient journey in the surgical oncology department runs on WhatsApp
messages, phone calls, and individual memory. This causes:

- Patients "falling through the cracks" between steps.
- No single place to see where a patient is in the journey.
- No automatic reminders — coordinators must chase people manually.
- Reports (counts by specialty, diagnosis, age, consultant) are assembled by hand.
- MDC and planning-round slides are built manually from scratch each week.

## 2. The goal (what success looks like)

One shared dashboard where:

- Every patient is registered once and then **automatically visible** to the right team.
- Each role is **notified automatically** when a patient reaches a step they own.
- Anyone on a team can see, at a glance, **where each patient is** in the journey (a timeline).
- The **workup checklist** updates as results become available.
- **Reports and Excel sheets generate themselves**.
- **MDC and planning-round slides generate themselves** from the patient's data.

## 3. Scope

### In scope (the full vision, built in phases)
Registration, team assignment, automatic notifications + email, MDC list management,
workup checklist with live result reflection, patient timeline, MDC decision tracking,
surgery scheduling, post-op follow-up, role-based dashboards, reports + Excel export,
auto-generated slides, and (later) an NCCN guidelines suggestion engine.

### Out of scope (for now)
- Real patient data and live hospital-system integration (we use synthetic data first).
- Replacing the hospital EMR — this sits *alongside* it.
- Billing, pharmacy, OR booking systems integration.
- Mobile native apps (the dashboard will work in a phone browser, but no App Store app).

### Non-goals
- This is **not** a diagnostic device. The AI brain *suggests*; clinicians decide.

---

## 4. Users and roles

| Role | Sees | Can do |
|---|---|---|
| **Prep-clinic coordinator** | All patients | Register patients, assign to a team, follow all patients, generate weekly/monthly reports + Excel |
| **Chairman of department** | All patients | View everything (read-only), view all reports |
| **Team clinic nurse coordinator** | Only their team's patients | Assign that rotation's fellows to the team, add patients to the weekly MDC list, list patients for surgery |
| **Fellow** | Only their assigned team's patients | Follow the workup flow, build weekly MDC slides + biweekly planning-round slides |
| **Consultant** | Only their own team's patients | View and follow their team's patients |
| **MDC coordinator** | Only patients **added to their MDC's list** by team coordinators (Breast / GI / Sarcoma / Thyroid) | Manage that MDC's discussion list, record decisions, and **export her MDC's cases to Excel (weekly & monthly, separately)** |

**Rotation rule:** Fellows rotate every 3 months (e.g. Jul–Sep, Oct–Dec). At the start of
each rotation, the team nurse coordinator assigns that rotation's fellows so they gain
access to their team's dashboard. When the rotation ends, that access is removed.

### The teams (consultants)

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

### The MDCs (tumor boards)
- **Breast MDC**
- **GI MDC** — hepatobiliary, pancreatic, colon, rectum, gastric, esophageal, small bowel, appendix, and all GI cases
- **Sarcoma MDC**
- **Thyroid MDC**

---

## 5. The patient journey (the heart of the system)

This is the process the dashboard automates, step by step. Each step lists **who acts**,
**what they enter**, and **what the system does automatically**.

### Step 1 — Registration at the preparatory clinic (first encounter)
- **Who:** Prep-clinic coordinator (nurse).
- **Enters:** Name, MRN, Date of birth, Diagnosis, Specialty, Assigned consultant.
- **Also:** Assigns the patient to a **team**.
- **System does automatically:** Sends an **in-app notification + email** to the team's
  **nurse coordinator, consultant, and current fellows**: *"You have a new patient
  scheduled for the upcoming clinic."* (This replaces today's manual WhatsApp + phone call.)

### Step 2 — Team coordinator prepares for MDC
- **Who:** Team nurse coordinator.
- **Does:** Adds the patient to the **proposed MDC list for next week**.

### Step 3 — Consultant clinic assessment
- **Who:** Consultant (with fellow).
- **Does:** Assesses the patient, **confirms which investigations** are needed → workup begins.

### Step 4 — Workup
- **Who:** Fellow follows; whole team can see.
- **System shows:** A **workup checklist** visible to the entire team. As each result
  becomes available, the system **reflects it automatically** (pulled from the database).
  *(In the prototype, results come from a synthetic database we will build.)*

### Step 5 — MDC discussion + categorization
- **Who:** MDC coordinator + team; category assigned by the team nurse coordinator.
- **Does:** Patient is discussed and a **decision** is recorded. The coordinator then files
  the patient into **one category** based on the result:

  | Category | What it means | Extra data captured |
  |---|---|---|
  | **Surgery** | Listed for an operation | (goes to the fellows' "Planned for surgery" list — see Step 6) |
  | **NACT** | Neoadjuvant chemotherapy first | **Month started**; patient appears on the dedicated **"NACT patients"** list |
  | **TNT (rectal)** | Total neoadjuvant therapy for rectal cancer | **Month started**; patient appears on the dedicated **"TNT" list** |
  | **Referred to medical team** | Managed medically (e.g. palliative/definitive systemic therapy) | Referral recorded |
  | **Watch & wait (rectal)** | Non-operative management after complete clinical response to TNT | **W&W start date** + **next investigations date** |
  | **Surveillance / other** | Routine follow-up or other plan | Plan note |

- **"Stay on the list" rule:** Patients in **NACT** or **TNT** remain on the team's active
  list until the **definitive decision** is made. When neoadjuvant treatment finishes, they
  move to a **Restaging** state (awaiting restaging imaging/results), which the team follows
  **before the upcoming clinic**. The system **auto-flags when re-discussion is due** (so they
  are not lost), and after re-discussion they are **re-categorized** (commonly → Surgery).
- **Who moves these follow-up states:** the **team nurse coordinator** is responsible for moving
  patients into **Restaging**, **Watch & wait**, or **Surveillance**, and for setting the
  **next investigations date**. (Enforced once role-based screens are built; today done in admin.)

### Step 6 — Surgery scheduling + pre-operative workup
- **Who:** Fellows (with the team nurse coordinator).
- **Does:** Patients in the **Surgery** category appear on the fellows' **"Planned for
  surgery"** list. For each, the fellow:
  - **Sets the proposed surgery date.**
  - **Completes the pre-operative workup checklist** — a *fitness-for-surgery* gate,
    separate from the diagnostic workup, with consults such as **Anesthesia, Cardiology,
    Internal Medicine** (and any others needed).
- The patient is marked **"Ready for surgery"** only once the required pre-op consults clear.

### Step 7 — Post-operative follow-up loop
- **Who:** The whole team (coordinator, consultant, fellows) — **fully visible to all of them.**
- **The loop** (MDC is re-entered *after* surgery, not just before):
  1. Patient is marked **operated** → capture **surgery date, procedure, surgeon**; status
     becomes **"Post-op — pathology pending."**
  2. **Final pathology** is tracked like a result item. When it arrives, the system
     **auto-flags the patient for post-op MDC re-discussion** (no operated patient is forgotten).
  3. **Post-op MDC** sets the next **category**:
     - **Adjuvant therapy** (chemo/radiation) → patient **stays on the active list** with a
       periodic re-review flag (same pattern as NACT).
     - **Surveillance** → moves to a quiet **surveillance/follow-up** list.
     - **Referred to medical team** → managed elsewhere.
  4. The loop **closes** only when the patient enters surveillance or is referred out.
- **Visibility rule:** Every stage of this loop — and the patient's position in it — is
  visible to the **entire team**, not only the fellow who updates it.

### The timeline
For every patient, the dashboard shows a **visual timeline** of all steps above, including the
post-op loop (done / current / upcoming), **visible to the whole team** — so anyone can
instantly see where the patient is.

---

## 5A. Role dashboards (task-first design)

**Principle: tasks first, lists second.** Each role logs in and immediately sees *what they
need to do today*, not just a list of patients to hunt through. The same "task inbox" pattern
is reused across roles for a consistent feel (fellow defined now; coordinator and consultant
follow the same shape later).

### The fellow's daily dashboard (the engine of the process)

1. **🔔 Needs my attention (task inbox)** — top of the page, the most important panel.
   Auto-built actionable items: new patient registered to my team → review · workup result
   arrived → check · pre-op consult cleared/pending · **MDC slides due (weekly)** ·
   **planning-round slides due (biweekly)** · re-discussion flags (NACT/TNT due, post-op
   pathology ready).
2. **📅 This week's MDC** — patients I'm presenting, each with a *"slides ready?"* indicator
   and a **Generate slides** button.
3. **📊 My patients by stage** — compact columns with live counts (click to expand):
   `New · In workup · Awaiting MDC · NACT · TNT · Planned for surgery · Post-op · Surveillance`.
4. **🔎 Quick search** by name/MRN; clicking any patient opens their **timeline + full detail**.

> Whole-team visibility (incl. the post-op loop) means consultants and coordinators see the
> same patient states; only the *actionable tasks* in panel 1 differ by role.

### The prep-clinic coordinator's dashboard (oversight + registration)

This coordinator sees **all patients across all teams**, registers them, and produces reports.

1. **➕ Register new patient** — prominent button opening the registration form (Name, MRN,
   DOB, diagnosis, specialty, consultant, team).
2. **🔔 Oversight flags (task inbox)** — patients **stuck too long at a stage**, e.g.
   registered >3 days but not yet added to an MDC list, or workup not started. This is her
   "nothing falls through the cracks" panel.
3. **📊 All patients by team & stage** — full pipeline view with live counts; filter by team,
   specialty, consultant, or stage.
4. **📈 Reports & exports** — generate the weekly/monthly report and **download the Excel
   sheet** in one click (see Section 7).
5. **🔎 Quick search** by name/MRN.

> The **chairman's dashboard** is the same all-patients view in **read-only** mode, plus
> access to all generated reports.

## 6. Notifications

| Trigger | Who is notified | Channel |
|---|---|---|
| Patient registered & assigned to a team | Team nurse coordinator, consultant, current fellows | In-app + email |
| **Start of each week (Monday)** — patients due this week for **restaging** or **watch & wait** results | Consultant, fellow, team nurse coordinator | In-app + email |
| (Later phases) Workup result ready, MDC scheduled, decision recorded, surgery listed | The relevant role(s) | In-app + email |

> **[RESOLVED]** v1 uses **in-app + email only**. No WhatsApp automation. (WhatsApp could
> be added later if needed.)

---

## 7. Reports (prep-clinic coordinator & chairman)

**Who:** Prep-clinic coordinator generates them; chairman can view all of them.
**When:** **Weekly** (this week's registrations) and **monthly**. Both also pickable for a
custom date range.

### What the report counts
Total number of patients, broken down by: **specialty · diagnosis · age · assigned consultant**.

### The auto-generated Excel file (one click to download)
The file has **two sheets**:

1. **Summary** — the counts (for management at a glance):
   - Patients per **specialty**
   - Patients per **diagnosis**
   - Patients per **consultant**
   - Patients per **age band** *(proposed bands: <40 · 40–49 · 50–59 · 60–69 · 70+)*
   - Grand total for the period
2. **Patient list (detail)** — one row per patient with columns:
   `MRN · Age · DOB · Diagnosis · Specialty · Consultant · Team · Registration date ·
   Current stage · MDC category`.

### MDC coordinator exports
The **MDC coordinator** can export **her MDC's cases to Excel**, generated **separately** as:
- **Weekly** — the cases listed for a given meeting/week.
- **Monthly** — all cases listed/discussed on her board that month.

(Built on each MDC listing's **meeting date**, so grouping by week or month is just a date filter.)

> **[OPEN QUESTION]** Age bands above are a proposal — adjust if your institute reports
> differently. Also: should the detail sheet include the **patient name**, or **MRN only**
> (more privacy-friendly for management reports)?

---

## 8. Slides (built by fellows)

- **MDC slides** — weekly.
- **Planning-round slides** — biweekly.
- Generated **from the patient's data** with a **professional design**.
- **Name, MRN, and genetic testing** must appear at the **top** of each slide.
- **Investigation results pulled from the database** (synthetic database in the prototype).
- (Later, with the AI brain) the **evidence supporting an MDC decision appears in the
  slide's notes field.**

> **[NEEDED LATER]** Please upload example slides (current MDC slides and planning-round
> slides) when we reach the slides step, so the generated design matches your format.

---

## 9. The NCCN guidelines brain (later phase)

A suggestion engine that, per patient/case, **suggests the workup** and **suggests an MDC
decision**, citing the **NCCN evidence** that supports it (shown in the slide notes field).

> This is the most advanced piece. Per your decision, we build it **after** the core
> dashboard is working and trusted. It will always be **advisory** — clinicians decide.

---

## 10. Data we store (in plain language)

- **Patient:** name, MRN, date of birth, diagnosis, specialty, assigned consultant, team,
  current step in the journey, dates of each step.
- **Team:** name, consultant(s), specialty, MDC it belongs to, current fellows.
- **User:** name, role, team (if any), login credentials.
- **Workup item:** which investigation, status (pending / ready), result, date.
- **MDC entry:** which MDC, date, decision, **category** (Surgery / NACT / TNT / Referred /
  Surveillance), notes/evidence, **re-discussion-due flag**.
- **NACT/TNT tracking:** category, **month started**, cycles/interval, next-review date.
- **Pre-op workup item:** which consult (Anesthesia / Cardiology / Internal Medicine / other),
  status (pending / cleared), date.
- **Surgery entry:** proposed date, **ready-for-surgery** status, scheduled date, status.
- **Notification:** who, what, when, read/unread.

*(This becomes the precise database design at the build step — shown here so you can sanity-check it.)*

---

## 11. Proposed technology (explained simply)

You don't need to memorize these — here is what I recommend and why, in plain terms.

| Part | Recommendation | Why (plain language) |
|---|---|---|
| The app itself | A **web app** (opens in any browser — Chrome, Edge, phone) | Nothing to install for users; just a link and a login |
| Building blocks | **Python (Django)** | One language for the whole app, plus it natively makes the **Excel sheets, slides, and the future AI brain** — fewer moving parts for a beginner |
| Database | **PostgreSQL** | Reliable, standard, free |
| Login & roles | Built into Django | Handles who-can-see-what securely |
| Excel files | `openpyxl` | Standard Python tool for spreadsheets |
| Slides | `python-pptx` | Standard Python tool for PowerPoint |
| AI brain (later) | **LangChain / LangGraph** | The standard for guideline-style reasoning |
| Where it runs (later) | **Microsoft Azure** (App Service + Azure Database for PostgreSQL) | Hospital already trusts Azure — eases future real-data approval |

> **[RESOLVED]** No hospital IT constraints initially. Deployment target is **Azure**, which
> is compatible with the hospital environment.

---

## 12. Build roadmap (phases)

Each phase ends with something you can click and test.

- **Phase 0 — Foundations:** project setup, login, the 6 roles, the teams, synthetic-data setup.
- **Phase 1 — Registration + notifications:** prep-clinic registration form, team assignment,
  automatic in-app + email alerts to the team. *(Your "first step".)*
- **Phase 2 — Team dashboard + timeline:** each role sees the right patients; patient timeline.
- **Phase 3 — MDC list + workup checklist:** weekly MDC list, live-reflecting workup checklist.
- **Phase 4 — MDC decision + categories + surgery + post-op:** record decision; assign
  category (Surgery / NACT / TNT / Referred / Surveillance); NACT & TNT lists with start
  month and re-discussion flags; "Planned for surgery" list with pre-op consult checklist
  (Anesthesia / Cardiology / Internal Medicine) and "ready for surgery" gate; post-op follow-up.
- **Phase 5 — Reports + Excel export.**
- **Phase 6 — Slides generation** (you upload example slides here).
- **Phase 7 — NCCN guidelines brain.**
- **Phase 8 — Deployment** (make it live for your colleagues).

---

## 13. Security & privacy (important even with fake data)

- Prototype uses **synthetic data only** — no real patient information.
- Role-based access: users only see what their role allows.
- Before any real-patient use, we add: encryption, audit logs, and hospital IT/security
  approval. **We will not put real patient data in until that approval exists.**

---

## 14. Open questions

**Resolved (2026-06-16):**
- ✅ **Notifications:** in-app + email only for v1 (no WhatsApp).
- ✅ **Hospital IT:** no constraints initially; deploy on **Azure**.
- ✅ **Specialty list:** confirmed correct.

**Still open:**
1. **Login accounts:** roughly how many total users? Will you provide the list of names/emails
   per role, or should the prototype use invented logins?
2. **Anything in Section 5 (the journey)** that doesn't match reality — keep refining as needed.

---

## 15. Appendix A — Workup checklists per diagnosis (clinical draft)

Checklists are organized **per diagnosis**. The system shows the matching checklist for each
patient; items auto-reflect as results arrive. (Later, the NCCN brain will *suggest* from these.)

### Baseline — applies to every patient
- Pathology/biopsy confirmation
- **Pathology review for all** (tumor-board review)
- CBC · CMP (LFTs + renal)
- Performance status
- Review of prior/outside imaging
- **Fertility counseling for all females < 40**

### Breast ✅ *(confirmed)*
- Diagnostic mammogram + breast US
- Core biopsy with **ER/PR/HER2 + Ki-67**
- Breast MRI (selected)
- **Staging imaging (conditional — overrides baseline CT):**
  - **Early breast cancer →** Abdomen US + CXR
  - **Locally advanced / node+ / symptomatic →** CAP CT (chest/abdomen/pelvis)
- **Genetic testing if age < 65 OR positive family history**

### Colon ✅ *(confirmed)*
- Colonoscopy + biopsy
- **CAP CT for staging**
- CEA
- MMR/MSI
- RAS/BRAF (if metastatic)

### Rectum ✅ *(confirmed)*
- **Pelvic MRI** (key)
- Colonoscopy + biopsy
- **DRE for tumor distance**
- **CAP CT for staging**
- CEA
- MMR/MSI

### Thyroid 🟡 *(draft — awaiting your review)*
- Neck US · FNA (Bethesda) · TSH/thyroid function
- Calcitonin if medullary suspected · Laryngoscopy (vocal cords)
- Genetic (RET) for medullary

### Gastric 🟡 *(draft)*
- EGD + biopsy · HER2 · EUS · Staging laparoscopy (selected) · CEA · CAP CT

### Esophageal 🟡 *(draft)*
- EGD + biopsy · EUS · PET-CT · HER2 / PD-L1 · CAP CT

### Pancreas / HPB (biliary) 🟡 *(draft)*
- Pancreas-protocol CT · CA 19-9 · EUS + biopsy · MRCP

### Liver (HCC) 🟡 *(draft)*
- Triphasic CT or MRI · AFP · Hepatitis serology · Child-Pugh score

### Sarcoma 🟡 *(draft)*
- MRI of primary site · Core biopsy (ideally at sarcoma center) · CT chest (mets screen)

> ✅ = confirmed by you · 🟡 = draft, awaiting your review.

---

## 16. Platform vision — Surgical Department Dashboard

The system grows from a single patient-flow app into a **Surgical Department Dashboard**: one
login with a **navigation menu** across several modules. What is built today (the patient
journey) becomes **Module 1**. Build order: **finish and test Module 1 first**, then add the
rest. Every module respects the existing role/access rules.

### Module 1 — Team / Patient-flow dashboard  *(in progress — finish first)*
The per-role patient journey already described in this PRD. Remaining work to "finish": MDC
add-to-list + triage, MDC decision + post-MDC categories, workup checklist, registration page,
notifications (email), surgery scheduling + pre-op consults, post-op loop, reports/Excel,
slides, and the role-specific home/task views.

### Foundation for stats & KPIs — dated events  *(enabler)*
Statistics and KPIs need **when** things happened, not just the current stage. So we record
**key milestone dates** per patient: registered ✅, consultant-clinic date, workup start, MDC
date ✅ (listing meeting date), decision date, **surgery date**, post-op re-discussion date.
Implemented pragmatically as key date fields and/or a small journey-event log. Without this,
counts like "surgeries in June" and durations like "days to surgery" cannot be computed.

### Module 2 — Statistics dashboard
Departmental activity on a **monthly** and **yearly** basis:
- **Number of new patients** (from registration date) — total and by specialty / team / diagnosis / age band.
- **Number of surgeries** (from surgery date) — total and by team / specialty / procedure.
- Trends over time (month-by-month, year-over-year).
- Exportable to Excel (reuses the reports engine).

### Module 3 — KPIs
Performance indicators computed from the dated events, e.g.:
- Median days: registration → consultant clinic → MDC → surgery.
- % of patients discussed at MDC within a target interval.
- Neoadjuvant → restaging interval; time to definitive decision.
- Throughput per team / per specialty.
Shown as KPI tiles with targets and trend arrows.

### Module 4 — M&M (Morbidity & Mortality)
A register for departmental M&M meetings (new data model):
- Case (optionally linked to a patient), date, procedure.
- Complication + severity (e.g. Clavien–Dindo grade), **morbidity vs mortality**.
- Root cause / lessons learned; presented status; meeting date.
- Export for M&M sessions; feeds relevant stats/KPIs (e.g. complication rate).

### Module 5 — Events
A department calendar: MDC meetings, M&M sessions, planning rounds, etc. — date/time, type,
notes/attendees. Later can drive reminders.

### Access (per module, high level)
- **Module 1** — as already defined per role.
- **Statistics / KPIs** — chairman, prep-clinic coordinator, consultants, team coordinators
  (department-level views); scope by team where appropriate.
- **M&M / Events** — department-wide (exact edit rights TBD when built).

> More modules may be added later. This section is the running vision; each module gets its
> own detailed spec when we reach it.

---

*End of draft. Tell me your edits, then we lock it and start Phase 0.*
