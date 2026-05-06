"""Integration tests for the RAG pipeline — end-to-end ingest/retrieve flows."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.services.rag.vector_store import Document, SearchResult, InMemoryVectorStore
from src.services.rag.hybrid_searcher import HybridSearcher
from src.services.rag.reranker import CrossEncoderReranker, CohereReranker
from src.services.rag.embedding import CohereEmbedding, EmbeddingService
from src.services.rag.pipeline import RAGConfig, RAGPipeline


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_docs(n: int = 5) -> list[dict]:
    """Generate test documents."""
    topics = [
        "Python is a high-level programming language known for its readability.",
        "Machine learning is a subset of artificial intelligence that learns from data.",
        "Docker containers package applications with their dependencies for portability.",
        "PostgreSQL is an advanced open-source relational database system.",
        "Kubernetes orchestrates containerized applications across multiple hosts.",
    ]
    return [
        {"content": topics[i % len(topics)], "metadata": {"index": i, "topic": f"t{i}"}}
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# RAGPipeline end-to-end
# ---------------------------------------------------------------------------

class TestRAGPipelineE2E:
    """End-to-end tests using InMemoryVectorStore and mocked embeddings."""

    @pytest.fixture
    def pipeline(self):
        config = RAGConfig(
            vector_store_type="memory",
            embedding_provider="openai",
            embedding_api_key="test-key",
            chunk_size=200,
            chunk_overlap=20,
            default_score_threshold=0.0,
        )
        return RAGPipeline(config)

    @pytest.mark.asyncio
    async def test_ingest_and_retrieve(self, pipeline):
        """Ingest documents then retrieve by query."""
        mock_embeddings = [[float(i % 3) / 10] * 10 for i in range(100)]

        with patch.object(
            pipeline._get_embedding_service(), "embed", new_callable=AsyncMock,
            return_value=mock_embeddings,
        ) as mock_embed:
            ingest_result = await pipeline.ingest("kb_1", _make_docs(3))

        assert ingest_result["document_count"] == 3
        assert ingest_result["chunk_count"] >= 3

        # Retrieve with mocked query embedding
        query_embedding = [0.1] * 10
        with patch.object(
            pipeline._get_embedding_service(), "embed_single", new_callable=AsyncMock,
            return_value=query_embedding,
        ):
            results = await pipeline.retrieve("kb_1", "programming", strategy="vector", top_k=3)

        assert "documents" in results
        assert "scores" in results
        assert len(results["documents"]) > 0

    @pytest.mark.asyncio
    async def test_ingest_persists_in_store(self, pipeline):
        """Documents should persist in the vector store after ingest."""
        mock_embeddings = [[0.1] * 10] * 20
        with patch.object(
            pipeline._get_embedding_service(), "embed", new_callable=AsyncMock,
            return_value=mock_embeddings,
        ):
            await pipeline.ingest("kb_2", _make_docs(2))

        store = pipeline._get_vector_store("kb_2")
        assert await store.count() > 0

    @pytest.mark.asyncio
    async def test_delete_documents(self, pipeline):
        """Ingested documents can be deleted."""
        mock_embeddings = [[0.1] * 10] * 20
        with patch.object(
            pipeline._get_embedding_service(), "embed", new_callable=AsyncMock,
            return_value=mock_embeddings,
        ):
            await pipeline.ingest("kb_3", _make_docs(2))

        store = pipeline._get_vector_store("kb_3")
        docs = await store.list_all()
        doc_ids = [d.doc_id for d in docs[:1]]

        deleted = await pipeline.delete_documents("kb_3", doc_ids)
        assert deleted == 1

    @pytest.mark.asyncio
    async def test_get_stats(self, pipeline):
        """Stats reflect ingested document count."""
        mock_embeddings = [[0.1] * 10] * 20
        with patch.object(
            pipeline._get_embedding_service(), "embed", new_callable=AsyncMock,
            return_value=mock_embeddings,
        ):
            await pipeline.ingest("kb_4", _make_docs(3))

        stats = await pipeline.get_stats("kb_4")
        assert stats["knowledge_base_id"] == "kb_4"
        assert stats["document_count"] > 0
        assert stats["vector_store_type"] == "memory"

    @pytest.mark.asyncio
    async def test_clear_cache(self, pipeline):
        """clear_cache removes cached stores and searchers."""
        mock_embeddings = [[0.1] * 10] * 20
        with patch.object(
            pipeline._get_embedding_service(), "embed", new_callable=AsyncMock,
            return_value=mock_embeddings,
        ):
            await pipeline.ingest("kb_5", _make_docs(1))

        assert "kb_5" in pipeline._vector_stores
        pipeline.clear_cache("kb_5")
        assert "kb_5" not in pipeline._vector_stores

    @pytest.mark.asyncio
    async def test_hybrid_strategy_uses_bm25(self, pipeline):
        """Hybrid search should use BM25 index (synced from store)."""
        mock_embeddings = [[float(i % 5) / 10] * 10 for i in range(100)]
        with patch.object(
            pipeline._get_embedding_service(), "embed", new_callable=AsyncMock,
            return_value=mock_embeddings,
        ):
            await pipeline.ingest("kb_h", _make_docs(3))

        query_embedding = [0.1] * 10
        with patch.object(
            pipeline._get_embedding_service(), "embed_single", new_callable=AsyncMock,
            return_value=query_embedding,
        ):
            results = await pipeline.retrieve("kb_h", "Python programming", strategy="hybrid", top_k=3)

        assert len(results["documents"]) > 0
        # Hybrid searcher should have been cached
        assert "kb_h" in pipeline._hybrid_searchers


# ---------------------------------------------------------------------------
# HybridSearcher sync from store
# ---------------------------------------------------------------------------

class TestHybridSearcherSync:
    """Test that HybridSearcher properly syncs BM25 index from vector store."""

    @pytest.mark.asyncio
    async def test_search_syncs_from_store(self):
        """First search should auto-sync documents from the store."""
        store = InMemoryVectorStore()
        docs = [
            Document(doc_id="d1", content="machine learning algorithms", embedding=[0.1] * 5),
            Document(doc_id="d2", content="python programming guide", embedding=[0.2] * 5),
            Document(doc_id="d3", content="deep learning neural networks", embedding=[0.3] * 5),
        ]
        await store.add(docs)

        searcher = HybridSearcher(store, alpha=0.5)
        assert len(searcher._documents) == 0  # not synced yet

        results = await searcher.search(
            query_embedding=[0.15] * 5,
            query_text="machine learning",
            top_k=3,
        )

        # After search, documents should be synced
        assert len(searcher._documents) == 3
        assert searcher._synced is True
        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_bm25_affects_ranking(self):
        """BM25 keyword matching should influence final ranking."""
        store = InMemoryVectorStore()
        # d2 has closer embeddings to the query but d1 matches keywords better
        docs = [
            Document(doc_id="d1", content="python programming language tutorial", embedding=[0.1] * 5),
            Document(doc_id="d2", content="java enterprise development guide", embedding=[0.9] * 5),
        ]
        await store.add(docs)

        searcher = HybridSearcher(store, alpha=0.3)  # low alpha = more BM25 weight
        results = await searcher.search(
            query_embedding=[0.9] * 5,  # vector-wise closest to d2
            query_text="python tutorial",  # keyword-wise closest to d1
            top_k=2,
        )

        assert len(results) == 2
        # With low alpha (heavy BM25 weight), "python tutorial" should rank d1 higher
        assert results[0].doc_id == "d1"


# ---------------------------------------------------------------------------
# CrossEncoderReranker
# ---------------------------------------------------------------------------

class TestCrossEncoderReranker:

    @pytest.mark.asyncio
    async def test_rerank_returns_sorted(self):
        """CrossEncoderReranker should return documents sorted by score."""
        reranker = CrossEncoderReranker(model_name="test-model")
        documents = [
            SearchResult(doc_id="d1", content="The quick brown fox", score=0.5),
            SearchResult(doc_id="d2", content="The lazy dog sleeps all day", score=0.8),
            SearchResult(doc_id="d3", content="Foxes are quick and agile", score=0.6),
        ]

        mock_model = MagicMock()
        mock_model.predict.return_value = [0.9, 0.2, 0.85]
        reranker._model = mock_model

        results = await reranker.rerank("quick fox", documents, top_n=2)

        assert len(results) == 2
        assert results[0].doc_id == "d1"  # highest cross-encoder score
        assert results[0].score == pytest.approx(0.9)
        assert results[1].doc_id == "d3"

    @pytest.mark.asyncio
    async def test_rerank_empty_documents(self):
        reranker = CrossEncoderReranker()
        results = await reranker.rerank("query", [], top_n=5)
        assert results == []

    @pytest.mark.asyncio
    async def test_rerank_preserves_metadata(self):
        reranker = CrossEncoderReranker(model_name="test-model")
        documents = [
            SearchResult(doc_id="d1", content="hello world", score=0.5, metadata={"src": "a"}),
        ]

        mock_model = MagicMock()
        mock_model.predict.return_value = [0.99]
        reranker._model = mock_model

        results = await reranker.rerank("hello", documents)
        assert results[0].metadata == {"src": "a"}


# ---------------------------------------------------------------------------
# CohereEmbedding
# ---------------------------------------------------------------------------

class TestCohereEmbedding:

    @pytest.mark.asyncio
    async def test_embed_returns_vectors(self):
        """CohereEmbedding should return properly shaped embeddings."""
        provider = CohereEmbedding(api_key="test-key", model="embed-english-v3.0")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "embeddings": {
                "float": [[0.1] * 1024, [0.2] * 1024],
            },
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
            result = await provider.embed(["hello", "world"])

        assert len(result) == 2
        assert len(result[0]) == 1024

    @pytest.mark.asyncio
    async def test_embed_empty_texts(self):
        provider = CohereEmbedding(api_key="test-key")
        result = await provider.embed([])
        assert result == []

    def test_dimension(self):
        provider = CohereEmbedding(api_key="test-key", model="embed-english-v3.0")
        assert provider.dimension() == 1024

        provider_light = CohereEmbedding(api_key="test-key", model="embed-english-light-v3.0")
        assert provider_light.dimension() == 384

    def test_embedding_service_from_config(self):
        service = EmbeddingService.from_config({
            "provider": "cohere",
            "api_key": "test-key",
            "model": "embed-english-v3.0",
        })
        assert service.dimension() == 1024


# ---------------------------------------------------------------------------
# MilvusVectorStore HNSW config
# ---------------------------------------------------------------------------

class TestMilvusHNSWConfig:

    def test_default_index_type_is_hnsw(self):
        from src.services.rag.vector_store import MilvusVectorStore
        store = MilvusVectorStore(host="localhost", port=19530)
        assert store._index_type == "HNSW"

    def test_ivf_flat_config(self):
        from src.services.rag.vector_store import MilvusVectorStore
        store = MilvusVectorStore(index_type="IVF_FLAT", ivf_nlist=256)
        assert store._index_type == "IVF_FLAT"
        assert store._ivf_nlist == 256

    def test_hnsw_custom_params(self):
        from src.services.rag.vector_store import MilvusVectorStore
        store = MilvusVectorStore(index_type="HNSW", hnsw_m=32, hnsw_ef_construction=512)
        assert store._hnsw_m == 32
        assert store._hnsw_ef_construction == 512

    @pytest.mark.asyncio
    async def test_ensure_collection_uses_hnsw(self):
        """ensure_collection should pass HNSW params to Milvus."""
        from src.services.rag.vector_store import MilvusVectorStore

        store = MilvusVectorStore(index_type="HNSW", hnsw_m=16, hnsw_ef_construction=256)

        mock_client = MagicMock()
        mock_client.has_collection.return_value = False

        with patch.object(store, "_get_client", return_value=mock_client):
            with patch("pymilvus.CollectionSchema"), patch("pymilvus.FieldSchema"), patch("pymilvus.DataType"):
                await store.ensure_collection()

        # Verify create_index was called with HNSW params
        call_kwargs = mock_client.create_index.call_args
        index_params = call_kwargs.kwargs.get("index_params") or call_kwargs[1].get("index_params")
        assert index_params["index_type"] == "HNSW"
        assert index_params["params"]["M"] == 16
        assert index_params["params"]["efConstruction"] == 256

    @pytest.mark.asyncio
    async def test_ensure_collection_uses_ivf_flat(self):
        """ensure_collection should pass IVF_FLAT params to Milvus."""
        from src.services.rag.vector_store import MilvusVectorStore

        store = MilvusVectorStore(index_type="IVF_FLAT", ivf_nlist=128)

        mock_client = MagicMock()
        mock_client.has_collection.return_value = False

        with patch.object(store, "_get_client", return_value=mock_client):
            with patch("pymilvus.CollectionSchema"), patch("pymilvus.FieldSchema"), patch("pymilvus.DataType"):
                await store.ensure_collection()

        call_kwargs = mock_client.create_index.call_args
        index_params = call_kwargs.kwargs.get("index_params") or call_kwargs[1].get("index_params")
        assert index_params["index_type"] == "IVF_FLAT"
        assert index_params["params"]["nlist"] == 128


# ---------------------------------------------------------------------------
# InMemoryVectorStore list_all
# ---------------------------------------------------------------------------

class TestInMemoryVectorStoreListAll:

    @pytest.mark.asyncio
    async def test_list_all_returns_all_docs(self):
        store = InMemoryVectorStore()
        docs = [
            Document(doc_id=f"d{i}", content=f"doc {i}", embedding=[float(i)] * 3)
            for i in range(5)
        ]
        await store.add(docs)

        all_docs = await store.list_all()
        assert len(all_docs) == 5

    @pytest.mark.asyncio
    async def test_list_all_respects_limit(self):
        store = InMemoryVectorStore()
        docs = [
            Document(doc_id=f"d{i}", content=f"doc {i}", embedding=[float(i)] * 3)
            for i in range(10)
        ]
        await store.add(docs)

        limited = await store.list_all(limit=3)
        assert len(limited) == 3

    @pytest.mark.asyncio
    async def test_list_all_empty_store(self):
        store = InMemoryVectorStore()
        result = await store.list_all()
        assert result == []
