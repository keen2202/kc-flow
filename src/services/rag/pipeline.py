"""RAG Pipeline — end-to-end retrieval-augmented generation pipeline.

Combines document chunking, embedding, vector storage, and retrieval
into a unified interface for the KnowledgeRetrieval node.
"""

from dataclasses import dataclass
from typing import Any

import structlog

from src.services.rag.chunker import ChunkingConfig, ChunkingStrategy, DocumentChunker
from src.services.rag.embedding import EmbeddingService
from src.services.rag.hybrid_searcher import HybridSearcher
from src.services.rag.reranker import CohereReranker, CrossEncoderReranker
from src.services.rag.vector_store import Document, InMemoryVectorStore, MilvusVectorStore, PGVectorStore, SearchResult, VectorStore

logger = structlog.get_logger()


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
    milvus_index_type: str = "HNSW"  # HNSW or IVF_FLAT
    # Hybrid search settings
    hybrid_alpha: float = 0.7  # vector weight (1-alpha = BM25 weight)
    # Reranker settings
    reranker_type: str = "cohere"  # cohere / local
    reranker_api_key: str = ""
    reranker_model: str = "rerank-english-v3.0"
    reranker_local_model: str = "BAAI/bge-reranker-base"


class RAGPipeline:
    """End-to-end RAG pipeline: ingest documents and retrieve relevant chunks.

    Usage:
        pipeline = RAGPipeline()
        await pipeline.ingest(knowledge_base_id="kb_1", documents=[...])
        results = await pipeline.retrieve(knowledge_base_id="kb_1", query="What is...")
    """

    def __init__(self, config: RAGConfig | None = None) -> None:
        self.config = config or RAGConfig()
        self._chunker = DocumentChunker(ChunkingConfig(
            strategy=self.config.chunking_strategy,
            chunk_size=self.config.chunk_size,
            chunk_overlap=self.config.chunk_overlap,
        ))
        self._embedding_service: EmbeddingService | None = None
        self._vector_stores: dict[str, VectorStore] = {}  # knowledge_base_id -> store
        self._hybrid_searchers: dict[str, HybridSearcher] = {}  # knowledge_base_id -> searcher

    def _get_embedding_service(self) -> EmbeddingService:
        """Lazy-init embedding service."""
        if self._embedding_service is None:
            self._embedding_service = EmbeddingService.from_config({
                "provider": self.config.embedding_provider,
                "model": self.config.embedding_model,
                "api_key": self.config.embedding_api_key,
            })
        return self._embedding_service

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
                    index_type=self.config.milvus_index_type,
                )
            else:
                raise ValueError(f"Unknown vector_store_type: {self.config.vector_store_type}")
        return self._vector_stores[knowledge_base_id]

    async def ingest(
        self,
        knowledge_base_id: str,
        documents: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Ingest documents into a knowledge base.

        Args:
            knowledge_base_id: Target knowledge base ID
            documents: List of documents with 'content' and optional 'metadata'

        Returns:
            Ingestion statistics
        """
        store = self._get_vector_store(knowledge_base_id)
        embedding_service = self._get_embedding_service()

        total_chunks = 0
        all_chunks: list[tuple[str, str, dict[str, Any]]] = []  # (chunk_id, content, metadata)

        for doc in documents:
            content = doc.get("content", "")
            metadata = doc.get("metadata", {})
            doc_id = doc.get("doc_id", f"doc_{total_chunks}")

            chunks = self._chunker.chunk(content, {**metadata, "doc_id": doc_id, "knowledge_base_id": knowledge_base_id})
            for chunk in chunks:
                all_chunks.append((chunk.chunk_id, chunk.content, chunk.metadata))
            total_chunks += len(chunks)

        # Generate embeddings in batches
        batch_size = 100
        vector_docs: list[Document] = []

        for i in range(0, len(all_chunks), batch_size):
            batch = all_chunks[i:i + batch_size]
            texts = [content for _, content, _ in batch]
            embeddings = await embedding_service.embed(texts)

            for (chunk_id, content, metadata), embedding in zip(batch, embeddings):
                vector_docs.append(Document(
                    doc_id=chunk_id,
                    content=content,
                    embedding=embedding,
                    metadata=metadata,
                ))

        # Store in vector store
        await store.add(vector_docs)

        logger.info(
            "Documents ingested",
            knowledge_base_id=knowledge_base_id,
            document_count=len(documents),
            chunk_count=total_chunks,
        )

        return {
            "document_count": len(documents),
            "chunk_count": total_chunks,
            "vector_count": len(vector_docs),
        }

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
            if knowledge_base_id not in self._hybrid_searchers:
                self._hybrid_searchers[knowledge_base_id] = HybridSearcher(
                    store, alpha=self.config.hybrid_alpha,
                )
            searcher = self._hybrid_searchers[knowledge_base_id]
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
        if self.config.reranker_type == "local":
            reranker = CrossEncoderReranker(
                model_name=self.config.reranker_local_model,
            )
            results = await reranker.rerank(query, results, top_n=top_k)
        elif self.config.reranker_api_key:
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

    async def delete_documents(
        self,
        knowledge_base_id: str,
        doc_ids: list[str],
    ) -> int:
        """Delete documents from a knowledge base."""
        store = self._get_vector_store(knowledge_base_id)
        count = await store.delete(doc_ids)
        logger.info("Documents deleted", knowledge_base_id=knowledge_base_id, count=count)
        return count

    async def get_stats(self, knowledge_base_id: str) -> dict[str, Any]:
        """Get knowledge base statistics."""
        store = self._get_vector_store(knowledge_base_id)
        count = await store.count()
        return {
            "knowledge_base_id": knowledge_base_id,
            "document_count": count,
            "vector_store_type": self.config.vector_store_type,
        }

    def clear_cache(self, knowledge_base_id: str | None = None) -> None:
        """Clear cached vector stores and hybrid searchers."""
        if knowledge_base_id:
            self._vector_stores.pop(knowledge_base_id, None)
            self._hybrid_searchers.pop(knowledge_base_id, None)
        else:
            self._vector_stores.clear()
            self._hybrid_searchers.clear()
