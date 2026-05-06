"""Vector store abstraction — storage and retrieval of embeddings for RAG."""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class Document:
    """A document stored in the vector store."""
    doc_id: str
    content: str
    embedding: list[float] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResult:
    """A search result from the vector store."""
    doc_id: str
    content: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


class VectorStore(ABC):
    """Abstract base class for vector stores."""

    @abstractmethod
    async def add(self, documents: list[Document]) -> list[str]:
        """Add documents to the store. Returns list of doc IDs."""
        ...

    @abstractmethod
    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Search for similar documents."""
        ...

    @abstractmethod
    async def delete(self, doc_ids: list[str]) -> int:
        """Delete documents by ID. Returns count deleted."""
        ...

    @abstractmethod
    async def get(self, doc_ids: list[str]) -> list[Document]:
        """Get documents by ID."""
        ...

    @abstractmethod
    async def count(self, filters: dict[str, Any] | None = None) -> int:
        """Count documents in the store."""
        ...

    async def list_all(self, limit: int = 100_000) -> list[Document]:
        """List all documents. Default implementation uses get() after search().

        Subclasses may override for efficiency.
        """
        return []


class InMemoryVectorStore(VectorStore):
    """Simple in-memory vector store for development and testing."""

    def __init__(self) -> None:
        self._documents: dict[str, Document] = {}

    async def add(self, documents: list[Document]) -> list[str]:
        doc_ids: list[str] = []
        for doc in documents:
            self._documents[doc.doc_id] = doc
            doc_ids.append(doc.doc_id)
        logger.debug("Added documents to vector store", count=len(doc_ids))
        return doc_ids

    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        scores: list[tuple[str, float]] = []

        for doc_id, doc in self._documents.items():
            # Apply metadata filters
            if filters and not self._match_filters(doc.metadata, filters):
                continue

            if not doc.embedding:
                continue

            score = self._cosine_similarity(query_embedding, doc.embedding)
            scores.append((doc_id, score))

        # Sort by score descending
        scores.sort(key=lambda x: x[1], reverse=True)
        top_results = scores[:top_k]

        results: list[SearchResult] = []
        for doc_id, score in top_results:
            doc = self._documents[doc_id]
            results.append(SearchResult(
                doc_id=doc_id,
                content=doc.content,
                score=score,
                metadata=doc.metadata,
            ))

        return results

    async def delete(self, doc_ids: list[str]) -> int:
        count = 0
        for doc_id in doc_ids:
            if doc_id in self._documents:
                del self._documents[doc_id]
                count += 1
        return count

    async def get(self, doc_ids: list[str]) -> list[Document]:
        return [self._documents[doc_id] for doc_id in doc_ids if doc_id in self._documents]

    async def count(self, filters: dict[str, Any] | None = None) -> int:
        if not filters:
            return len(self._documents)
        return sum(1 for doc in self._documents.values() if self._match_filters(doc.metadata, filters))

    async def list_all(self, limit: int = 100_000) -> list[Document]:
        return list(self._documents.values())[:limit]

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if len(a) != len(b) or not a:
            return 0.0
        dot_product = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot_product / (norm_a * norm_b)

    @staticmethod
    def _match_filters(metadata: dict[str, Any], filters: dict[str, Any]) -> bool:
        """Check if document metadata matches all filters."""
        for key, value in filters.items():
            if key not in metadata:
                return False
            if isinstance(value, list):
                if metadata[key] not in value:
                    return False
            elif metadata[key] != value:
                return False
        return True


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

    async def list_all(self, limit: int = 100_000) -> list[Document]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT id, content, embedding, metadata FROM {self._table_name} LIMIT $1",
                limit,
            )
        return [
            Document(
                doc_id=row["id"],
                content=row["content"],
                embedding=list(row["embedding"]) if row["embedding"] else [],
                metadata=json.loads(row["metadata"]) if isinstance(row["metadata"], str) else row["metadata"],
            )
            for row in rows
        ]


class MilvusVectorStore(VectorStore):
    """Milvus vector store for production use.

    Args:
        host: Milvus server host.
        port: Milvus server port.
        collection: Collection name.
        embedding_dim: Embedding vector dimension.
        index_type: Vector index type — "IVF_FLAT" or "HNSW".
        hnsw_m: HNSW parameter — max connections per node (default 16).
        hnsw_ef_construction: HNSW parameter — search width during construction (default 256).
        ivf_nlist: IVF_FLAT parameter — number of clusters (default 128).
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 19530,
        collection: str = "documents",
        embedding_dim: int = 1536,
        index_type: str = "HNSW",
        hnsw_m: int = 16,
        hnsw_ef_construction: int = 256,
        ivf_nlist: int = 128,
    ) -> None:
        self._host = host
        self._port = port
        self._collection = collection
        self._embedding_dim = embedding_dim
        self._index_type = index_type.upper()
        self._hnsw_m = hnsw_m
        self._hnsw_ef_construction = hnsw_ef_construction
        self._ivf_nlist = ivf_nlist
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
            from pymilvus import CollectionSchema, DataType, FieldSchema
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

            if self._index_type == "HNSW":
                index_params = {
                    "index_type": "HNSW",
                    "metric_type": "COSINE",
                    "params": {
                        "M": self._hnsw_m,
                        "efConstruction": self._hnsw_ef_construction,
                    },
                }
            else:  # IVF_FLAT
                index_params = {
                    "index_type": "IVF_FLAT",
                    "metric_type": "COSINE",
                    "params": {"nlist": self._ivf_nlist},
                }

            client.create_index(
                collection_name=self._collection,
                field_name="embedding",
                index_params=index_params,
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
