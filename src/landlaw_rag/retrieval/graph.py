"""Bounded graph expansion over Vietnamese legal chunks.

The graph is materialized in memory from parsed chunk metadata and explicit
text references. Every traversable edge records its source chunk and evidence
span so graph-added context can be audited and cited deterministically.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
import json
import re
from pathlib import Path
from typing import Any

from .hybrid import Retriever


@dataclass(frozen=True)
class GraphConfig:
    """Limits and relation weights for graph expansion."""

    seed_multiplier: int = 3
    min_seed_k: int = 12
    max_hops: int = 1
    max_expanded_chunks: int = 24
    max_neighbors_per_node: int = 8
    hop_decay: float = 0.7
    relation_weights: dict[str, float] = field(default_factory=lambda: {
        "same_clause": 0.65,
        "same_article": 0.35,
        "amends_article": 0.75,
        "replaces_article": 0.80,
        "references_article": 0.50,
    })
    allowed_relations: tuple[str, ...] = (
        "same_clause", "same_article", "amends_article",
        "replaces_article", "references_article",
    )

    def __post_init__(self) -> None:
        if self.seed_multiplier < 1 or self.min_seed_k < 1:
            raise ValueError("seed limits must be positive")
        if self.max_hops < 0 or self.max_expanded_chunks < 0:
            raise ValueError("graph expansion limits cannot be negative")
        if self.max_neighbors_per_node < 1:
            raise ValueError("max_neighbors_per_node must be positive")
        if not 0 < self.hop_decay <= 1:
            raise ValueError("hop_decay must be in (0, 1]")
        if any(weight < 0 for weight in self.relation_weights.values()):
            raise ValueError("relation weights cannot be negative")


class GraphRetriever:
    """Expand hybrid retrieval through legal hierarchy and explicit references.

    Supported legal edges are `amends_article`, `replaces_article`, and
    `references_article`; hierarchy-derived edges are `same_clause` and
    `same_article`. Cross-document extraction is conservative and corpus-aware.
    """

    SUPPORTED_DOCS = {
        "31-2024-QH15", "43-2024-QH15", "45-2013-QH13", "254-2025-QH15"
    }
    _ARTICLE_REF = re.compile(r"\bĐiều\s+(\d+[a-z]?)\b", re.IGNORECASE)
    _AMENDMENT_TARGET = re.compile(
        r"(?:sửa đổi|bổ sung)[^\n.]{0,100}?\bĐiều\s+(\d+[a-z]?)\b",
        re.IGNORECASE,
    )
    _REPLACEMENT_TARGET = re.compile(
        r"(?:thay thế|được thay thế)[^\n.]{0,100}?\bĐiều\s+(\d+[a-z]?)\b",
        re.IGNORECASE,
    )
    _LAND_LAW_ARTICLES = re.compile(
        r"((?:Điều\s+\d+[a-z]?\s*,?\s*)+)\s+(?:của\s+)?Luật\s+Đất\s+đai"
        r"(?:\s+số\s+(\d{1,4})\s*/\s*(\d{4})\s*/\s*QH\s*(\d+))?",
        re.IGNORECASE,
    )

    def __init__(
        self,
        retriever: Retriever,
        chunks: list[dict[str, Any]],
        config: GraphConfig | None = None,
    ) -> None:
        self.retriever = retriever
        self.config = config or GraphConfig()
        self.chunks = {str(chunk["chunk_id"]): chunk for chunk in chunks}
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: list[dict[str, Any]] = []
        self._adjacency: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.by_article: dict[tuple[str, str], list[str]] = defaultdict(list)
        self.by_clause: dict[tuple[str, str, str], list[str]] = defaultdict(list)
        self.by_point: dict[tuple[str, str, str, str], list[str]] = defaultdict(list)
        self.by_document_article: dict[tuple[str, str], list[str]] = defaultdict(list)
        self._build()

    @staticmethod
    def _norm(value: Any) -> str:
        return " ".join(str(value or "").casefold().split())

    @staticmethod
    def _article_number(value: Any) -> str:
        match = re.search(r"(\d+[a-z]?)", str(value or ""), re.IGNORECASE)
        return match.group(1).casefold() if match else ""

    @staticmethod
    def _node_id(kind: str, *parts: Any) -> str:
        return ":".join((kind, *(str(part) for part in parts if part is not None)))

    @staticmethod
    def _doc_id(chunk: dict[str, Any]) -> str:
        return str(chunk.get("metadata", {}).get("document_id") or "").upper()

    def _add_node(self, node_id: str, kind: str, **properties: Any) -> None:
        self.nodes.setdefault(node_id, {"id": node_id, "type": kind, **properties})

    def _add_edge(
        self,
        source: str,
        target: str,
        relation: str,
        evidence: dict[str, Any],
        *,
        traversable: bool = True,
    ) -> None:
        edge = {
            "source": source,
            "target": target,
            "relation": relation,
            "evidence": evidence,
            "traversable": traversable,
        }
        self.edges.append(edge)
        if traversable:
            self._adjacency[source].append(edge)

    def _build(self) -> None:
        for chunk_id, chunk in self.chunks.items():
            meta = chunk.get("metadata", {})
            doc = str(meta.get("document_id") or "")
            article = self._article_number(meta.get("article"))
            clause = self._article_number(meta.get("clause"))
            point = str(meta.get("point") or "").strip().casefold()
            source_file = meta.get("source_file")

            chunk_node = self._node_id("chunk", chunk_id)
            doc_node = self._node_id("document", doc)
            self._add_node(chunk_node, "chunk", chunk_id=chunk_id, source_file=source_file)
            self._add_node(doc_node, "document", document_id=doc)
            parent = doc_node
            if article:
                article_node = self._node_id("article", doc, article)
                self._add_node(article_node, "article", document_id=doc, article=article)
                self._add_edge(parent, article_node, "contains", {
                    "source_file": source_file, "metadata_field": "article",
                    "source_chunk_id": chunk_id,
                }, traversable=False)
                parent = article_node
                self.by_article[(self._norm(doc), self._norm(meta.get("article")))].append(chunk_id)
                self.by_document_article[(self._norm(doc), article)].append(chunk_id)
            if clause:
                clause_node = self._node_id("clause", doc, article, clause)
                self._add_node(clause_node, "clause", document_id=doc, article=article, clause=clause)
                self._add_edge(parent, clause_node, "contains", {
                    "source_file": source_file, "metadata_field": "clause",
                    "source_chunk_id": chunk_id,
                }, traversable=False)
                parent = clause_node
                self.by_clause[(self._norm(doc), self._norm(meta.get("article")), self._norm(meta.get("clause")))].append(chunk_id)
            if point:
                point_node = self._node_id("point", doc, article, clause, point)
                self._add_node(point_node, "point", document_id=doc, article=article, clause=clause, point=point)
                self._add_edge(parent, point_node, "contains", {
                    "source_file": source_file, "metadata_field": "point",
                    "source_chunk_id": chunk_id,
                }, traversable=False)
                parent = point_node
                self.by_point[(self._norm(doc), self._norm(meta.get("article")), self._norm(meta.get("clause")), point)].append(chunk_id)
            self._add_edge(parent, chunk_node, "has_chunk", {
                "source_file": source_file, "source_chunk_id": chunk_id,
                "metadata": {key: meta.get(key) for key in ("document_id", "article", "clause", "point")},
            }, traversable=False)

        # Chunk-to-chunk adjacency is explicit and auditable while the full
        # document → article → clause → point → chunk hierarchy remains intact.
        for (doc, article, clause), members in self.by_clause.items():
            self._connect_peers(members, "same_clause", {"document_id": doc, "article": article, "clause": clause})
        for (doc, article), members in self.by_article.items():
            self._connect_peers(members, "same_article", {"document_id": doc, "article": article})

        for chunk_id, chunk in self.chunks.items():
            for target_doc, target_article, relation, provenance in self._extract_legal_edges(chunk):
                target_ids = self.by_document_article.get((self._norm(target_doc), target_article), [])
                for target_id in target_ids:
                    self._add_edge(
                        self._node_id("chunk", chunk_id),
                        self._node_id("chunk", target_id),
                        relation,
                        {"source_chunk_id": chunk_id, "target_chunk_id": target_id, **provenance},
                    )

    def _connect_peers(self, members: list[str], relation: str, basis: dict[str, Any]) -> None:
        for source in members:
            for target in members:
                if source == target:
                    continue
                self._add_edge(
                    self._node_id("chunk", source), self._node_id("chunk", target), relation,
                    {"source_chunk_id": source, "target_chunk_id": target,
                     "source_file": self.chunks[source].get("metadata", {}).get("source_file"),
                     "basis": basis},
                )

    @classmethod
    def _extract_legal_edges(
        cls, chunk: dict[str, Any]
    ) -> list[tuple[str, str, str, dict[str, Any]]]:
        """Return resolvable legal references with exact source spans."""
        metadata = chunk.get("metadata", {})
        source_doc = cls._doc_id(chunk)
        text = str(chunk.get("text") or chunk.get("content") or "")
        results: list[tuple[str, str, str, dict[str, Any]]] = []

        if source_doc == "43-2024-QH15" and cls._article_number(metadata.get("article")) == "1":
            for match in cls._AMENDMENT_TARGET.finditer(text):
                results.append((
                    "31-2024-QH15", match.group(1).casefold(), "amends_article",
                    {"source_file": metadata.get("source_file"),
                     "source_span": [match.start(), match.end()], "evidence_text": match.group(0)},
                ))
            for match in cls._REPLACEMENT_TARGET.finditer(text):
                results.append((
                    "31-2024-QH15", match.group(1).casefold(), "replaces_article",
                    {"source_file": metadata.get("source_file"),
                     "source_span": [match.start(), match.end()], "evidence_text": match.group(0)},
                ))

        if source_doc == "254-2025-QH15":
            for match in cls._LAND_LAW_ARTICLES.finditer(text):
                target_doc = (
                    f"{match.group(2)}-{match.group(3)}-QH{match.group(4)}"
                    if match.group(2) else "31-2024-QH15"
                )
                if target_doc not in cls.SUPPORTED_DOCS:
                    continue
                for article_match in cls._ARTICLE_REF.finditer(match.group(1)):
                    # Keep offsets in the full source chunk, not just the capture group.
                    start = match.start(1) + article_match.start()
                    end = match.start(1) + article_match.end()
                    results.append((
                        target_doc, article_match.group(1).casefold(), "references_article",
                        {"source_file": metadata.get("source_file"),
                         "source_span": [start, end], "evidence_text": text[start:end]},
                    ))
        # Duplicate chunk fragments can repeat the article heading; retain one edge per target.
        unique: dict[tuple[str, str, str, str], tuple[str, str, str, dict[str, Any]]] = {}
        for target_doc, article, relation, evidence in results:
            unique.setdefault((target_doc, article, relation, evidence["evidence_text"]),
                              (target_doc, article, relation, evidence))
        return list(unique.values())

    def to_dict(self) -> dict[str, Any]:
        """Export a JSON-serializable graph snapshot for inspection."""
        return {"schema_version": 1, "nodes": list(self.nodes.values()), "edges": self.edges}

    def save(self, path: str | Path) -> None:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def search(self, query: str, top_k: int) -> list[dict[str, Any]]:
        if top_k <= 0:
            raise ValueError("top_k phải lớn hơn 0")
        seed_k = max(top_k * self.config.seed_multiplier, self.config.min_seed_k)
        seeds = self.retriever.search(query, seed_k)
        ranked: dict[str, dict[str, Any]] = {}
        queue: deque[tuple[str, int, float, int]] = deque()

        for rank, seed in enumerate(seeds, start=1):
            chunk_id = str(seed["chunk_id"])
            hybrid_score = seed.get("final_score", seed.get("rrf_score", seed.get("score")))
            if hybrid_score is None:
                hybrid_score = 1.0 / rank
            try:
                score = max(float(hybrid_score), 0.0)
            except (TypeError, ValueError):
                score = 1.0 / rank
            # Rank signal keeps BM25/vector adapters usable even if they expose
            # incomparable native score scales.
            score += 1.0 / (60 + rank)
            item = dict(seed)
            item.update({
                "graph_score": score,
                "graph_relations": ["hybrid_match"],
                "graph_provenance": [],
                "graph_hops": 0,
            })
            ranked[chunk_id] = item
            queue.append((chunk_id, 0, score, rank))

        expanded = 0
        while queue and expanded < self.config.max_expanded_chunks:
            source_id, depth, source_score, anchor_rank = queue.popleft()
            if depth >= self.config.max_hops:
                continue
            source_node = self._node_id("chunk", source_id)
            neighbors: list[tuple[float, dict[str, Any], str]] = []
            for edge in self._adjacency.get(source_node, []):
                relation = edge["relation"]
                if relation not in self.config.allowed_relations:
                    continue
                weight = self.config.relation_weights.get(relation, 0.0)
                if weight <= 0:
                    continue
                candidate_id = edge["target"].removeprefix("chunk:")
                if candidate_id not in self.chunks:
                    continue
                candidate_score = source_score * weight * (self.config.hop_decay ** depth)
                neighbors.append((candidate_score, edge, candidate_id))
            neighbors.sort(key=lambda entry: (-entry[0], entry[2]))
            for candidate_score, edge, candidate_id in neighbors[:self.config.max_neighbors_per_node]:
                existing = ranked.get(candidate_id)
                if existing is not None:
                    if candidate_score > float(existing["graph_score"]):
                        existing["graph_score"] = candidate_score
                    if edge["relation"] not in existing["graph_relations"]:
                        existing["graph_relations"].append(edge["relation"])
                    existing["graph_provenance"].append(edge["evidence"])
                    continue
                chunk = self.chunks[candidate_id]
                item = dict(chunk)
                item["graph_score"] = candidate_score
                item["graph_relations"] = [edge["relation"]]
                item["graph_provenance"] = [edge["evidence"]]
                item["graph_hops"] = depth + 1
                item["anchor_rank"] = anchor_rank
                ranked[candidate_id] = item
                queue.append((candidate_id, depth + 1, candidate_score, anchor_rank))
                expanded += 1
                if expanded >= self.config.max_expanded_chunks:
                    break

        # Preserve the best hybrid anchors, then interleave graph evidence by
        # weighted relevance. Graph-added results keep their original chunk IDs.
        ordered = sorted(
            ranked.values(),
            key=lambda item: (
                float(item["graph_score"]),
                -int(item.get("anchor_rank", item.get("rank", 10**9))),
                str(item["chunk_id"]),
            ),
            reverse=True,
        )[:top_k]
        for rank, item in enumerate(ordered, start=1):
            item["rank"] = rank
            item["graph_score"] = round(float(item["graph_score"]), 8)
        return ordered
