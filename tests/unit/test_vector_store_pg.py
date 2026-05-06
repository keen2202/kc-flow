"""Unit tests for PGVectorStore (mocked asyncpg)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.services.rag.vector_store import PGVectorStore, Document, SearchResult


@pytest.fixture
def mock_pool():
    """Mock asyncpg connection pool."""
    pool = MagicMock()
    conn = AsyncMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    pool.acquire.return_value = cm
    return pool, conn


@pytest.mark.asyncio
async def test_pgvector_ensure_table(mock_pool):
    pool, conn = mock_pool
    store = PGVectorStore("postgresql://localhost/test", embedding_dim=128)
    store._pool = pool

    await store.ensure_table()

    assert conn.execute.call_count == 2
    sql = conn.execute.call_args_list[0][0][0]
    assert "CREATE TABLE" in sql
    assert "documents" in sql
    assert "vector(128)" in sql


@pytest.mark.asyncio
async def test_pgvector_add(mock_pool):
    pool, conn = mock_pool
    store = PGVectorStore("postgresql://localhost/test", embedding_dim=128)
    store._pool = pool

    docs = [
        Document(doc_id="d1", content="hello", embedding=[0.1] * 128, metadata={"key": "val"}),
        Document(doc_id="d2", content="world", embedding=[0.2] * 128),
    ]

    ids = await store.add(docs)

    assert ids == ["d1", "d2"]
    conn.executemany.assert_called_once()


@pytest.mark.asyncio
async def test_pgvector_search(mock_pool):
    pool, conn = mock_pool
    conn.fetch = AsyncMock(return_value=[
        {"id": "d1", "content": "hello", "distance": 0.9, "metadata": {"key": "val"}},
    ])
    store = PGVectorStore("postgresql://localhost/test", embedding_dim=128)
    store._pool = pool

    results = await store.search([0.1] * 128, top_k=5)

    assert len(results) == 1
    assert results[0].doc_id == "d1"
    assert results[0].score == pytest.approx(0.9)  # 1 - distance


@pytest.mark.asyncio
async def test_pgvector_search_with_filters(mock_pool):
    pool, conn = mock_pool
    conn.fetch = AsyncMock(return_value=[])
    store = PGVectorStore("postgresql://localhost/test", embedding_dim=128)
    store._pool = pool

    await store.search([0.1] * 128, top_k=5, filters={"category": "test"})

    sql = conn.fetch.call_args[0][0]
    assert "@>" in sql or "metadata" in sql


@pytest.mark.asyncio
async def test_pgvector_delete(mock_pool):
    pool, conn = mock_pool
    conn.fetchval = AsyncMock(return_value=2)
    store = PGVectorStore("postgresql://localhost/test", embedding_dim=128)
    store._pool = pool

    count = await store.delete(["d1", "d2"])

    assert count == 2


@pytest.mark.asyncio
async def test_pgvector_get(mock_pool):
    pool, conn = mock_pool
    conn.fetch = AsyncMock(return_value=[
        {"id": "d1", "content": "hello", "embedding": [0.1] * 128, "metadata": {}},
    ])
    store = PGVectorStore("postgresql://localhost/test", embedding_dim=128)
    store._pool = pool

    docs = await store.get(["d1"])

    assert len(docs) == 1
    assert docs[0].doc_id == "d1"


@pytest.mark.asyncio
async def test_pgvector_count(mock_pool):
    pool, conn = mock_pool
    conn.fetchval = AsyncMock(return_value=42)
    store = PGVectorStore("postgresql://localhost/test", embedding_dim=128)
    store._pool = pool

    count = await store.count()

    assert count == 42


@pytest.mark.asyncio
async def test_pgvector_count_with_filters(mock_pool):
    pool, conn = mock_pool
    conn.fetchval = AsyncMock(return_value=5)
    store = PGVectorStore("postgresql://localhost/test", embedding_dim=128)
    store._pool = pool

    count = await store.count(filters={"category": "test"})

    assert count == 5
    sql = conn.fetchval.call_args[0][0]
    assert "@>" in sql or "metadata" in sql
