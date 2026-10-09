"""Graph-augmented retrieval over the parsed legal hierarchy.

The graph is built from chunk metadata at runtime, so it stays aligned with the
current corpus and needs no external graph database or extra dependency.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .hybrid import Retriever


class GraphRetriever:
    """Expand hybrid search hits through document/article/clause relationships."""

    def __init__(self, retriever: Retriever, chunks: list[dict[str, Any]]) -> None:
        self.retriever = retriever
        self.chunks = {str(chunk["chunk_id"]): chunk for chunk in chunks}
        self.by_article: dict[tuple[str, str], list[str]] = defaultdict(list)
        self.by_clause: dict[tuple[str, str, str], list[str]] = defaultdict(list)

        for chunk_id, chunk in self.chunks.items():
            metadata = chunk.get("metadata", {})
            document = self._norm(metadata.get("document_id"))
            article = self._norm(metadata.get("article"))
            clause = self._norm(metadata.get("clause"))
            if document and article:
                self.by_article[(document, article)].append(chunk_id)
                if clause:
                    self.by_clause[(document, article, clause)].append(chunk_id)

    @staticmethod
    def _norm(value: Any) -> str:
        return " ".join(str(value or "").casefold().split())

    def search(self, query: str, top_k: int) -> list[dict[str, Any]]:
        if top_k <= 0:
            raise ValueError("top_k phải lớn hơn 0")
        # Retrieve a wider seed set to give graph expansion several anchors.
        seeds = self.retriever.search(query, max(top_k * 3, 12))
        ranked: dict[str, dict[str, Any]] = {}

        def add(item: dict[str, Any], score: float, relation: str, anchor_rank: int) -> None:
            chunk_id = str(item["chunk_id"])
            current = ranked.get(chunk_id)
            if current is None:
                current = dict(item)
                current["graph_score"] = 0.0
                current["graph_relations"] = []
                current["_anchor_rank"] = anchor_rank
                ranked[chunk_id] = current
            current["graph_score"] += score
            current["_anchor_rank"] = min(current["_anchor_rank"], anchor_rank)
            if relation not in current["graph_relations"]:
                current["graph_relations"].append(relation)

        for rank, seed in enumerate(seeds, start=1):
            add(seed, 1.0 / (60 + rank), "hybrid_match", rank)
            metadata = seed.get("metadata", {})
            document = self._norm(metadata.get("document_id"))
            article = self._norm(metadata.get("article"))
            clause = self._norm(metadata.get("clause"))
            if not document or not article:
                continue

            same_clause = self.by_clause.get((document, article, clause), []) if clause else []
            same_article = self.by_article.get((document, article), [])
            for chunk_id in same_clause:
                neighbor = self.chunks[chunk_id]
                add(neighbor, 0.65 / (60 + rank), "same_clause", rank)
            for chunk_id in same_article:
                neighbor = self.chunks[chunk_id]
                neighbor_clause = self._norm(neighbor.get("metadata", {}).get("clause"))
                if neighbor_clause == clause:
                    continue
                add(neighbor, 0.35 / (60 + rank), "same_article", rank)

        output = sorted(
            ranked.values(),
            key=lambda item: (
                item["graph_score"],
                -item["_anchor_rank"],
                str(item["chunk_id"]),
            ),
            reverse=True,
        )[:top_k]
        for rank, item in enumerate(output, start=1):
            item["rank"] = rank
            item["graph_score"] = round(item["graph_score"], 8)
            item.pop("_anchor_rank", None)
        return output
