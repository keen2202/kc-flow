"""Unit tests for HybridSearcher."""

import pytest
from unittest.mock import AsyncMock
from src.services.rag.vector_store import Document, SearchResult, VectorStore
from src.services.rag.hybrid_searcher import HybridSearcher


class MockVectorStore(VectorStore):
    """Minimal mock vector store for testing."""

    def __init__(self, search_results: list[SearchResult] | None = None):
        self._search_results = search_results or []
        self._documents: dict[str, Document] = {}

    async def add(self, documents: list[Document]) -> list[str]:
        for doc in documents:
            self._documents[doc.doc_id] = doc
        return [doc.doc_id for doc in documents]

    async def search(self, query_embedding, top_k=5, filters=None):
        return self._search_results[:top_k]

    async def delete(self, doc_ids):
        count = sum(1 for d in doc_ids if d in self._documents)
        for d in doc_ids:
            self._documents.pop(d, None)
        return count

    async def get(self, doc_ids):
        return [self._documents[d] for d in doc_ids if d in self._documents]

    async def count(self, filters=None):
        return len(self._documents)


@pytest.mark.asyncio
async def test_hybrid_searcher_add_documents():
    store = MockVectorStore()
    searcher = HybridSearcher(store, alpha=0.7)

    docs = [
        Document(doc_id="d1", content="the quick brown fox", embedding=[0.1] * 10),
        Document(doc_id="d2", content="the lazy dog", embedding=[0.2] * 10),
    ]
    await searcher.add_documents(docs)

    assert len(searcher._documents) == 2
    assert searcher._bm25 is not None


@pytest.mark.asyncio
async def test_hybrid_searcher_remove_documents():
    store = MockVectorStore()
    searcher = HybridSearcher(store, alpha=0.7)

    docs = [
        Document(doc_id="d1", content="the quick brown fox", embedding=[0.1] * 10),
        Document(doc_id="d2", content="the lazy dog", embedding=[0.2] * 10),
    ]
    await searcher.add_documents(docs)
    await searcher.remove_documents(["d1"])

    assert len(searcher._documents) == 1
    assert "d1" not in searcher._documents


@pytest.mark.asyncio
async def test_hybrid_searcher_fuses_scores():
    # Vector search returns d1 first, BM25 should return d2 first for "lazy dog"
    vector_results = [
        SearchResult(doc_id="d1", content="the quick brown fox", score=0.9),
        SearchResult(doc_id="d2", content="the lazy dog", score=0.7),
    ]
    store = MockVectorStore(search_results=vector_results)
    searcher = HybridSearcher(store, alpha=0.7)

    docs = [
        Document(doc_id="d1", content="the quick brown fox", embedding=[0.1] * 10),
        Document(doc_id="d2", content="the lazy dog", embedding=[0.2] * 10),
    ]
    await searcher.add_documents(docs)

    results = await searcher.search(
        query_embedding=[0.15] * 10,
        query_text="lazy dog",
        top_k=2,
    )

    assert len(results) == 2
    # Both should have scores > 0 from RRF fusion
    assert all(r.score > 0 for r in results)


@pytest.mark.asyncio
async def test_hybrid_searcher_alpha_weighting():
    # With alpha=1.0, should be pure vector search
    vector_results = [
        SearchResult(doc_id="d1", content="hello world", score=0.9),
    ]
    store = MockVectorStore(search_results=vector_results)
    searcher = HybridSearcher(store, alpha=1.0)

    docs = [
        Document(doc_id="d1", content="hello world", embedding=[0.1] * 10),
    ]
    await searcher.add_documents(docs)

    results = await searcher.search(
        query_embedding=[0.1] * 10,
        query_text="hello",
        top_k=1,
    )

    assert len(results) == 1
    assert results[0].doc_id == "d1"


@pytest.mark.asyncio
async def test_hybrid_searcher_empty_query():
    store = MockVectorStore()
    searcher = HybridSearcher(store, alpha=0.7)

    results = await searcher.search(
        query_embedding=[],
        query_text="",
        top_k=5,
    )

    assert results == []
