import sys
from pathlib import Path

from app.rag.chunker import chunk_pages
from app.rag.parser import extract_pages
from app.rag.vectorstore import VectorStore

pdf = Path(sys.argv[1])
store = VectorStore()

chunks = chunk_pages(extract_pages(pdf))
store.add_chunks(pdf.stem, chunks)
print(f"Indexed {len(chunks)} chunks from {pdf.name}\n")

while True:
    question = input("Question (or 'quit'): ").strip()
    if question.lower() in ("quit", "exit", ""):
        break
    for r in store.search(question, k=3):
        print(f"\n  score {r.score:.2f} | page {r.page}")
        print(f"  {r.text[:200]}...")
    print()