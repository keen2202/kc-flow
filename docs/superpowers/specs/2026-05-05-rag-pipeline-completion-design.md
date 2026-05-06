# RAG Pipeline Completion Design

**Date:** 2026-05-05
**Task:** #33 RAG Pipeline
**Scope:** Complete remaining checklist items — PGVector/Milvus backends, hybrid search, reranker

---

## Current State

Implemented:
- `VectorStore` ABC with `InMemoryVectorStore` (cosine similarity)
- `PGVectorStore` and `MilvusVectorStore` (stubs raising `NotImplementedError`)
- `EmbeddingService` with OpenAI + local sentence-transformers
- `DocumentChunker` with 4 strategies (fixed, sentence, paragraph, recursive)
- `RAGPipeline` with ingest/retrieve/delete/stats

## Components to Implement

### 1. PGVectorStore

**File:** `src/services/rag/vector_store.py` (replace stub)

- Uses `asyncpg` for async PostgreSQL access
- Constructor: `PGVectorStore(connection_string, table_name="documents", embedding_dim=1536)`
- `ensure_table()`: CREATE TABLE IF NOT EXISTS with columns: `id TEXT PRIMARY KEY`, `content TEXT`, `embedding vector({dim})`, `metadata JSONB`, `created_at TIMESTAMPTZ DEFAULT NOW()`. Creates GIN index on metadata.
- `add()`: INSERT ... ON CONFLICT (id) DO UPDATE with batch support
- `search()`: SELECT with `<=>` (cosine distance) operator, ORDER BY distance LIMIT top_k. Supports metadata filter via JSONB `@>` operator.
- `delete()`, `get()`, `count()`: standard SQL operations
- Distance metric: cosine (default) or L2, configurable via constructor

### 2. MilvusVectorStore

**File:** `src/services/rag/vector_store.py` (replace stub)

- Uses `pymilvus` (async via `asyncio.to_thread` wrapping sync calls)
- Constructor: `MilvusVectorStore(host="localhost", port=19530, collection="documents", embedding_dim=1536)`
- `ensure_collection()`: Create collection with schema (id VARCHAR, content VARCHAR, embedding FLOAT_VECTOR, metadata JSON), IVF_FLAT index with COSINE metric
- `add()`: batch insert with auto-generated IDs
- `search()`: vector search with metric_type=COSINE, metadata filter expression
- `delete()`, `get()`, `count()`: standard Milvus operations

### 3. HybridSearcher

**File:** `src/services/rag/hybrid_searcher.py` (new)

- Uses `rank_bm25` library for BM25 scoring
- Constructor: `HybridSearcher(vector_store, alpha=0.7)` — alpha = vector score weight
- Maintains an in-memory BM25 index (rebuilt on add/delete)
- Tokenization: simple whitespace + lowercase split (no external tokenizer dependency)
- `search(query_embedding, query_text, top_k)`:
  1. Vector search: top_k * 2 results from vector store
  2. BM25 search: tokenize query, score all stored documents
  3. Merge via Reciprocal Rank Fusion (RRF): `score = 1/(k+rank_vector) + 1/(k+rank_bm25)` with k=60
  4. Return merged top_k results
- `add_documents()` / `remove_documents()`: update BM25 index

### 4. Reranker

**File:** `src/services/rag/reranker.py` (new)

- Uses httpx to call Cohere Rerank API
- Constructor: `CohereReranker(api_key, model="rerank-english-v3.0")`
- `rerank(query, documents, top_n)`:
  1. POST to `https://api.cohere.com/v1/rerank`
  2. Pass query + list of document texts
  3. Return re-ordered documents with relevance scores
- Error handling: timeout, rate limit, API errors

### 5. RAGPipeline Updates

**File:** `src/services/rag/pipeline.py`

- `_get_vector_store()`: factory based on `config.vector_store_type`:
  - `"memory"` → `InMemoryVectorStore`
  - `"pgvector"` → `PGVectorStore(config.pgvector_connection_string)`
  - `"milvus"` → `MilvusVectorStore(config.milvus_host, config.milvus_port)`
- `retrieve()`:
  - If `strategy == "hybrid"`: use `HybridSearcher`
  - If `reranker_config` set: apply `CohereReranker` after retrieval
- Add `RAGConfig` fields: `pgvector_connection_string`, `milvus_host`, `milvus_port`, `reranker_api_key`, `reranker_model`, `hybrid_alpha`

### 6. Integration Tests

**File:** `tests/integration/test_rag_pipeline.py`

- Test PGVectorStore with real asyncpg connection (skip if no PG available)
- Test MilvusVectorStore with real pymilvus connection (skip if no Milvus available)
- Test HybridSearcher with mock vector store
- Test CohereReranker with mocked httpx responses
- Test RAGPipeline end-to-end with each backend

## Dependencies

New packages to add to `pyproject.toml`:
- `asyncpg>=0.29.0` (already listed)
- `pymilvus>=2.4.0` (new)
- `rank-bm25>=0.2.2` (new)
