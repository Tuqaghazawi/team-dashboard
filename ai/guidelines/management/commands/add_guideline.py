"""Add a guideline PDF to the retrieval index.

    python manage.py add_guideline --pdf data/guidelines/nccn_esophageal.pdf \
        --label "Esophageal (NCCN)"

Use this for diseases the KHCC set does not cover — hepatobiliary and
oesophageal, where NCCN is the source the team uses instead.

The label matters. It is what gets cited under every answer, so it must say
which guideline and whose: "Esophageal (NCCN)" and not "Esophageal". It is also
what the coverage check matches on, so it must contain the disease word.

Licensing: NCCN guidelines are copyrighted. Keep the PDFs in data/guidelines/,
which is git-ignored, and never commit them. Only the extracted chunks and their
embeddings enter the index, and the index is git-ignored too.
"""

import json
import sys
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

RAG_DIR = Path(__file__).resolve().parents[3] / "rag"


class Command(BaseCommand):
    help = "Chunk a guideline PDF and add it to the ChromaDB retrieval index."

    def add_arguments(self, parser):
        parser.add_argument("--pdf", required=True, help="Path to the guideline PDF.")
        parser.add_argument(
            "--label", required=True,
            help='Citation label, e.g. "Esophageal (NCCN)". Must name the disease.',
        )
        parser.add_argument("--start", type=int, default=1, help="First page (1-based).")
        parser.add_argument("--end", type=int, default=None, help="Last page.")
        parser.add_argument(
            "--replace", action="store_true",
            help="Remove any existing chunks with this label first.",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Chunk and report, but do not embed or write to the index.",
        )

    def handle(self, *args, **options):
        pdf = Path(options["pdf"])
        if not pdf.exists():
            raise CommandError(f"No PDF at {pdf}")

        label = options["label"].strip()
        if not label:
            raise CommandError("A label is required.")

        chunker, embed_index = self._rag_modules()
        chunks, pages = self._chunk(pdf, chunker, options["start"], options["end"])
        if not chunks:
            raise CommandError("No text extracted — is this a scanned PDF needing OCR?")

        self.stdout.write(
            f"{pdf.name}: {pages} page(s) -> {len(chunks)} chunk(s), labelled '{label}'"
        )
        self.stdout.write(f"  first chunk: {chunks[0][:160]}...")

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry run — nothing written."))
            return

        collection = embed_index.chroma.get_or_create_collection("guidelines")

        if options["replace"]:
            existing = collection.get(where={"cancer": label})
            if existing["ids"]:
                collection.delete(ids=existing["ids"])
                self.stdout.write(f"  removed {len(existing['ids'])} existing chunk(s)")

        page_range = f"{options['start']}-{options['end'] or pages}"
        ids = [f"{_slug(label)}-{i}" for i in range(len(chunks))]
        metadatas = [{"cancer": label, "pages": page_range} for _ in chunks]

        self.stdout.write("  embedding (this calls the OpenAI API)...")
        vectors = []
        for batch_start in range(0, len(chunks), 64):
            batch = chunks[batch_start:batch_start + 64]
            vectors.extend(embed_index.embed(batch))

        collection.add(ids=ids, documents=chunks, embeddings=vectors, metadatas=metadatas)

        # Keep the chunk file in step, so the index can be rebuilt from scratch.
        self._append_chunks(chunks, label, page_range)

        self.stdout.write(self.style.SUCCESS(f"Added {len(chunks)} chunk(s) as '{label}'."))
        self.stdout.write(
            "  The coverage check reads the index directly, so this guideline is "
            "now offered to matching patients."
        )

    # --- helpers ---

    def _rag_modules(self):
        """The Session 6 chunker and index, which expect to run from their folder."""
        if str(RAG_DIR) not in sys.path:
            sys.path.insert(0, str(RAG_DIR))
        try:
            import chunk_guidelines
            import embed_index
        except Exception as exc:
            raise CommandError(
                f"Could not load the RAG modules ({exc}). Check OPENAI_API_KEY."
            ) from exc
        return chunk_guidelines, embed_index

    def _chunk(self, pdf, chunker, start, end):
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise CommandError("pypdf is required to read the PDF.") from exc

        reader = PdfReader(str(pdf))
        last = end or len(reader.pages)
        if start < 1 or last > len(reader.pages) or start > last:
            raise CommandError(
                f"Page range {start}-{last} is outside this {len(reader.pages)}-page PDF."
            )

        # Reuse the Session 6 cleaning and packing, so these chunks look like the
        # existing ones and retrieval behaves the same.
        text = "\n".join(
            chunker.clean(reader.pages[page - 1].extract_text() or "")
            for page in range(start, last + 1)
        )
        return chunker.chunk_text(text), last - start + 1

    def _append_chunks(self, chunks, label, page_range):
        path = RAG_DIR / "guideline_chunks.jsonl"
        existing = 0
        if path.exists():
            with open(path, encoding="utf-8") as handle:
                existing = sum(1 for _ in handle)
        with open(path, "a", encoding="utf-8") as handle:
            for i, chunk in enumerate(chunks):
                handle.write(json.dumps({
                    "id": f"c{existing + i}", "cancer": label,
                    "pages": page_range, "text": chunk,
                }) + "\n")


def _slug(label):
    return "".join(c.lower() if c.isalnum() else "-" for c in label).strip("-")
