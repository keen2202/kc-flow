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
        ],
    }
    mock_response.raise_for_status = MagicMock()

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
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        results = await reranker.rerank("hello", documents, top_n=1)

    assert results[0].metadata == {"source": "doc1"}
