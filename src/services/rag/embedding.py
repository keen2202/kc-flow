"""Embedding service — vector embedding generation for RAG pipeline."""

from abc import ABC, abstractmethod
from typing import Any

import structlog

logger = structlog.get_logger()


class EmbeddingProvider(ABC):
    """Abstract base class for embedding providers."""

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of texts."""
        ...

    @abstractmethod
    def dimension(self) -> int:
        """Return the embedding dimension."""
        ...


class OpenAIEmbedding(EmbeddingProvider):
    """OpenAI embedding provider using text-embedding-3-small/large."""

    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small",
        base_url: str | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url or "https://api.openai.com/v1"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        import httpx

        if not texts:
            return []

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self._base_url}/embeddings",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"input": texts, "model": self._model},
            )
            response.raise_for_status()
            data = response.json()

            # Sort by index to maintain order
            embeddings = sorted(data["data"], key=lambda x: x["index"])
            return [e["embedding"] for e in embeddings]

    def dimension(self) -> int:
        dims = {
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
            "text-embedding-ada-002": 1536,
        }
        return dims.get(self._model, 1536)


class CohereEmbedding(EmbeddingProvider):
    """Cohere embedding provider using embed-v4 / embed-english-v3.0."""

    def __init__(
        self,
        api_key: str,
        model: str = "embed-english-v3.0",
        input_type: str = "search_document",
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._input_type = input_type

    async def embed(self, texts: list[str]) -> list[list[float]]:
        import httpx

        if not texts:
            return []

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                "https://api.cohere.com/v1/embed",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "texts": texts,
                    "model": self._model,
                    "input_type": self._input_type,
                    "embedding_types": ["float"],
                },
            )
            response.raise_for_status()
            data = response.json()

            return data["embeddings"]["float"]

    def dimension(self) -> int:
        dims = {
            "embed-english-v3.0": 1024,
            "embed-multilingual-v3.0": 1024,
            "embed-english-light-v3.0": 384,
            "embed-multilingual-light-v3.0": 384,
        }
        return dims.get(self._model, 1024)


class LocalEmbedding(EmbeddingProvider):
    """Local embedding using sentence-transformers (optional dependency)."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self._model_name = model_name
        self._model: Any = None

    def _load_model(self) -> Any:
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self._model_name)
            except ImportError:
                raise ImportError(
                    "sentence-transformers is required for local embeddings. "
                    "Install with: pip install sentence-transformers"
                )
        return self._model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        model = self._load_model()
        embeddings = model.encode(texts, show_progress_bar=False)
        return embeddings.tolist()

    def dimension(self) -> int:
        model = self._load_model()
        return model.get_sentence_embedding_dimension()


class EmbeddingService:
    """Unified embedding service with provider selection."""

    def __init__(self, provider: EmbeddingProvider | None = None) -> None:
        self._provider = provider

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "EmbeddingService":
        """Create embedding service from configuration."""
        provider_type = config.get("provider", "openai")

        if provider_type == "openai":
            provider = OpenAIEmbedding(
                api_key=config.get("api_key", ""),
                model=config.get("model", "text-embedding-3-small"),
                base_url=config.get("base_url"),
            )
        elif provider_type == "cohere":
            provider = CohereEmbedding(
                api_key=config.get("api_key", ""),
                model=config.get("model", "embed-english-v3.0"),
                input_type=config.get("input_type", "search_document"),
            )
        elif provider_type == "local":
            provider = LocalEmbedding(
                model_name=config.get("model", "all-MiniLM-L6-v2"),
            )
        else:
            raise ValueError(f"Unknown embedding provider: {provider_type}")

        return cls(provider=provider)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for texts."""
        if self._provider is None:
            raise RuntimeError("No embedding provider configured")
        return await self._provider.embed(texts)

    async def embed_single(self, text: str) -> list[float]:
        """Generate embedding for a single text."""
        results = await self.embed([text])
        return results[0] if results else []

    def dimension(self) -> int:
        """Get embedding dimension."""
        if self._provider is None:
            raise RuntimeError("No embedding provider configured")
        return self._provider.dimension()
