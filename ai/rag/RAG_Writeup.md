# Session 6 — Clinical Knowledge Retrieval System (RAG)

**Project:** MDC guideline assistant — a retrieval-augmented generation system over the KHCC oncology clinical practice guidelines, built as the `ai/rag` module of the team-dashboard capstone.
**Source document:** merged KHCC Clinical Practice Guidelines (280 pages, fully digital text) covering six cancers — Thyroid, Breast, Colon, Gastric, Pancreatic, and Rectal.
**Data:** institutional guideline text only; all queries answered strictly from retrieved passages.

---

## 1. Pipeline

```
280-page PDF -> parse -> chunk -> embed -> ChromaDB
question -> embed -> nearest chunks -> LLM answers ONLY from them -> cited answer
                                                      -> DeepEval scores -> grade-and-retry upgrade
```

## 2. Parsing

The assignment suggests LlamaParse. I inspected the PDF first: 280 pages, 0 scanned pages, ~2,550 characters per page — it is clean, digital text. LlamaParse's main advantage is rescuing scanned or heavily tabular PDFs; on clean text it adds an external dependency and API key for little gain. I therefore parsed locally with `pypdf` and stripped repeated boilerplate (confidentiality banners, page footers, CPG headers). LlamaParse would be the right choice for a scanned or table-dense guideline, and the parse step is isolated so it can be swapped without touching the rest of the pipeline.

## 3. Chunking (justification)

The six guidelines were split by page range, then each was packed into chunks of about 1,000 characters on paragraph boundaries, with roughly 150 characters of overlap. Every chunk is tagged with its cancer and source pages.

- **Size (~1,000 chars):** large enough to hold one complete recommendation with its condition, small enough that retrieval stays precise. Larger chunks return a page of noise around the needed sentence; smaller chunks return fragments that lose their subject.
- **Overlap (~150 chars):** a recommendation that falls on a chunk boundary would otherwise be split — condition in one chunk, action in the next. Overlap keeps the full statement retrievable from either neighbour.
- **Metadata tagging (cancer + pages):** lets every answer cite its source and — critically for a six-cancer corpus — keeps a thyroid question from being answered with gastric text.

Result: **780 chunks** (Thyroid 112, Breast 258, Colon 147, Gastric 69, Pancreatic 60, Rectal 134).

## 4. Embedding, indexing, and grounded answering

Chunks were embedded with OpenAI `text-embedding-3-small` and stored in a persistent ChromaDB collection. At query time the question is embedded the same way and the nearest chunks are retrieved by vector similarity — retrieval by meaning, not keywords.

The generation prompt enforces grounding: answer only from the numbered passages, cite each claim with its source label, and if the answer is not present reply exactly "Not found in the provided guidelines." This was verified with an out-of-scope query (melanoma, absent from all six guidelines): retrieval still returned its nearest chunks, but the system correctly refused to answer rather than improvising — the core anti-hallucination property of a clinical RAG system.

## 5. Evaluation (DeepEval, 5 grounded Q&A pairs, 4 metrics)

Five question / gold-answer pairs were written, one per guideline, with each gold answer taken directly from the source text. Each RAG answer was scored on faithfulness, answer relevancy, contextual precision, and contextual recall, using an LLM judge.

**Judge-model finding:** with `gpt-4o-mini` as judge, the faithfulness metric intermittently failed with a length-limit parse error on two questions — the judge's structured reply was truncated before completion. Switching the judge to `gpt-4o` resolved this and produced a complete, stable baseline. Notably, some scores shifted between the two judges on identical answers (e.g. colon faithfulness 0.75 → 1.00), an early sign that the judge itself is a source of variance and needs validation — the subject of Session 7.

**Baseline scorecard (gpt-4o judge):**

| Question | Faithfulness | Relevancy | Ctx precision | Ctx recall |
|---|---|---|---|---|
| Thyroid — total thyroidectomy | 1.00 | 1.00 | 1.00 | 1.00 |
| Breast — DCIS margin | 1.00 | 1.00 | 0.83 | 1.00 |
| Colon — baseline blood tests | 1.00 | 0.75 | 1.00 | 1.00 |
| Rectal — pre-treatment evaluation | 1.00 | 1.00 | 1.00 | 1.00 |
| Pancreatic — histological proof | 0.50 | 1.00 | 1.00 | 1.00 |
| **Average** | **0.90** | **0.95** | **0.97** | **1.00** |

Retrieval was essentially perfect across all six cancers (precision 0.97, recall 1.00). The one clear generation failure was the pancreatic answer (faithfulness 0.50): it stated histological proof is mandatory only in unresectable cases and dropped the guideline's second condition, "or when a neoadjuvant strategy is planned" — an overgeneralization, not a retrieval miss.

## 6. Agentic upgrade — grade-and-retry, and its measured effect

Because retrieval was already maxed, a retrieval-side upgrade (query rewrite) had little to gain; the weakness was generation faithfulness. I implemented grade-and-retry: the system drafts an answer, a grader LLM checks whether every claim is supported by the context, and on failure the answer is rewritten with the grader's feedback.

**First attempt — grader = generator model (gpt-4o-mini):** near-zero effect (faithfulness 0.90 → 0.90); the pancreatic case stayed at 0.50. The grader shared the generator's blind spot and passed the flawed answer. An agentic loop only helps if the checker is genuinely more capable than the writer.

**Second attempt — independent stronger grader (gpt-4o):** the grader caught the pancreatic omission, forced a real retry, and the answer became fully grounded.

**Metric deltas (baseline vs strong-grader grade-and-retry):**

| Metric | Baseline | Grade-and-retry | Δ |
|---|---|---|---|
| Faithfulness | 0.90 | 1.00 | +0.10 |
| Answer relevancy | 0.95 | 0.75 | −0.20 |
| Contextual precision | 0.97 | 0.97 | 0.00 |
| Contextual recall | 1.00 | 1.00 | 0.00 |

The upgrade did exactly what it targeted — faithfulness reached 1.00, with the pancreatic case fixed from 0.50 — but **relevancy fell 0.20**. Forcing strict grounding made answers more complete but less focused on the precise question asked. Retrieval metrics were unchanged, as expected, since the agent rewrites rather than re-retrieves.

## 7. Critical analysis

- **The upgrade is a trade-off, not a strict win.** Grade-and-retry moves the system along a faithfulness ↔ relevancy curve at 2–3× the API cost per answer. For a clinical guideline tool I would accept lower relevancy for higher faithfulness — a wrong or incomplete clinical statement is more dangerous than a slightly unfocused one. The right operating point is a use-case decision, not an absolute.
- **The grader must be independent and stronger.** The first grade-and-retry attempt failed precisely because the grader shared the generator's model and blind spot. Self-checking by the same model gives false reassurance.
- **The judge is itself unvalidated.** Scores varied by judge model on identical answers, and the mini-judge truncated. The evaluation numbers are estimates from an LLM judge, not ground truth — they need human-agreement validation (Session 7).
- **Parsing residue.** Title-page boilerplate survives in the first chunk of each guideline; it does not harm retrieval (those chunks do not match clinical questions) but a production system would strip it more aggressively.
- **Provenance and safety.** Every answer is grounded in retrieved passages and cites its source and pages; the system refuses out-of-scope questions. Guideline version metadata should be surfaced so advice is auditable and staleness is visible. Real patient queries would require an in-institution model rather than an external API.

## 8. Conclusion

The system is a working, evaluated, grounded RAG pipeline over six KHCC oncology guidelines: 780 tagged chunks, vector retrieval that reached near-perfect contextual precision and recall, grounded answering that refuses when the answer is absent, a four-metric DeepEval suite, and an agentic grade-and-retry upgrade whose effect was measured honestly — faithfulness raised to 1.00 at the cost of relevancy and compute. As the `ai/rag` module it is the guideline-checker brain of the MDC recommender, ready to be wrapped as an agent in the Session 5 orchestrator.
