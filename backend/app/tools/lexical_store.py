"""Bounded lexical retrieval for memory-limited, cloud-model deployments."""
import re
from collections import deque
from functools import lru_cache
from pathlib import Path
from threading import Lock

from langchain_core.documents import Document
from pypdf import PdfReader
from app.core.config import PDF_PATH


def tokens(text):
    return set(re.findall(r'[a-z0-9]{3,}', text.lower()))


class LexicalStore:
    def __init__(self, documents=(), memory=False):
        self.documents = deque(documents, maxlen=500 if memory else 3000)
        self.lock = Lock()

    def add_texts(self, texts, metadatas):
        with self.lock:
            self.documents.extend(Document(page_content=text[:4000], metadata=metadata) for text, metadata in zip(texts, metadatas))

    def similarity_search(self, question, k=3, filter=None):
        query = tokens(question)
        with self.lock:
            candidates = [d for d in self.documents if not filter or all(d.metadata.get(key) == value for key, value in filter.items())]
        scored = [(len(query.intersection(tokens(d.page_content))), i, d) for i, d in enumerate(candidates)]
        return [Document(page_content=d.page_content, metadata=dict(d.metadata)) for score, _, d in sorted(scored, key=lambda x: (x[0], x[1]), reverse=True)[:k] if score > 0]

    def as_retriever(self, search_kwargs=None):
        store, k = self, (search_kwargs or {}).get('k', 3)
        class Retriever:
            def invoke(self, question):
                return store.similarity_search(question, k=k)
        return Retriever()


@lru_cache(maxsize=1)
def reference_store():
    documents = []
    if Path(PDF_PATH).exists():
        for index, page in enumerate(PdfReader(PDF_PATH).pages):
            text = page.extract_text() or ''
            for start in range(0, len(text), 2500):
                documents.append(Document(page_content=text[start:start + 2800], metadata={'page': index + 1}))
                if len(documents) >= 3000:
                    break
            if len(documents) >= 3000:
                break
    return LexicalStore(documents)


memory_store = LexicalStore(memory=True)
