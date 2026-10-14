from typing import Any

import pytest

from landlaw_rag.retrieval.graph import GraphConfig, GraphRetriever
from landlaw_rag.evaluation.graph import evaluate_graph_ablation
from landlaw_rag.generation.rag import filter_results_by_version


class StubRetriever:
    def __init__(self, results: list[dict[str, Any]]) -> None:
        self.results = results
        self.calls: list[int] = []

    def search(self, query: str, top_k: int) -> list[dict[str, Any]]:
        self.calls.append(top_k)
        return self.results[:top_k]


def _chunk(chunk_id: str, document: str, article: str, text: str, clause: str | None = None):
    return {
        "chunk_id": chunk_id,
        "text": text,
        "metadata": {
            "chunk_id": chunk_id,
            "document_id": document,
            "article": article,
            "clause": clause,
            "source_file": f"{document}.txt",
        },
    }


def test_graph_builds_hierarchy_and_provenance_for_amendment_edge() -> None:
    source = _chunk(
        "law43-a1-c2", "43-2024-QH15", "Điều 1",
        "Sửa đổi, bổ sung khoản 1 Điều 252 như sau.", "Khoản 2",
    )
    target = _chunk("law31-a252-c1", "31-2024-QH15", "Điều 252", "Nội dung hiệu lực.", "Khoản 1")
    stub = StubRetriever([{
        "chunk_id": source["chunk_id"], "text": source["text"],
        "metadata": source["metadata"], "rank": 1, "rrf_score": 0.03,
    }])
    graph = GraphRetriever(stub, [source, target])

    result = graph.search("Luật 43 sửa đổi Điều 252", top_k=2)
    target_hit = next(item for item in result if item["chunk_id"] == target["chunk_id"])
    assert "amends_article" in target_hit["graph_relations"]
    assert target_hit["graph_provenance"][0]["source_chunk_id"] == source["chunk_id"]
    assert target_hit["graph_provenance"][0]["evidence_text"] == "Sửa đổi, bổ sung khoản 1 Điều 252"
    assert any(node["id"] == "article:31-2024-QH15:252" for node in graph.to_dict()["nodes"])


def test_graph_bounds_hops_and_expansion_count() -> None:
    source = _chunk("a", "43-2024-QH15", "Điều 1", "Thay thế Điều 252.", "Khoản 2")
    target = _chunk("b", "31-2024-QH15", "Điều 252", "Đích", "Khoản 1")
    stub = StubRetriever([{
        "chunk_id": "a", "text": source["text"], "metadata": source["metadata"],
        "rank": 1, "rrf_score": 0.02,
    }])
    result = GraphRetriever(stub, [source, target], GraphConfig(max_expanded_chunks=0)).search("x", 2)
    assert [item["chunk_id"] for item in result] == ["a"]


def test_replacement_relation_has_distinct_label() -> None:
    source = _chunk("a", "43-2024-QH15", "Điều 1", "Thay thế khoản 1 Điều 252 như sau.", "Khoản 1")
    target = _chunk("b", "31-2024-QH15", "Điều 252", "Đích", "Khoản 1")
    graph = GraphRetriever(StubRetriever([]), [source, target])
    assert any(edge[2] == "replaces_article" for edge in graph._extract_legal_edges(source))


def test_same_clause_expansion_preserves_version_isolation() -> None:
    first = _chunk("c1", "31-2024-QH15", "Điều 1", "Khoản một.", "Khoản 1")
    sibling = _chunk("c2", "31-2024-QH15", "Điều 1", "Điểm a.", "Khoản 1")
    legacy = _chunk("old", "45-2013-QH13", "Điều 1", "Luật cũ.", "Khoản 1")
    stub = StubRetriever([{
        "chunk_id": "c1", "text": first["text"], "metadata": first["metadata"],
        "rank": 1, "rrf_score": 0.02,
    }])
    hits = GraphRetriever(stub, [first, sibling, legacy]).search("Điều 1", top_k=3)
    assert "same_clause" in next(item for item in hits if item["chunk_id"] == "c2")["graph_relations"]
    assert {item["chunk_id"] for item in filter_results_by_version(hits, "Điều 1 hiện nay")} == {"c1", "c2"}


def test_graph_ablation_reports_retrieval_and_optional_human_scores() -> None:
    chunks = [
        _chunk("a", "43-2024-QH15", "Điều 1", "Sửa đổi khoản 1 Điều 252."),
        _chunk("b", "31-2024-QH15", "Điều 252", "Ngày có hiệu lực."),
    ]
    baseline = StubRetriever([{
        "chunk_id": "a", "metadata": chunks[0]["metadata"], "text": chunks[0]["text"],
    }])
    graph = StubRetriever([{
        "chunk_id": "a", "metadata": chunks[0]["metadata"], "text": chunks[0]["text"],
    }, {
        "chunk_id": "b", "metadata": chunks[1]["metadata"], "text": chunks[1]["text"],
    }])
    case = {
        "question_id": "q1", "question": "Luật 43 thay đổi gì?",
        "relevant_units": [
            {"document_id": "43-2024-QH15", "article": "Điều 1"},
            {"document_id": "31-2024-QH15", "article": "Điều 252"},
        ],
    }
    report = evaluate_graph_ablation(
        [case], chunks, baseline, graph, top_k=2,
        answer_judgments=[{
            "question_id": "q1", "answer_correct": True, "citation_supported": False,
            "cited_chunk_ids": ["a", "b"],
        }],
    )
    assert report["systems"]["hybrid_graph"]["recall@2"] == 1.0
    assert report["systems"]["hybrid"]["recall@2"] == 0.5
    assert report["human_answer_and_citation_judgments"]["citation_supported_rate"] == 0.0
    assert report["citation_source_metrics"]["gold_unit_citation_precision"] == 1.0
    assert report["citation_source_metrics"]["gold_unit_citation_recall"] == 1.0


@pytest.mark.parametrize("bad_config", [
    {"max_hops": -1}, {"max_expanded_chunks": -1}, {"hop_decay": 0},
])
def test_invalid_graph_limits_are_rejected(bad_config: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        GraphConfig(**bad_config)
