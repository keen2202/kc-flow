"""Hybrid search — fuses vector similarity with BM25 keyword matching via RRF."""

from typing import Any

import structlog

from src.services.rag.vector_store import Document, SearchResult, VectorStore

logger = structlog.get_logger()


class HybridSearcher:
    """Combines vector search with BM25 keyword search using Reciprocal Rank Fusion.

    Maintains a BM25 index that is lazily synced from the vector store on first
    search call.  The sync pulls all documents from the store so BM25 has the
    full corpus for accurate keyword scoring.

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
        self._synced: bool = False

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

    async def _ensure_synced(self) -> None:
        """Sync the BM25 corpus from the vector store if not yet done."""
        if self._synced:
            return

        try:
            all_docs = await self._store.list_all()
            for doc in all_docs:
                if doc.doc_id not in self._documents:
                    self._documents[doc.doc_id] = doc
            self._rebuild_bm25()
            self._synced = True
            logger.debug("HybridSearcher: synced from store", count=len(self._documents))
        except Exception:
            logger.warning("HybridSearcher: failed to sync from store, using local index only")

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

        # Ensure BM25 index is populated from the vector store
        await self._ensure_synced()

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
