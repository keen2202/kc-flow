"""Reranker — post-retrieval reranking via Cohere Rerank API or local cross-encoder."""

from typing import Any

import structlog
import httpx

from src.services.rag.vector_store import SearchResult

logger = structlog.get_logger()


class CrossEncoderReranker:
    """Local cross-encoder reranker using sentence-transformers.

    Supports BAAI/bge-reranker models and other CrossEncoder-compatible models.

    Args:
        model_name: HuggingFace model name. Default "BAAI/bge-reranker-base".
    """

    def __init__(self, model_name: str = "BAAI/bge-reranker-base") -> None:
        self._model_name = model_name
        self._model: Any = None

    def _load_model(self) -> Any:
        if self._model is None:
            try:
                from sentence_transformers import CrossEncoder
                self._model = CrossEncoder(self._model_name)
            except ImportError:
                raise ImportError(
                    "sentence-transformers is required for local reranking. "
                    "Install with: pip install sentence-transformers"
                )
        return self._model

    async def rerank(
        self,
        query: str,
        documents: list[SearchResult],
        top_n: int | None = None,
    ) -> list[SearchResult]:
        """Rerank documents using a local cross-encoder model."""
        if not documents:
            return []

        import asyncio

        model = self._load_model()
        pairs = [(query, doc.content) for doc in documents]

        scores = await asyncio.to_thread(model.predict, pairs)

        scored = list(zip(documents, scores))
        scored.sort(key=lambda x: x[1], reverse=True)

        if top_n is not None:
            scored = scored[:top_n]

        reranked: list[SearchResult] = []
        for doc, score in scored:
            reranked.append(SearchResult(
                doc_id=doc.doc_id,
                content=doc.content,
                score=float(score),
                metadata=doc.metadata,
            ))

        logger.debug(
            "Cross-encoder reranked documents",
            model=self._model_name,
            input_count=len(documents),
            output_count=len(reranked),
        )

        return reranked


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
