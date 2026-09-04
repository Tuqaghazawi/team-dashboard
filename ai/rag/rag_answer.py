"""
rag_answer.py — Step 3: answer a question using ONLY the retrieved chunks.

  question -> retrieve top chunks -> [ LLM: answer ONLY from context ] -> cited answer

Reuses the index built in Step 2 (embed_index.py).
"""
from embed_index import client, embed, chroma

CHAT_MODEL = "gpt-4o-mini"

# Improved "answer only from context" prompt. Changes from v1:
#  - lead with the direct recommendation (fixes low relevancy)
#  - every claim must be grounded in a passage (fixes low faithfulness)
#  - cite using the ACTUAL source label shown, not a placeholder
SYSTEM = (
    "You are a clinical guideline assistant for KHCC. Follow these rules strictly:\n"
    "1. Answer ONLY from the numbered context passages. Use no outside medical knowledge.\n"
    "2. Lead with the direct answer to the question asked; be concise.\n"
    "3. Every statement must be supported by a passage. If the answer is not in the "
    "context, reply exactly: 'Not found in the provided guidelines.'\n"
    "4. Cite the passage(s) you used with their exact label as shown, e.g. "
    "[Thyroid, pages 1-41]. Never output the literal words 'cancer' or 'pages' as a "
    "placeholder."
)


def retrieve(query, k=4):
    col = chroma.get_collection("guidelines")
    qvec = embed([query])[0]
    res = col.query(query_embeddings=[qvec], n_results=k)
    return [{"text": d, "cancer": m["cancer"], "pages": m["pages"]}
            for d, m in zip(res["documents"][0], res["metadatas"][0])]


def build_context(chunks):
    return "\n\n".join(
        f"[Source {i} - {c['cancer']}, pages {c['pages']}]\n{c['text']}"
        for i, c in enumerate(chunks, 1)
    )


def answer(query, k=4):
    chunks = retrieve(query, k)
    context = build_context(chunks)
    resp = client.chat.completions.create(
        model=CHAT_MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query}"},
        ],
    )
    print(f"\nQ: {query}\n")
    print(resp.choices[0].message.content)
    print("\n--- sources retrieved ---")
    for c in chunks:
        print(f"  {c['cancer']} · pages {c['pages']}")


if __name__ == "__main__":
    answer("When is total thyroidectomy recommended?")
    answer("What is the recommended treatment for melanoma?")
