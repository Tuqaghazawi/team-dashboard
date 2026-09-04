# Session 5 — Multi-Agent Clinical Workflow with Human Approval

**Project:** MDC recommendation workflow — the orchestration layer of the team-dashboard capstone, built in LangGraph as the `ai/agents` module.
**What it does:** for a patient case, two specialist agents (a guideline checker and a peri-op drug checker) contribute findings; a recommend node drafts an MDC plan; the plan is held for physician sign-off via `interrupt()`. Approval saves it; rejection loops back to revise with the physician's feedback.

---

## 1. Architecture

```
START -> supervisor --routes--> guideline_checker -> supervisor
                            --> drug_checker      -> supervisor
                            --> recommend -> human_review
  human_review --approved--> END
               --rejected--> recommend        (revise with feedback)
```

- **State** is a `TypedDict` shared across all nodes. `revisions` carries an `operator.add` reducer so each rejection increments it rather than overwriting.
- **Two specialist agents** are built with `create_agent` (LangChain 1.0), each with its own tool. In the capstone the guideline tool calls the `ai/rag` RAG system (Session 6) and the drug tool calls the `ai/pharmacy` peri-op flag (Session 3).
- **The supervisor** is an orchestrator node that routes to whichever specialist has not run yet, then to `recommend` — a simple, inspectable routing policy.
- **`human_review`** calls `interrupt()`, which pauses the entire graph and surfaces the draft. A `MemorySaver` checkpointer saves the full state under a `thread_id`, so the run can be resumed later with `Command(resume=...)`.

## 2. Demonstration

Running one case (62F, differentiated thyroid cancer, on warfarin, for surgery):

- The workflow ran both specialists, drafted a recommendation, and **paused** — "draft held for sign-off."
- The physician **rejected** with the feedback *"state the pre-op INR target and bridging plan."* The graph looped back to `recommend`, which regenerated the draft **with a new explicit INR target and bridging entry** — the feedback visibly changed the output.
- The physician then **approved**; the run completed with `decision = approved` and `revisions = 1` (the reducer counted the single loop).

All five required features were exercised: multi-agent contribution, supervisor routing, `interrupt()` human approval, the approval path, and the rejection-with-feedback loop.

## 3. Comparison to the Session 3 manual tool-calling loop

I built both a hand-written tool-calling pipeline (Session 3, the pharmacy text-to-SQL and peri-op flag) and this LangGraph workflow, so the comparison is direct.

| Axis | Session 3 — manual loop | Session 5 — LangGraph |
|---|---|---|
| **Lines of code** | Less scaffolding; I wrote the control flow directly as plain Python calls. Fine for a single, linear task. | More scaffolding (state schema, nodes, edges, compile), but the control flow — loops, routing, pause/resume — is declared once and handled by the engine rather than hand-managed. |
| **Persistence** | None. State lived in local variables and was lost when the script ended; a pause for human input was not possible. | The checkpointer saves the entire state at every step under a `thread_id`. The graph can pause at `interrupt()` and resume minutes or days later, surviving process restart. |
| **Auditability** | I would have to add my own logging to reconstruct what happened. | Every super-step is checkpointed and the full state is inspectable at any point (`get_state`), including the number of revisions and the feedback that drove each one — an audit trail by construction. |
| **Safety** | Human approval, if any, was a plain `if` in a script — not resumable, not enforced. | `interrupt()` is a real, resumable human gate: the workflow physically cannot proceed past the draft until a physician resumes it. Rejection is a first-class path that returns control for revision. |

## 4. When to reach for `create_agent` vs a full `StateGraph` at KHCC

- **Use `create_agent`** for a single-purpose agent: one job, a few tools, take input and return a result. The standalone guideline-checker or the drug-checker on their own fit this — `create_agent` handles the tool-calling loop so I do not have to. It is the right tool for a bounded task and keeps the code small.
- **Use a full `StateGraph`** when the task needs custom control flow that a single agent cannot express: routing between multiple agents, loops, a human-in-the-loop pause with resume, or persistent state across invocations. The MDC workflow needs all four — a supervisor choosing among specialists, a revision loop, and a physician approval gate — so it must be a graph, not a single agent.

A practical rule for the dashboard: build each specialist as a `create_agent` unit, and use one `StateGraph` to orchestrate them with the human-approval gate. The two layers compose — the agents are the workers, the graph is the clinical workflow around them.

## 5. Critical analysis

- **The human gate is the point, not a formality.** In the demo the model produced a specific pre-op INR target that was its own addition rather than a cited guideline value. This is exactly what the `interrupt()` gate exists to catch: the workflow surfaces a draft for a clinician to verify and correct, and records nothing until a physician approves. The system is designed to assist the MDC, never to decide for it.
- **Grounding belongs in the tools.** The specialist tools are lightweight here; wiring them to the real `ai/rag` and `ai/pharmacy` modules is what will make the findings source-backed rather than model-generated. The orchestration is complete; the grounding is the integration step.
- **Checkpointer choice matters for deployment.** `MemorySaver` is dev-only — state is lost on restart. A real deployment needs `SqliteSaver` (single-user) or `PostgresSaver` so a paused case survives until the physician returns.
- **Idempotency around the interrupt.** Because a resumed node re-runs from its first line, any real side effect (writing the approved recommendation to the patient record) must sit after the approval and use upsert semantics, not run before the interrupt.

## 6. Conclusion

The workflow is a working multi-agent MDC recommender with a resumable physician-approval gate: a typed state with a reducer, two `create_agent` specialists, a supervisor router, a recommend node, and an `interrupt()` human-in-the-loop step, all persisted by a checkpointer and demonstrated across both the approval and rejection-with-feedback paths. As the `ai/agents` module it is the orchestration layer that ties the RAG guideline brain (Session 6) and the pharmacy checker (Session 3) into a single clinical workflow, with the physician kept firmly in the loop.
