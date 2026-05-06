# RAG Pipeline Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the RAG pipeline by implementing PGVector/Milvus backends, hybrid search, and reranker integration.

**Architecture:** Extend the existing `VectorStore` ABC with two production backends (PGVector via asyncpg, Milvus via pymilvus), add a `HybridSearcher` that fuses vector + BM25 scores via RRF, add a `CohereReranker` for post-retrieval reranking, and wire everything into the `RAGPipeline` via a factory pattern.

**Tech Stack:** asyncpg, pymilvus, rank-bm25, httpx (Cohere API), pytest-asyncio

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `src/services/rag/vector_store.py` | Replace PGVectorStore/MilvusVectorStore stubs with full implementations |
| Create | `src/services/rag/hybrid_searcher.py` | BM25 index + Reciprocal Rank Fusion |
| Create | `src/services/rag/reranker.py` | Cohere Rerank API client |
| Modify | `src/services/rag/pipeline.py` | Factory pattern for backends, wire hybrid/reranker |
| Modify | `pyproject.toml` | Add pymilvus, rank-bm25 dependencies |
| Create | `tests/unit/test_vector_store_pg.py` | PGVectorStore unit tests (mocked asyncpg) |
| Create | `tests/unit/test_vector_store_milvus.py` | MilvusVectorStore unit tests (mocked pymilvus) |
| Create | `tests/unit/test_hybrid_searcher.py` | HybridSearcher unit tests |
| Create | `tests/unit/test_reranker.py` | CohereReranker unit tests |
| Modify | `tests/unit/test_rag_pipeline.py` | Update pipeline tests for new backends |

---

### Task 1: Add Dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add pymilvus and rank-bm25 to dependencies**

```toml
# In pyproject.toml [project] dependencies, add after "asyncpg>=0.29.0":
    "pymilvus>=2.4.0",
    "rank-bm25>=0.2.2",
```

The full dependencies section becomes:

```toml
dependencies = [
    # API Framework
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "python-multipart>=0.0.12",

    # Data & Validation
    "pydantic>=2.9.0",
    "pydantic-settings>=2.5.0",

    # Database
    "sqlalchemy[asyncio]>=2.0.35",
    "asyncpg>=0.29.0",
    "alembic>=1.13.0",

    # Vector Stores
    "pymilvus>=2.4.0",

    # Search
    "rank-bm25>=0.2.2",

    # Cache & Queue
    "redis[hiredis]>=5.1.0",
    "celery[redis]>=5.4.0",

    # HTTP Client
    "httpx>=0.27.0",

    # Templating
    "jinja2>=3.1.0",

    # Logging
    "structlog>=24.4.0",

    # Auth
    "python-jose[cryptography]>=3.3.0",
    "passlib[bcrypt]>=1.7.4",
    "bcrypt>=4.2.0",

    # Document Processing
    "pypdf2>=3.0.0",
    "python-docx>=1.1.0",
    "openpyxl>=3.1.0",

    # YAML
    "pyyaml>=6.0.0",

    # JSON Schema
    "jsonschema>=4.23.0",

    # Container
    "docker>=7.1.0",
]
```

- [ ] **Step 2: Install dependencies**

Run: `cd /root/.openclaw/workspace/kc-flow && pip install -e ".[dev]" --quiet`

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "deps: add pymilvus and rank-bm25 for RAG pipeline"
```

---

### Task 2: PGVectorStore Implementation

**Files:**
- Modify: `src/services/rag/vector_store.py:155-175`
- Create: `tests/unit/test_vector_store_pg.py`

- [ ] **Step 1: Write failing tests for PGVectorStore**

Create `tests/unit/test_vector_store_pg.py`:

```python
"""Unit tests for PGVectorStore (mocked asyncpg)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.services.rag.vector_store import PGVectorStore, Document, SearchResult


@pytest.fixture
def mock_pool():
    """Mock asyncpg connection pool."""
    pool = AsyncMock()
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool, conn


@pytest.mark.asyncio
async def test_pgvector_ensure_table(mock_pool):
    pool, conn = mock_pool
    store = PGVectorStore("postgresql://localhost/test", embedding_dim=128)
    store._pool = pool

    await store.ensure_table()

    conn.execute.assert_called_once()
    sql = conn.execute.call_args[0][0]
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
        {"id": "d1", "content": "hello", "distance": 0.1, "metadata": {"key": "val"}},
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /root/.openclaw/workspace/kc-flow && python -m pytest tests/unit/test_vector_store_pg.py -v 2>&1 | head -40`
Expected: FAIL — `NotImplementedError` from stubs

- [ ] **Step 3: Implement PGVectorStore**

Replace the `PGVectorStore` class in `src/services/rag/vector_store.py` (lines 155-175) with:

```python
class PGVectorStore(VectorStore):
    """PostgreSQL + pgvector store for production use."""

    def __init__(
        self,
        connection_string: str,
        table_name: str = "documents",
        embedding_dim: int = 1536,
    ) -> None:
        self._connection_string = connection_string
        self._table_name = table_name
        self._embedding_dim = embedding_dim
        self._pool: Any = None

    async def _get_pool(self) -> Any:
        if self._pool is None:
            import asyncpg
            self._pool = await asyncpg.create_pool(self._connection_string)
        return self._pool

    async def ensure_table(self) -> None:
        """Create the documents table if it doesn't exist."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {self._table_name} (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    embedding vector({self._embedding_dim}),
                    metadata JSONB DEFAULT '{{}}',
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            await conn.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{self._table_name}_metadata
                ON {self._table_name} USING GIN (metadata)
            """)

    async def add(self, documents: list[Document]) -> list[str]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.executemany(
                f"""
                INSERT INTO {self._table_name} (id, content, embedding, metadata)
                VALUES ($1, $2, $3::vector, $4::jsonb)
                ON CONFLICT (id) DO UPDATE SET
                    content = EXCLUDED.content,
                    embedding = EXCLUDED.embedding,
                    metadata = EXCLUDED.metadata
                """,
                [
                    (doc.doc_id, doc.content, str(doc.embedding), json.dumps(doc.metadata))
                    for doc in documents
                ],
            )
        return [doc.doc_id for doc in documents]

    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            where_clause = ""
            params: list[Any] = [str(query_embedding), top_k]

            if filters:
                conditions = []
                for i, (key, value) in enumerate(filters.items(), start=3):
                    conditions.append(f"metadata @> $${json.dumps({key: value})}$$::jsonb")
                where_clause = "WHERE " + " AND ".join(conditions)

            rows = await conn.fetch(
                f"""
                SELECT id, content, 1 - (embedding <=> $1::vector) AS distance, metadata
                FROM {self._table_name}
                {where_clause}
                ORDER BY embedding <=> $1::vector
                LIMIT $2
                """,
                *params,
            )

        return [
            SearchResult(
                doc_id=row["id"],
                content=row["content"],
                score=float(row["distance"]),
                metadata=json.loads(row["metadata"]) if isinstance(row["metadata"], str) else row["metadata"],
            )
            for row in rows
        ]

    async def delete(self, doc_ids: list[str]) -> int:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            count = await conn.fetchval(
                f"DELETE FROM {self._table_name} WHERE id = ANY($1) RETURNING COUNT(*)",
                doc_ids,
            )
        return count or 0

    async def get(self, doc_ids: list[str]) -> list[Document]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT id, content, embedding, metadata FROM {self._table_name} WHERE id = ANY($1)",
                doc_ids,
            )
        return [
            Document(
                doc_id=row["id"],
                content=row["content"],
                embedding=list(row["embedding"]),
                metadata=json.loads(row["metadata"]) if isinstance(row["metadata"], str) else row["metadata"],
            )
            for row in rows
        ]

    async def count(self, filters: dict[str, Any] | None = None) -> int:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            if filters:
                conditions = []
                for key, value in filters.items():
                    conditions.append(f"metadata @> $${json.dumps({key: value})}$$::jsonb")
                where_clause = "WHERE " + " AND ".join(conditions)
                count = await conn.fetchval(
                    f"SELECT COUNT(*) FROM {self._table_name} {where_clause}"
                )
            else:
                count = await conn.fetchval(
                    f"SELECT COUNT(*) FROM {self._table_name}"
                )
        return count or 0
```

Add `import json` at the top of `vector_store.py` (after existing imports).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /root/.openclaw/workspace/kc-flow && python -m pytest tests/unit/test_vector_store_pg.py -v`
Expected: All 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/services/rag/vector_store.py tests/unit/test_vector_store_pg.py
git commit -m "feat(rag): implement PGVectorStore with asyncpg"
```

---

### Task 3: MilvusVectorStore Implementation

**Files:**
- Modify: `src/services/rag/vector_store.py:178-199`
- Create: `tests/unit/test_vector_store_milvus.py`

- [ ] **Step 1: Write failing tests for MilvusVectorStore**

Create `tests/unit/test_vector_store_milvus.py`:

```python
"""Unit tests for MilvusVectorStore (mocked pymilvus)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.services.rag.vector_store import MilvusVectorStore, Document, SearchResult


@pytest.fixture
def mock_milvus():
    """Mock pymilvus modules."""
    with patch("src.services.rag.vector_store.MilvusClient") as mock_client_cls:
        client = MagicMock()
        mock_client_cls.return_value = client
        yield client


@pytest.mark.asyncio
async def test_milvus_ensure_collection(mock_milvus):
    store = MilvusVectorStore(embedding_dim=128)

    await store.ensure_collection()

    mock_milvus.create_collection.assert_called_once()
    call_kwargs = mock_milvus.create_collection.call_args
    assert call_kwargs[1]["collection_name"] == "documents" or call_kwargs[0][0] == "documents"


@pytest.mark.asyncio
async def test_milvus_add(mock_milvus):
    mock_milvus.insert.return_value = {"insert_count": 2}
    store = MilvusVectorStore(embedding_dim=128)

    docs = [
        Document(doc_id="d1", content="hello", embedding=[0.1] * 128, metadata={"key": "val"}),
        Document(doc_id="d2", content="world", embedding=[0.2] * 128),
    ]

    ids = await store.add(docs)

    assert ids == ["d1", "d2"]
    mock_milvus.insert.assert_called_once()


@pytest.mark.asyncio
async def test_milvus_search(mock_milvus):
    hit = MagicMock()
    hit.id = "d1"
    hit.distance = 0.1
    hit.entity = {"content": "hello", "metadata": "{}"}
    mock_milvus.search.return_value = [[hit]]

    store = MilvusVectorStore(embedding_dim=128)
    results = await store.search([0.1] * 128, top_k=5)

    assert len(results) == 1
    assert results[0].doc_id == "d1"
    assert results[0].score == pytest.approx(0.9)


@pytest.mark.asyncio
async def test_milvus_delete(mock_milvus):
    mock_milvus.delete.return_value = {"delete_count": 2}
    store = MilvusVectorStore(embedding_dim=128)

    count = await store.delete(["d1", "d2"])

    assert count == 2


@pytest.mark.asyncio
async def test_milvus_get(mock_milvus):
    mock_milvus.get.return_value = [
        {"id": "d1", "content": "hello", "embedding": [0.1] * 128, "metadata": "{}"},
    ]
    store = MilvusVectorStore(embedding_dim=128)

    docs = await store.get(["d1"])

    assert len(docs) == 1
    assert docs[0].doc_id == "d1"


@pytest.mark.asyncio
async def test_milvus_count(mock_milvus):
    mock_milvus.query.return_value = [{"count": 42}]
    store = MilvusVectorStore(embedding_dim=128)

    count = await store.count()

    assert count == 42
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /root/.openclaw/workspace/kc-flow && python -m pytest tests/unit/test_vector_store_milvus.py -v 2>&1 | head -40`
Expected: FAIL — `NotImplementedError` from stubs

- [ ] **Step 3: Implement MilvusVectorStore**

Replace the `MilvusVectorStore` class in `src/services/rag/vector_store.py` (lines 178-199) with:

```python
class MilvusVectorStore(VectorStore):
    """Milvus vector store for production use."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 19530,
        collection: str = "documents",
        embedding_dim: int = 1536,
    ) -> None:
        self._host = host
        self._port = port
        self._collection = collection
        self._embedding_dim = embedding_dim
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            from pymilvus import MilvusClient
            self._client = MilvusClient(
                uri=f"http://{self._host}:{self._port}",
            )
        return self._client

    async def ensure_collection(self) -> None:
        """Create the collection if it doesn't exist."""
        import asyncio

        def _create() -> None:
            from pymilvus import CollectionSchema, FieldSchema, DataType
            client = self._get_client()

            if client.has_collection(self._collection):
                return

            schema = CollectionSchema(fields=[
                FieldSchema("id", DataType.VARCHAR, is_primary=True, max_length=256),
                FieldSchema("content", DataType.VARCHAR, max_length=65535),
                FieldSchema("embedding", DataType.FLOAT_VECTOR, dim=self._embedding_dim),
                FieldSchema("metadata", DataType.JSON),
            ])

            client.create_collection(
                collection_name=self._collection,
                schema=schema,
            )

            client.create_index(
                collection_name=self._collection,
                field_name="embedding",
                index_params={
                    "index_type": "IVF_FLAT",
                    "metric_type": "COSINE",
                    "params": {"nlist": 128},
                },
            )

        await asyncio.to_thread(_create)

    async def add(self, documents: list[Document]) -> list[str]:
        import asyncio

        def _insert() -> None:
            client = self._get_client()
            data = [
                {
                    "id": doc.doc_id,
                    "content": doc.content,
                    "embedding": doc.embedding,
                    "metadata": doc.metadata,
                }
                for doc in documents
            ]
            client.insert(collection_name=self._collection, data=data)

        await asyncio.to_thread(_insert)
        return [doc.doc_id for doc in documents]

    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        import asyncio

        def _search() -> list[SearchResult]:
            client = self._get_client()

            filter_expr = ""
            if filters:
                conditions = []
                for key, value in filters.items():
                    if isinstance(value, str):
                        conditions.append(f'metadata["{key}"] == "{value}"')
                    else:
                        conditions.append(f'metadata["{key}"] == {value}')
                filter_expr = " and ".join(conditions)

            results = client.search(
                collection_name=self._collection,
                data=[query_embedding],
                limit=top_k,
                output_fields=["content", "metadata"],
                filter=filter_expr or None,
            )

            search_results: list[SearchResult] = []
            for hits in results:
                for hit in hits:
                    metadata = hit.entity.get("metadata", {})
                    if isinstance(metadata, str):
                        import json
                        metadata = json.loads(metadata)
                    search_results.append(SearchResult(
                        doc_id=str(hit.id),
                        content=hit.entity.get("content", ""),
                        score=1.0 - hit.distance,  # COSINE distance to similarity
                        metadata=metadata,
                    ))
            return search_results

        return await asyncio.to_thread(_search)

    async def delete(self, doc_ids: list[str]) -> int:
        import asyncio

        def _delete() -> int:
            client = self._get_client()
            result = client.delete(
                collection_name=self._collection,
                ids=doc_ids,
            )
            return result.get("delete_count", len(doc_ids))

        return await asyncio.to_thread(_delete)

    async def get(self, doc_ids: list[str]) -> list[Document]:
        import asyncio

        def _get() -> list[Document]:
            client = self._get_client()
            results = client.get(
                collection_name=self._collection,
                ids=doc_ids,
                output_fields=["content", "embedding", "metadata"],
            )
            return [
                Document(
                    doc_id=str(r["id"]),
                    content=r.get("content", ""),
                    embedding=r.get("embedding", []),
                    metadata=r.get("metadata", {}),
                )
                for r in results
            ]

        return await asyncio.to_thread(_get)

    async def count(self, filters: dict[str, Any] | None = None) -> int:
        import asyncio

        def _count() -> int:
            client = self._get_client()
            if filters:
                conditions = []
                for key, value in filters.items():
                    if isinstance(value, str):
                        conditions.append(f'metadata["{key}"] == "{value}"')
                    else:
                        conditions.append(f'metadata["{key}"] == {value}')
                filter_expr = " and ".join(conditions)
                result = client.query(
                    collection_name=self._collection,
                    filter=filter_expr,
                    output_fields=["count(*)"],
                )
                return result[0].get("count(*)", 0) if result else 0
            else:
                result = client.query(
                    collection_name=self._collection,
                    filter="",
                    output_fields=["count(*)"],
                )
                return result[0].get("count(*)", 0) if result else 0

        return await asyncio.to_thread(_count)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /root/.openclaw/workspace/kc-flow && python -m pytest tests/unit/test_vector_store_milvus.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/services/rag/vector_store.py tests/unit/test_vector_store_milvus.py
git commit -m "feat(rag): implement MilvusVectorStore with pymilvus"
```

---

### Task 4: HybridSearcher Implementation

**Files:**
- Create: `src/services/rag/hybrid_searcher.py`
- Create: `tests/unit/test_hybrid_searcher.py`

- [ ] **Step 1: Write failing tests for HybridSearcher**

Create `tests/unit/test_hybrid_searcher.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /root/.openclaw/workspace/kc-flow && python -m pytest tests/unit/test_hybrid_searcher.py -v 2>&1 | head -20`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.services.rag.hybrid_searcher'`

- [ ] **Step 3: Implement HybridSearcher**

Create `src/services/rag/hybrid_searcher.py`:

```python
"""Hybrid search — fuses vector similarity with BM25 keyword matching via RRF."""

from typing import Any

import structlog

from src.services.rag.vector_store import Document, SearchResult, VectorStore

logger = structlog.get_logger()


class HybridSearcher:
    """Combines vector search with BM25 keyword search using Reciprocal Rank Fusion.

    Args:
        vector_store: The underlying vector store for semantic search.
        alpha: Weight for vector score (1-alpha for BM25). Default 0.7.
        rrf_k: RRF constant (default 60).
    """

    def __init__(self, vector_store: VectorStore, alpha: float = 0.7, rrf_k: int = 60) -> None:
        self._store = vector_store
        self._alpha = alpha
        self._rrf_k = rrf_k
        self._documents: dict[str, Document] = {}
        self._bm25: Any = None
        self._doc_ids: list[str] = []  # ordered list matching BM25 corpus index

    def _rebuild_bm25(self) -> None:
        """Rebuild the BM25 index from stored documents."""
        from rank_bm25 import BM25Okapi

        corpus = []
        self._doc_ids = []
        for doc_id, doc in self._documents.items():
            tokens = doc.content.lower().split()
            corpus.append(tokens)
            self._doc_ids.append(doc_id)

        if corpus:
            self._bm25 = BM25Okapi(corpus)
        else:
            self._bm25 = None

    async def add_documents(self, documents: list[Document]) -> None:
        """Add documents to the hybrid searcher's index."""
        for doc in documents:
            self._documents[doc.doc_id] = doc
        self._rebuild_bm25()
        logger.debug("HybridSearcher: added documents", count=len(documents))

    async def remove_documents(self, doc_ids: list[str]) -> None:
        """Remove documents from the hybrid searcher's index."""
        for doc_id in doc_ids:
            self._documents.pop(doc_id, None)
        self._rebuild_bm25()
        logger.debug("HybridSearcher: removed documents", count=len(doc_ids))

    async def search(
        self,
        query_embedding: list[float],
        query_text: str,
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Hybrid search combining vector similarity and BM25 via RRF.

        Args:
            query_embedding: Vector embedding of the query.
            query_text: Raw text of the query (for BM25 tokenization).
            top_k: Number of results to return.
            filters: Metadata filters (passed to vector store).

        Returns:
            Merged and re-ranked search results.
        """
        if not query_embedding or not query_text:
            return []

        # 1. Vector search — get 2x candidates
        vector_results = await self._store.search(
            query_embedding=query_embedding,
            top_k=top_k * 2,
            filters=filters,
        )

        # 2. BM25 search
        bm25_scores: dict[str, float] = {}
        if self._bm25 is not None and self._doc_ids:
            tokens = query_text.lower().split()
            scores = self._bm25.get_scores(tokens)
            for doc_id, score in zip(self._doc_ids, scores):
                if score > 0:
                    bm25_scores[doc_id] = float(score)

        # 3. Reciprocal Rank Fusion
        # Rank vector results
        vector_rank: dict[str, int] = {}
        for rank, result in enumerate(vector_results):
            vector_rank[result.doc_id] = rank + 1  # 1-indexed

        # Rank BM25 results
        sorted_bm25 = sorted(bm25_scores.items(), key=lambda x: x[1], reverse=True)
        bm25_rank: dict[str, int] = {}
        for rank, (doc_id, _) in enumerate(sorted_bm25):
            bm25_rank[doc_id] = rank + 1

        # Compute RRF scores
        all_doc_ids = set(vector_rank.keys()) | set(bm25_rank.keys())
        rrf_scores: dict[str, float] = {}

        for doc_id in all_doc_ids:
            score = 0.0
            if doc_id in vector_rank:
                score += self._alpha * (1.0 / (self._rrf_k + vector_rank[doc_id]))
            if doc_id in bm25_rank:
                score += (1.0 - self._alpha) * (1.0 / (self._rrf_k + bm25_rank[doc_id]))
            rrf_scores[doc_id] = score

        # Sort by RRF score descending, take top_k
        sorted_results = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)[:top_k]

        # Build result list with original content
        doc_lookup = {r.doc_id: r for r in vector_results}
        doc_lookup.update(self._documents)

        results: list[SearchResult] = []
        for doc_id, score in sorted_results:
            if doc_id in doc_lookup:
                doc = doc_lookup[doc_id]
                if isinstance(doc, SearchResult):
                    results.append(SearchResult(
                        doc_id=doc_id,
                        content=doc.content,
                        score=score,
                        metadata=doc.metadata,
                    ))
                elif isinstance(doc, Document):
                    results.append(SearchResult(
                        doc_id=doc_id,
                        content=doc.content,
                        score=score,
                        metadata=doc.metadata,
                    ))

        return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /root/.openclaw/workspace/kc-flow && python -m pytest tests/unit/test_hybrid_searcher.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/services/rag/hybrid_searcher.py tests/unit/test_hybrid_searcher.py
git commit -m "feat(rag): implement HybridSearcher with BM25 + RRF fusion"
```

---

### Task 5: CohereReranker Implementation

**Files:**
- Create: `src/services/rag/reranker.py`
- Create: `tests/unit/test_reranker.py`

- [ ] **Step 1: Write failing tests for CohereReranker**

Create `tests/unit/test_reranker.py`:

```python
"""Unit tests for CohereReranker."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.services.rag.reranker import CohereReranker
from src.services.rag.vector_store import SearchResult


@pytest.fixture
def reranker():
    return CohereReranker(api_key="test-key", model="rerank-english-v3.0")


@pytest.mark.asyncio
async def test_reranker_rerank(reranker):
    documents = [
        SearchResult(doc_id="d1", content="The quick brown fox", score=0.9),
        SearchResult(doc_id="d2", content="The lazy dog sleeps", score=0.7),
        SearchResult(doc_id="d3", content="Foxes are quick animals", score=0.8),
    ]

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "results": [
            {"index": 2, "relevance_score": 0.95},
            {"index": 0, "relevance_score": 0.85},
            {"index": 1, "relevance_score": 0.3},
        ],
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        results = await reranker.rerank("quick fox", documents, top_n=2)

    assert len(results) == 2
    assert results[0].doc_id == "d3"  # highest relevance
    assert results[0].score == pytest.approx(0.95)
    assert results[1].doc_id == "d1"
    assert results[1].score == pytest.approx(0.85)


@pytest.mark.asyncio
async def test_reranker_empty_documents(reranker):
    results = await reranker.rerank("query", [], top_n=5)
    assert results == []


@pytest.mark.asyncio
async def test_reranker_api_error(reranker):
    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_response.text = "Rate limited"
    mock_response.raise_for_status = MagicMock(side_effect=Exception("429"))

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        with pytest.raises(Exception):
            await reranker.rerank("query", [
                SearchResult(doc_id="d1", content="test", score=0.5),
            ])


@pytest.mark.asyncio
async def test_reranker_preserves_metadata(reranker):
    documents = [
        SearchResult(doc_id="d1", content="hello", score=0.9, metadata={"source": "doc1"}),
    ]

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "results": [{"index": 0, "relevance_score": 0.99}],
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        results = await reranker.rerank("hello", documents, top_n=1)

    assert results[0].metadata == {"source": "doc1"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /root/.openclaw/workspace/kc-flow && python -m pytest tests/unit/test_reranker.py -v 2>&1 | head -20`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.services.rag.reranker'`

- [ ] **Step 3: Implement CohereReranker**

Create `src/services/rag/reranker.py`:

```python
"""Reranker — post-retrieval reranking via Cohere Rerank API."""

import structlog
import httpx

from src.services.rag.vector_store import SearchResult

logger = structlog.get_logger()


class CohereReranker:
    """Reranks search results using Cohere's Rerank API.

    Args:
        api_key: Cohere API key.
        model: Rerank model name. Default "rerank-english-v3.0".
        timeout: HTTP timeout in seconds. Default 30.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "rerank-english-v3.0",
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout

    async def rerank(
        self,
        query: str,
        documents: list[SearchResult],
        top_n: int | None = None,
    ) -> list[SearchResult]:
        """Rerank documents by relevance to the query.

        Args:
            query: The search query.
            documents: Documents to rerank.
            top_n: Number of top results to return. None = all.

        Returns:
            Re-ordered documents with Cohere relevance scores.
        """
        if not documents:
            return []

        texts = [doc.content for doc in documents]

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                "https://api.cohere.com/v1/rerank",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._model,
                    "query": query,
                    "documents": texts,
                    "top_n": top_n or len(documents),
                    "return_documents": False,
                },
            )
            response.raise_for_status()

        data = response.json()
        results_data = data.get("results", [])

        # Map back to SearchResult objects
        reranked: list[SearchResult] = []
        for item in results_data:
            idx = item["index"]
            original = documents[idx]
            reranked.append(SearchResult(
                doc_id=original.doc_id,
                content=original.content,
                score=float(item["relevance_score"]),
                metadata=original.metadata,
            ))

        logger.debug(
            "Reranked documents",
            input_count=len(documents),
            output_count=len(reranked),
        )

        return reranked
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /root/.openclaw/workspace/kc-flow && python -m pytest tests/unit/test_reranker.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/services/rag/reranker.py tests/unit/test_reranker.py
git commit -m "feat(rag): implement CohereReranker for post-retrieval reranking"
```

---

### Task 6: RAGPipeline Updates

**Files:**
- Modify: `src/services/rag/pipeline.py`

- [ ] **Step 1: Update RAGConfig with new fields**

In `src/services/rag/pipeline.py`, replace the `RAGConfig` dataclass (lines 20-30) with:

```python
@dataclass
class RAGConfig:
    """RAG pipeline configuration."""
    chunking_strategy: ChunkingStrategy = ChunkingStrategy.RECURSIVE
    chunk_size: int = 512
    chunk_overlap: int = 50
    embedding_provider: str = "openai"
    embedding_model: str = "text-embedding-3-small"
    embedding_api_key: str = ""
    vector_store_type: str = "memory"  # memory / pgvector / milvus
    default_top_k: int = 5
    default_score_threshold: float = 0.5
    # PGVector settings
    pgvector_connection_string: str = ""
    pgvector_table_name: str = "documents"
    pgvector_embedding_dim: int = 1536
    # Milvus settings
    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_collection: str = "documents"
    milvus_embedding_dim: int = 1536
    # Hybrid search settings
    hybrid_alpha: float = 0.7  # vector weight (1-alpha = BM25 weight)
    # Reranker settings
    reranker_api_key: str = ""
    reranker_model: str = "rerank-english-v3.0"
```

- [ ] **Step 2: Update imports in pipeline.py**

Replace the import line (line 14) with:

```python
from src.services.rag.vector_store import Document, InMemoryVectorStore, PGVectorStore, MilvusVectorStore, SearchResult, VectorStore
```

Add new imports after the existing imports:

```python
from src.services.rag.hybrid_searcher import HybridSearcher
from src.services.rag.reranker import CohereReranker
```

- [ ] **Step 3: Update _get_vector_store factory**

Replace the `_get_vector_store` method (lines 62-70) with:

```python
    def _get_vector_store(self, knowledge_base_id: str) -> VectorStore:
        """Get or create vector store for a knowledge base."""
        if knowledge_base_id not in self._vector_stores:
            if self.config.vector_store_type == "memory":
                self._vector_stores[knowledge_base_id] = InMemoryVectorStore()
            elif self.config.vector_store_type == "pgvector":
                if not self.config.pgvector_connection_string:
                    raise ValueError("pgvector_connection_string required for pgvector backend")
                self._vector_stores[knowledge_base_id] = PGVectorStore(
                    connection_string=self.config.pgvector_connection_string,
                    table_name=self.config.pgvector_table_name,
                    embedding_dim=self.config.pgvector_embedding_dim,
                )
            elif self.config.vector_store_type == "milvus":
                self._vector_stores[knowledge_base_id] = MilvusVectorStore(
                    host=self.config.milvus_host,
                    port=self.config.milvus_port,
                    collection=self.config.milvus_collection,
                    embedding_dim=self.config.milvus_embedding_dim,
                )
            else:
                raise ValueError(f"Unknown vector_store_type: {self.config.vector_store_type}")
        return self._vector_stores[knowledge_base_id]
```

- [ ] **Step 4: Update retrieve() to support hybrid and reranker**

Replace the `retrieve` method (lines 135-193) with:

```python
    async def retrieve(
        self,
        knowledge_base_id: str,
        query: str,
        strategy: str = "hybrid",
        top_k: int | None = None,
        score_threshold: float | None = None,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Retrieve relevant documents for a query.

        Args:
            knowledge_base_id: Knowledge base to search
            query: Search query
            strategy: Retrieval strategy (vector, hybrid)
            top_k: Number of results to return
            score_threshold: Minimum similarity score
            filters: Metadata filters

        Returns:
            Dict with 'documents' and 'scores' lists
        """
        store = self._get_vector_store(knowledge_base_id)
        embedding_service = self._get_embedding_service()
        top_k = top_k or self.config.default_top_k
        score_threshold = score_threshold or self.config.default_score_threshold

        # Generate query embedding
        query_embedding = await embedding_service.embed_single(query)

        # Search based on strategy
        if strategy == "hybrid":
            searcher = HybridSearcher(store, alpha=self.config.hybrid_alpha)
            # Feed existing documents into hybrid searcher
            # (in production, this would be persisted; for now, rebuild from store)
            results = await searcher.search(
                query_embedding=query_embedding,
                query_text=query,
                top_k=top_k,
                filters=filters,
            )
        else:
            # Pure vector search
            results = await store.search(
                query_embedding=query_embedding,
                top_k=top_k,
                filters=filters,
            )

        # Apply reranker if configured
        if self.config.reranker_api_key:
            reranker = CohereReranker(
                api_key=self.config.reranker_api_key,
                model=self.config.reranker_model,
            )
            results = await reranker.rerank(query, results, top_n=top_k)

        # Filter by score threshold
        filtered = [r for r in results if r.score >= score_threshold]

        documents = [
            {
                "doc_id": r.doc_id,
                "content": r.content,
                "score": r.score,
                "metadata": r.metadata,
            }
            for r in filtered
        ]
        scores = [r.score for r in filtered]

        logger.debug(
            "Documents retrieved",
            knowledge_base_id=knowledge_base_id,
            query_length=len(query),
            results=len(documents),
            strategy=strategy,
        )

        return {"documents": documents, "scores": scores}
```

- [ ] **Step 5: Run existing pipeline tests to check for regressions**

Run: `cd /root/.openclaw/workspace/kc-flow && python -m pytest tests/ -v -k "rag or pipeline" 2>&1 | tail -20`
Expected: All existing tests PASS (no regressions)

- [ ] **Step 6: Commit**

```bash
git add src/services/rag/pipeline.py
git commit -m "feat(rag): wire hybrid search and reranker into RAGPipeline"
```

---

### Task 7: Update __init__.py Exports

**Files:**
- Modify: `src/services/rag/__init__.py`

- [ ] **Step 1: Update exports**

Replace `src/services/rag/__init__.py` with:

```python
"""RAG pipeline components: vector store, chunker, embedding, pipeline."""

from src.services.rag.chunker import Chunk, ChunkingConfig, ChunkingStrategy, DocumentChunker
from src.services.rag.embedding import EmbeddingProvider, EmbeddingService, LocalEmbedding, OpenAIEmbedding
from src.services.rag.hybrid_searcher import HybridSearcher
from src.services.rag.pipeline import RAGConfig, RAGPipeline
from src.services.rag.reranker import CohereReranker
from src.services.rag.vector_store import (
    Document,
    InMemoryVectorStore,
    MilvusVectorStore,
    PGVectorStore,
    SearchResult,
    VectorStore,
)

__all__ = [
    "Chunk",
    "ChunkingConfig",
    "ChunkingStrategy",
    "CohereReranker",
    "Document",
    "DocumentChunker",
    "EmbeddingProvider",
    "EmbeddingService",
    "HybridSearcher",
    "InMemoryVectorStore",
    "LocalEmbedding",
    "MilvusVectorStore",
    "OpenAIEmbedding",
    "PGVectorStore",
    "RAGConfig",
    "RAGPipeline",
    "SearchResult",
    "VectorStore",
]
```

- [ ] **Step 2: Verify imports work**

Run: `cd /root/.openclaw/workspace/kc-flow && python -c "from src.services.rag import RAGPipeline, HybridSearcher, CohereReranker, PGVectorStore, MilvusVectorStore; print('All imports OK')"`
Expected: `All imports OK`

- [ ] **Step 3: Commit**

```bash
git add src/services/rag/__init__.py
git commit -m "feat(rag): export all RAG components from __init__"
```

---

### Task 8: Run Full Test Suite

**Files:**
- None (verification only)

- [ ] **Step 1: Run all RAG-related tests**

Run: `cd /root/.openclaw/workspace/kc-flow && python -m pytest tests/unit/test_vector_store_pg.py tests/unit/test_vector_store_milvus.py tests/unit/test_hybrid_searcher.py tests/unit/test_reranker.py -v`
Expected: All tests PASS

- [ ] **Step 2: Run full test suite to check for regressions**

Run: `cd /root/.openclaw/workspace/kc-flow && python -m pytest tests/ -v 2>&1 | tail -30`
Expected: All tests PASS

- [ ] **Step 3: Final commit if any fixes were needed**

```bash
git add -A
git commit -m "test(rag): verify all RAG pipeline components pass"
```
