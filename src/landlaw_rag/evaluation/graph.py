"""Retrieval and optional human-judgment metrics for graph ablations."""

from __future__ import annotations

import math
from time import perf_counter
from typing import Any, Mapping, Sequence


def _selector_matches(chunk: Mapping[str, Any], selector: Mapping[str, Any]) -> bool:
    metadata = chunk.get("metadata", {})
    for field in ("document_id", "article", "clause", "point"):
        expected = selector.get(field)
        if expected is not None and str(metadata.get(field) or "").casefold() != str(expected).casefold():
            return False
    text_contains = selector.get("text_contains")
    return text_contains is None or str(text_contains).casefold() in str(chunk.get("text") or "").casefold()


def evaluate_graph_ablation(
    cases: Sequence[Mapping[str, Any]],
    chunks: Sequence[Mapping[str, Any]],
    baseline: Any,
    graph_retriever: Any,
    *,
    top_k: int = 8,
    answer_judgments: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compare Hybrid and Hybrid+Graph on shared query/source labels.

    Gold labels are legal-unit selectors, not brittle generated chunk IDs.
    Optional answer judgments must be independently reviewed by a human and
    contain `question_id`, `answer_correct`, and `citation_supported` booleans.
    """
    if top_k <= 0:
        raise ValueError("top_k must be positive")
    results: list[dict[str, Any]] = []
    totals: dict[str, dict[str, float]] = {"hybrid": {}, "hybrid_graph": {}}
    chunk_rows = list(chunks)

    # Warm both systems so first-call model/tokenizer initialization does not
    # bias the paired retrieval latency comparison.
    if cases:
        warmup_query = str(cases[0]["question"])
        baseline.search(warmup_query, top_k=top_k)
        graph_retriever.search(warmup_query, top_k=top_k)

    for case in cases:
        selectors = case.get("relevant_units", [])
        relevant_units = [
            selector for selector in selectors
            if any(_selector_matches(chunk, selector) for chunk in chunk_rows)
        ]
        if not relevant_units:
            raise ValueError(f"No chunks match gold labels for {case.get('question_id')}")
        query = str(case["question"])
        tick = perf_counter()
        baseline_hits = baseline.search(query, top_k=top_k)
        hybrid_ms = (perf_counter() - tick) * 1000
        tick = perf_counter()
        graph_hits = graph_retriever.search(query, top_k=top_k)
        graph_ms = (perf_counter() - tick) * 1000
        def hit_matches(hit: Mapping[str, Any], selector: Mapping[str, Any]) -> bool:
            return _selector_matches(hit, selector)

        def unit_metrics(hits: Sequence[Mapping[str, Any]]) -> dict[str, float]:
            matched: set[int] = set()
            relevance: list[int] = []
            first = None
            for rank, hit in enumerate(hits[:top_k], 1):
                newly_found = next((
                    index for index, selector in enumerate(relevant_units)
                    if index not in matched and hit_matches(hit, selector)
                ), None)
                relevance.append(int(newly_found is not None))
                if newly_found is not None:
                    matched.add(newly_found)
                    if first is None:
                        first = rank
            dcg = sum(value / math.log2(rank + 1) for rank, value in enumerate(relevance, 1))
            ideal = sum(1 / math.log2(rank + 1) for rank in range(1, min(len(relevant_units), top_k) + 1))
            return {
                f"recall@{top_k}": len(matched) / len(relevant_units),
                f"precision@{top_k}": sum(relevance) / top_k,
                f"mrr@{top_k}": 1 / first if first else 0.0,
                f"ndcg@{top_k}": dcg / ideal if ideal else 0.0,
            }

        row: dict[str, Any] = {
            "question_id": case["question_id"],
            "relation_focus": case.get("relation_focus", "general"),
            "query": query,
            "gold_unit_count": len(relevant_units),
            "hybrid": unit_metrics(baseline_hits),
            "hybrid_graph": unit_metrics(graph_hits),
            "latency_ms": {"hybrid": hybrid_ms, "hybrid_graph": graph_ms},
            "hybrid_chunk_ids": [str(x["chunk_id"]) for x in baseline_hits],
            "hybrid_graph_chunk_ids": [str(x["chunk_id"]) for x in graph_hits],
            "graph_hit_annotations": [{
                "chunk_id": str(hit["chunk_id"]),
                "relations": hit.get("graph_relations", []),
                "hops": hit.get("graph_hops", 0),
                "provenance": hit.get("graph_provenance", []),
            } for hit in graph_hits],
            "graph_relations": sorted({
                relation for hit in graph_hits for relation in hit.get("graph_relations", [])
            }),
            "graph_provenance": [
                evidence for hit in graph_hits for evidence in hit.get("graph_provenance", [])
            ],
        }
        for system in totals:
            for metric, value in row[system].items():
                totals[system][metric] = totals[system].get(metric, 0.0) + value
        results.append(row)

    count = len(results)
    summary = {
        system: {metric: value / count for metric, value in values.items()}
        for system, values in totals.items()
    }
    groups: dict[str, dict[str, dict[str, float]]] = {}
    for focus in sorted({str(row["relation_focus"]) for row in results}):
        group_rows = [row for row in results if str(row["relation_focus"]) == focus]
        groups[focus] = {}
        for system in totals:
            metrics = group_rows[0][system]
            groups[focus][system] = {
                key: sum(row[system][key] for row in group_rows) / len(group_rows)
                for key in metrics
            }
        groups[focus]["latency_ms"] = {
            system: sum(row["latency_ms"][system] for row in group_rows) / len(group_rows)
            for system in totals
        }
    summary["latency_ms"] = {
        system: sum(row["latency_ms"][system] for row in results) / count
        for system in totals
    }
    judgment_rows = list(answer_judgments or [])
    reviewed_rows = [
        row for row in judgment_rows
        if row.get("answer_correct") is not None or row.get("citation_supported") is not None
    ]
    judgments: dict[str, Any] = {"reviewed_count": len(reviewed_rows)}
    if judgment_rows:
        for key in ("answer_correct", "citation_supported"):
            marked = [row[key] for row in judgment_rows if row.get(key) is not None]
            judgments[f"{key}_rate"] = (
                sum(bool(value) for value in marked) / len(marked) if marked else None
            )
    cases_by_id = {str(case["question_id"]): case for case in cases}
    chunks_by_id = {str(chunk["chunk_id"]): chunk for chunk in chunk_rows}
    citation_precision: list[float] = []
    citation_recall: list[float] = []
    for judgment in judgment_rows:
        cited_ids = [str(value) for value in judgment.get("cited_chunk_ids", [])]
        case = cases_by_id.get(str(judgment.get("question_id")))
        if not cited_ids or case is None:
            continue
        selectors = case.get("relevant_units", [])
        covered = {
            index for index, selector in enumerate(selectors)
            if any(
                chunk_id in chunks_by_id and _selector_matches(chunks_by_id[chunk_id], selector)
                for chunk_id in cited_ids
            )
        }
        relevant_citations = sum(
            any(_selector_matches(chunks_by_id[cid], selector) for selector in selectors)
            for cid in cited_ids if cid in chunks_by_id
        )
        citation_precision.append(relevant_citations / len(cited_ids))
        citation_recall.append(len(covered) / len(selectors) if selectors else 0.0)
    citation_source_metrics = {
        "reviewed_answer_count": len(citation_precision),
        "gold_unit_citation_precision": (
            sum(citation_precision) / len(citation_precision) if citation_precision else None
        ),
        "gold_unit_citation_recall": (
            sum(citation_recall) / len(citation_recall) if citation_recall else None
        ),
        "note": "Overlap with labeled legal units; claim-level support still requires human review.",
    }
    return {
        "schema_version": 1,
        "top_k": top_k,
        "query_count": count,
        "systems": summary,
        "by_relation_focus": groups,
        "human_answer_and_citation_judgments": judgments,
        "citation_source_metrics": citation_source_metrics,
        "cases": results,
    }
