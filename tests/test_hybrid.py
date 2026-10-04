from typing import Any

import pytest

from landlaw_rag.retrieval.hybrid import (
    HybridConfig,
    HybridRetriever,
    apply_version_boost,
    detect_version_intent,
)


class StubRetriever:
    def __init__(self, results: list[dict[str, Any]]) -> None:
        self.results = results

    def search(self, query: str, top_k: int) -> list[dict[str, Any]]:
        return self.results[:top_k]


def _result(chunk_id: str, rank: int, score: float, **metadata: str) -> dict[str, Any]:
    return {"chunk_id": chunk_id, "text": f"Nội dung {chunk_id}", "metadata": metadata, "score": score, "rank": rank}


def test_rrf_merges_and_deduplicates_chunk_ids() -> None:
    bm25 = StubRetriever([_result("shared", 1, 10.0), _result("lexical", 2, 8.0)])
    vector = StubRetriever([_result("semantic", 1, 0.9), _result("shared", 2, 0.8)])
    results = HybridRetriever(bm25, vector, HybridConfig(rrf_k=60)).search("bồi thường đất", top_k=3)
    assert [item["chunk_id"] for item in results] == ["shared", "semantic", "lexical"]
    assert results[0]["bm25_score"] == 10.0
    assert results[0]["vector_score"] == 0.8
    assert len({item["chunk_id"] for item in results}) == 3


def test_exact_legal_reference_is_prioritized() -> None:
    bm25 = StubRetriever([
        _result("popular", 1, 20.0, document_id="45-2013-QH13", article="Điều 57"),
        _result("exact", 2, 10.0, document_id="31-2024-QH15", article="Điều 57", clause="Khoản 2"),
    ])
    vector = StubRetriever([_result("popular", 1, 0.95, document_id="45-2013-QH13")])
    results = HybridRetriever(bm25, vector).search("Khoản 2 Điều 57 Luật 31/2024/QH15", top_k=2)
    assert results[0]["chunk_id"] == "exact"
    assert results[0]["exact_match_count"] == 3
    assert results[0]["rank"] == 1


def test_result_schema_and_missing_source_scores() -> None:
    retriever = HybridRetriever(StubRetriever([_result("bm25-only", 1, 3.5)]), StubRetriever([]))
    result = retriever.search("quyền sử dụng đất", top_k=1)[0]
    assert {"chunk_id", "text", "metadata", "bm25_score", "vector_score", "rrf_score", "rank"} <= result.keys()
    assert result["vector_score"] is None
    assert result["rrf_score"] == pytest.approx(1 / 61)


def test_empty_query_is_rejected() -> None:
    retriever = HybridRetriever(StubRetriever([]), StubRetriever([]))
    with pytest.raises(ValueError, match="Query không được rỗng"):
        retriever.search("   ")


def _fused(chunk_id: str, year: int, rrf_score: float) -> dict[str, Any]:
    document_id = "45-2013-QH13" if year == 2013 else "31-2024-QH15"
    return {
        "chunk_id": chunk_id,
        "text": f"Luật Đất đai {year}",
        "metadata": {"document_id": document_id, "document_title": f"Luật Đất đai {year}"},
        "bm25_score": 1.0,
        "vector_score": 0.8,
        "rrf_score": rrf_score,
    }


def test_unspecified_year_prefers_current_2024_without_removing_2013() -> None:
    query = "Người dân được bồi thường như thế nào khi Nhà nước thu hồi đất ở?"
    results = apply_version_boost(query, [_fused("law-2013", 2013, 0.030), _fused("law-2024", 2024, 0.029)])
    assert results[0]["chunk_id"] == "law-2024"
    assert results[0]["version_score"] > 0
    assert {item["version_year"] for item in results} == {2013, 2024}


@pytest.mark.parametrize(
    ("query", "expected_year"),
    [
        ("Điều 79 Luật Đất đai 2013 quy định gì?", 2013),
        ("Điều 98 Luật Đất đai 2024 quy định gì?", 2024),
    ],
)
def test_explicit_year_prioritizes_requested_law(query: str, expected_year: int) -> None:
    results = apply_version_boost(query, [_fused("law-2013", 2013, 0.031), _fused("law-2024", 2024, 0.031)])
    assert results[0]["version_year"] == expected_year
    assert results[0]["version_intent"] == "explicit"
    assert results[0]["final_score"] > results[1]["final_score"]


def test_comparison_query_keeps_both_versions_in_top_k() -> None:
    query = "So sánh quy định bồi thường đất ở giữa 2013 và 2024."
    candidates = [
        _fused("law-2024-a", 2024, 0.040),
        _fused("law-2024-b", 2024, 0.039),
        _fused("law-2013", 2013, 0.020),
    ]
    results = apply_version_boost(query, candidates, top_k=2)
    assert detect_version_intent(query)["mode"] == "comparison"
    assert {item["version_year"] for item in results} == {2013, 2024}
    assert all(item["version_score"] > 0 for item in results)
