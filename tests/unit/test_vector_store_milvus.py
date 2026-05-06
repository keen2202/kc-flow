"""Unit tests for MilvusVectorStore (mocked pymilvus)."""

import pytest
from unittest.mock import MagicMock, patch
from src.services.rag.vector_store import MilvusVectorStore, Document, SearchResult


@pytest.fixture
def mock_milvus():
    """Mock pymilvus modules."""
    with patch("pymilvus.MilvusClient") as mock_client_cls:
        client = MagicMock()
        mock_client_cls.return_value = client
        yield client


@pytest.mark.asyncio
async def test_milvus_ensure_collection():
    store = MilvusVectorStore(embedding_dim=128)
    mock_client = MagicMock()
    mock_client.has_collection.return_value = False
    store._client = mock_client

    await store.ensure_collection()

    mock_client.create_collection.assert_called_once()
    mock_client.create_index.assert_called_once()


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
    mock_milvus.query.return_value = [{"count(*)": 42}]
    store = MilvusVectorStore(embedding_dim=128)

    count = await store.count()

    assert count == 42


@pytest.mark.asyncio
async def test_milvus_search_with_filters(mock_milvus):
    hit = MagicMock()
    hit.id = "d1"
    hit.distance = 0.2
    hit.entity = {"content": "filtered", "metadata": {"category": "test"}}
    mock_milvus.search.return_value = [[hit]]

    store = MilvusVectorStore(embedding_dim=128)
    results = await store.search([0.1] * 128, top_k=5, filters={"category": "test"})

    assert len(results) == 1
    mock_milvus.search.assert_called_once()
    call_kwargs = mock_milvus.search.call_args[1]
    assert call_kwargs["filter"] is not None
