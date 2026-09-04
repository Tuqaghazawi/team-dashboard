"""
chunk_guidelines.py — parse the merged KHCC guideline PDF into clean,
tagged chunks for RAG.

Chunking strategy (this is the 'justified chunking' the assignment wants):
  - Split the 280-page merged PDF into its 6 disease guidelines by page range.
  - Strip repeated boilerplate (confidentiality banners, page footers, CPG
    headers) so chunks hold clinical content, not letterhead.
  - Pack text into ~1000-character chunks on paragraph boundaries, with ~150
    chars of overlap so a recommendation split across a boundary is still
    retrievable from either chunk.
  - Tag every chunk with its cancer + source page -> retrieval can cite, and
    a query about one cancer won't be answered from another's text.
"""
import json, re
from pathlib import Path
from pypdf import PdfReader

PDF = Path("/mnt/user-data/uploads/ilovepdf_merged.pdf")
OUT = Path(__file__).parent / "guideline_chunks.jsonl"

# 1-based page where each guideline starts, + the doc end
SECTIONS = [(1,"Thyroid"),(42,"Breast"),(113,"Colon"),
            (177,"Gastric"),(210,"Pancreatic"),(233,"Rectal")]
END = 280

TARGET, OVERLAP = 1000, 150

BOILERPLATE = re.compile(
    r"(Confidential Information|P&P|Documents Control UNIT|Approved By|"
    r"CPG Number|Date Originated|Due Revision Date|Originating Entity|"
    r"Clinical Practice Guidelines Manual|Page \d+ of \d+|^\s*\d+\s*$)", re.I)

def clean(text):
    keep=[]
    for line in text.splitlines():
        s=line.strip()
        if not s: continue
        if BOILERPLATE.search(s): continue
        keep.append(s)
    return "\n".join(keep)

def chunk_text(text):
    paras=[p.strip() for p in re.split(r"\n(?=\S)", text) if p.strip()]
    chunks, buf = [], ""
    for p in paras:
        if len(buf)+len(p)+1 <= TARGET:
            buf = (buf+"\n"+p).strip()
        else:
            if buf: chunks.append(buf)
            buf = (buf[-OVERLAP:]+"\n"+p).strip() if buf else p
    if buf: chunks.append(buf)
    return chunks

def main():
    r = PdfReader(str(PDF))
    bounds = SECTIONS + [(END+1,"_end")]
    rows=[]
    cid=0
    for i,(start,cancer) in enumerate(SECTIONS):
        end = bounds[i+1][0]-1
        section=""
        for pg in range(start, end+1):
            section += "\n" + clean(r.pages[pg-1].extract_text() or "")
        for ch in chunk_text(section):
            if len(ch) < 60:      # drop tiny fragments
                continue
            cid+=1
            rows.append({"id":f"c{cid}","cancer":cancer,
                         "pages":f"{start}-{end}","text":ch})
    with open(OUT,"w",encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row,ensure_ascii=False)+"\n")

    from collections import Counter
    per=Counter(r["cancer"] for r in rows)
    avg=sum(len(r["text"]) for r in rows)//len(rows)
    print(f"Wrote {len(rows)} chunks -> {OUT.name}  (avg {avg} chars)")
    for c,_ in SECTIONS:
        pass
    for cancer in [s[1] for s in SECTIONS]:
        print(f"  {cancer:12} {per[cancer]:4} chunks")

if __name__=="__main__":
    main()
