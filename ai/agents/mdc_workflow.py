"""
mdc_workflow.py — Session 5: multi-agent MDC review workflow (LangGraph).

The orchestration layer of the capstone. For a patient case it runs two
specialist agents, drafts an MDC recommendation, and HOLDS it for physician
sign-off via interrupt(). Approve -> save. Reject -> loop back with feedback.

Graph:
  START -> supervisor --(routes)--> guideline_checker -> supervisor
                                --> drug_checker      -> supervisor
                                --> recommend -> human_review
  human_review --approved--> END
               --rejected--> recommend   (revise with feedback)

Requires:  pip install "langchain>=1.0,<2.0" "langgraph>=1.0,<2.0" langchain-openai
Uses your OPENAI_API_KEY (via .env).
"""
import operator
from typing import Literal
from typing_extensions import TypedDict, Annotated

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command, interrupt
from langgraph.checkpoint.memory import InMemorySaver   # dev checkpointer; SqliteSaver for persistence

load_dotenv()
MODEL = "openai:gpt-4o-mini"


# ---------------------------------------------------------------------------
# 1. STATE — the shared memory every node reads/writes (a TypedDict).
#    'revisions' has a reducer (operator.add) so each reject loop increments it.
# ---------------------------------------------------------------------------
class MDCState(TypedDict):
    case: str                 # the patient case description (input)
    guideline_findings: str   # filled by the guideline-checker agent
    drug_findings: str        # filled by the drug/peri-op agent
    recommendation: str       # the draft MDC plan
    decision: str             # "approved" / "rejected"
    feedback: str             # physician feedback on a rejection
    revisions: Annotated[int, operator.add]


# ---------------------------------------------------------------------------
# 2. TOOLS for the specialist agents.
#    In the capstone these call the real modules: guideline_lookup -> ai/rag
#    (Session 6 RAG), drug_interaction_check -> ai/pharmacy (Session 3).
#    Kept lightweight here so the workflow runs standalone.
# ---------------------------------------------------------------------------
@tool
def guideline_lookup(topic: str) -> str:
    """Look up KHCC oncology guideline guidance for a clinical topic or cancer."""
    # Capstone: replace body with a call to the ai/rag RAG system.
    return (f"KHCC CPG note for '{topic}': confirm histology, stage, and MDC review; "
            f"follow disease-specific guideline recommendations.")


@tool
def drug_interaction_check(medications: str) -> str:
    """Check a patient's medications for peri-operative actions and interactions."""
    # Capstone: replace body with a call to the ai/pharmacy peri-op flag.
    return (f"Peri-op medication check for '{medications}': flag anticoagulants/antiplatelets "
            f"for hold/bridging and route high-risk agents to the relevant service.")


# ---------------------------------------------------------------------------
# 3. SPECIALIST AGENTS — built with create_agent (LangChain 1.0).
# ---------------------------------------------------------------------------
guideline_agent = create_agent(
    model=MODEL, tools=[guideline_lookup],
    system_prompt="You are an oncology guideline checker for an MDC. Given a case, "
                  "identify the relevant guideline recommendations. Be concise.",
)
drug_agent = create_agent(
    model=MODEL, tools=[drug_interaction_check],
    system_prompt="You are a clinical pharmacist for an MDC. Given a case, identify "
                  "peri-operative medication actions and interactions. Be concise.",
)
recommender = ChatOpenAI(model="gpt-4o-mini", temperature=0)


# ---------------------------------------------------------------------------
# 4. NODES
# ---------------------------------------------------------------------------
def supervisor(state) -> Command[Literal["guideline_checker", "drug_checker", "recommend"]]:
    """Orchestrator: route to whichever specialist hasn't run yet, then to recommend."""
    if not state.get("guideline_findings"):
        return Command(goto="guideline_checker")
    if not state.get("drug_findings"):
        return Command(goto="drug_checker")
    return Command(goto="recommend")


def guideline_checker(state) -> dict:
    res = guideline_agent.invoke(
        {"messages": [{"role": "user",
                       "content": f"Case:\n{state['case']}\n\nWhat do the guidelines advise?"}]})
    return {"guideline_findings": res["messages"][-1].content}


def drug_checker(state) -> dict:
    res = drug_agent.invoke(
        {"messages": [{"role": "user",
                       "content": f"Case:\n{state['case']}\n\nAny peri-op medication issues?"}]})
    return {"drug_findings": res["messages"][-1].content}


def recommend(state) -> dict:
    prompt = (f"Draft a concise MDC recommendation for this case.\n\n"
              f"Case: {state['case']}\n"
              f"Guideline findings: {state['guideline_findings']}\n"
              f"Drug findings: {state['drug_findings']}\n")
    if state.get("feedback"):
        prompt += f"\nRevise per physician feedback from the last review: {state['feedback']}"
    return {"recommendation": recommender.invoke(prompt).content}


def human_review(state) -> Command[Literal["recommend", "__end__"]]:
    """HOLD for physician sign-off. The graph pauses here until resumed."""
    decision = interrupt({
        "recommendation": state["recommendation"],
        "action": "Approve or reject this MDC recommendation.",
    })
    verdict = decision.get("decision") if isinstance(decision, dict) else decision
    feedback = decision.get("feedback", "") if isinstance(decision, dict) else ""
    if verdict == "approved":
        return Command(update={"decision": "approved"}, goto=END)
    return Command(update={"decision": "rejected", "feedback": feedback, "revisions": 1},
                   goto="recommend")


# ---------------------------------------------------------------------------
# 5. WIRE + COMPILE (with a checkpointer so it can pause/resume).
# ---------------------------------------------------------------------------
def build():
    b = StateGraph(MDCState)
    b.add_node("supervisor", supervisor)
    b.add_node("guideline_checker", guideline_checker)
    b.add_node("drug_checker", drug_checker)
    b.add_node("recommend", recommend)
    b.add_node("human_review", human_review)
    b.add_edge(START, "supervisor")
    b.add_edge("guideline_checker", "supervisor")
    b.add_edge("drug_checker", "supervisor")
    b.add_edge("recommend", "human_review")
    return b.compile(checkpointer=InMemorySaver())


# ---------------------------------------------------------------------------
# 6. DEMO — both paths on one case.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    graph = build()
    cfg = {"configurable": {"thread_id": "case-001"}}
    case = ("62F, differentiated thyroid cancer, 3.5 cm nodule, on warfarin for AF. "
            "Planned for surgery. MDC review requested.")

    print("=== Running agents + drafting (pauses at human review) ===")
    r = graph.invoke({"case": case, "revisions": 0}, cfg)
    print("\nDRAFT held for sign-off:\n", r["__interrupt__"][0].value["recommendation"])

    print("\n=== Physician REJECTS with feedback -> loops back ===")
    graph.invoke(Command(resume={"decision": "rejected",
                                 "feedback": "State the pre-op INR target and bridging plan."}), cfg)
    print("REVISED draft:\n", graph.get_state(cfg).values["recommendation"])

    print("\n=== Physician APPROVES ===")
    graph.invoke(Command(resume={"decision": "approved"}), cfg)
    s = graph.get_state(cfg).values
    print(f"decision: {s['decision']} | revisions: {s['revisions']}")