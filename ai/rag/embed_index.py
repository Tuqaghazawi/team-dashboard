"""
embed_index.py — Step 2: turn the 780 chunks into a searchable vector index.

Concept:
  embedding  = a chunk's meaning as a list of numbers (a vector)
  ChromaDB   = a database that stores those vectors and finds the nearest ones
  retrieval  = embed the QUESTION the same way, ask Chroma for the closest chunks

Run order:
  A. build_index()  -> embeds all chunks + stores them   (uses your OpenAI key)
  B. search(...)     -> ask a question, see what comes back

The embed() and Chroma calls are given (you can't guess an API). Your part is
the test question at the bottom — pick one and watch retrieval work.
"""
import json
from pathlib import Path
import chromadb
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).parent
CHUNKS = ROOT / "guideline_chunks.jsonl"
DB_DIR = ROOT / "chroma_db"
EMBED_MODEL = "text-embedding-3-small"   # cheap, good enough for retrieval

client = OpenAI()
chroma = chromadb.PersistentClient(path=str(DB_DIR))   # saved to disk, survives restarts


def embed(texts):
    """Turn a list of texts into a list of vectors (one OpenAI call for the batch)."""
    resp = client.embeddings.create(model=EMBED_MODEL, input=texts)
    return [d.embedding for d in resp.data]


def build_index():
    rows = [json.loads(l) for l in open(CHUNKS, encoding="utf-8")]

    # fresh collection each run, so re-running never duplicates (the Part-1 lesson)
    try:
        chroma.delete_collection("guidelines")
    except Exception:
        pass
    col = chroma.create_collection("guidelines")

    B = 100                                    # embed 100 chunks per API call
    for i in range(0, len(rows), B):
        batch = rows[i:i + B]
        vectors = embed([r["text"] for r in batch])
        col.add(
            ids=[r["id"] for r in batch],
            embeddings=vectors,
            documents=[r["text"] for r in batch],
            metadatas=[{"cancer": r["cancer"], "pages": r["pages"]} for r in batch],
        )
        print(f"  indexed {i + len(batch)}/{len(rows)}")

    print(f"Done — {col.count()} chunks indexed in {DB_DIR.name}/")
    return col


def search(query, k=3):
    """Embed the question, return the k nearest chunks (lower distance = closer)."""
    col = chroma.get_collection("guidelines")
    qvec = embed([query])[0]
    res = col.query(query_embeddings=[qvec], n_results=k)
    print(f"\nQ: {query}")
    for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
        print(f"  [{meta['cancer']} · pages {meta['pages']} · distance {dist:.3f}]")
        print("   " + doc[:170].replace("\n", " ") + " ...")


if __name__ == "__main__":
    build_index()
    search("When is total thyroidectomy recommended?")
    # TODO: add a search() of your own — try a different cancer, e.g.
    # search("What is the adjuvant treatment for stage III colon cancer?")
