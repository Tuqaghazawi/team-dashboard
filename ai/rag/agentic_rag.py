"""
agentic_rag.py — Step 5: grade-and-retry (the agentic upgrade).

Baseline RAG answers in one shot. This adds a self-check loop:

  draft answer -> grader: is every claim supported by the context?
                    PASS -> return
                    FAIL -> retry WITH the grader's feedback -> re-grade

It directly targets faithfulness — the grader catches an omitted condition or
an overgeneralization, and the retry fixes it. Reuses the Step 3 pipeline.
"""
from rag_answer import retrieve, build_context, client, CHAT_MODEL, SYSTEM
GRADER_MODEL = "gpt-4o"
GRADER_SYSTEM = (
    "You are a strict clinical fact-checker. Given CONTEXT passages, a QUESTION, and a "
    "candidate ANSWER, decide whether EVERY claim in the answer is directly supported by "
    "the context — no additions, no overgeneralization, and no dropping of stated "
    "conditions. Reply on the FIRST line with exactly PASS or FAIL. If FAIL, add a second "
    "line stating precisely what to fix."
)


def draft(query, context):
    resp = client.chat.completions.create(
        model=GRADER_MODEL, temperature=0,
        messages=[{"role": "system", "content": SYSTEM},
                  {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query}"}],
    )
    return resp.choices[0].message.content


def grade(query, context, ans):
    resp = client.chat.completions.create(
        model=CHAT_MODEL, temperature=0,
        messages=[{"role": "system", "content": GRADER_SYSTEM},
                  {"role": "user",
                   "content": f"Context:\n{context}\n\nQuestion: {query}\n\nAnswer:\n{ans}"}],
    )
    text = resp.choices[0].message.content.strip()
    passed = text.upper().startswith("PASS")
    feedback = text.split("\n", 1)[1].strip() if "\n" in text else ""
    return passed, feedback


def retry(query, context, feedback):
    resp = client.chat.completions.create(
        model=CHAT_MODEL, temperature=0,
        messages=[{"role": "system", "content": SYSTEM},
                  {"role": "user",
                   "content": f"Context:\n{context}\n\nQuestion: {query}\n\n"
                              f"Your previous answer had this problem: {feedback}\n"
                              f"Rewrite it, fixing the problem and staying strictly grounded "
                              f"in the context."}],
    )
    return resp.choices[0].message.content


def answer_agentic(query, k=4, max_retries=2, verbose=True):
    chunks = retrieve(query, k)
    context = build_context(chunks)
    ans = draft(query, context)
    for i in range(max_retries):
        passed, feedback = grade(query, context, ans)
        if verbose:
            print(f"   grade {i+1}: {'PASS' if passed else 'FAIL - ' + feedback[:90]}")
        if passed:
            break
        ans = retry(query, context, feedback)
    return ans, chunks


if __name__ == "__main__":
    # The pancreatic question scored 0.50 faithfulness in the baseline -
    # watch the grader catch the omission and the retry fix it.
    q = "When is histological proof of malignancy mandatory in pancreatic cancer?"
    print(f"Q: {q}")
    final, _ = answer_agentic(q)
    print("\nFINAL ANSWER:\n", final)
