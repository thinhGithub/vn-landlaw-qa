"""Hybrid retrieval bằng Reciprocal Rank Fusion cho Milestone 5."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Protocol

from .bm25 import BM25Index
from .vector import VectorIndex

DOCUMENT_ID_RE = re.compile(r"\b(\d{1,4})\s*[/-]\s*(\d{4})\s*[/-]\s*QH\s*(\d+)\b", re.IGNORECASE)
ARTICLE_RE = re.compile(r"\bđiều\s+(\d+[a-z]?)\b", re.IGNORECASE)
CLAUSE_RE = re.compile(r"\bkhoản\s+(\d+)\b", re.IGNORECASE)


class Retriever(Protocol):
    """Interface tối thiểu dùng chung cho các retriever."""

    def search(self, query: str, top_k: int) -> list[dict[str, Any]]:
        ...


@dataclass(frozen=True)
class HybridConfig:
    bm25_top_n: int = 20
    vector_top_n: int = 20
    final_top_k: int = 8
    rrf_k: int = 60
    explicit_version_boost: float = 0.020
    comparison_version_boost: float = 0.010
    current_version_boost: float = 0.005


def _normalize(value: Any) -> str:
    return " ".join(unicodedata.normalize("NFC", str(value or "")).lower().split())


def extract_legal_references(query: str) -> dict[str, str | None]:
    """Trích số hiệu văn bản, Điều và Khoản được nêu rõ trong query."""

    normalized = _normalize(query)
    document_match = DOCUMENT_ID_RE.search(normalized)
    article_match = ARTICLE_RE.search(normalized)
    clause_match = CLAUSE_RE.search(normalized)
    return {
        "document_id": f"{document_match.group(1)}-{document_match.group(2)}-QH{document_match.group(3)}" if document_match else None,
        "article": f"Điều {article_match.group(1)}" if article_match else None,
        "clause": f"Khoản {clause_match.group(1)}" if clause_match else None,
    }


def _exact_match_count(metadata: dict[str, Any], references: dict[str, str | None]) -> int:
    return sum(
        1 for field, expected in references.items()
        if expected is not None and _normalize(metadata.get(field)) == _normalize(expected)
    )


def metadata_year(metadata: dict[str, Any]) -> int | None:
    """Suy ra năm văn bản từ metadata, không phụ thuộc chunk_id."""

    raw_year = metadata.get("year")
    if raw_year is not None:
        match = re.search(r"\b(20\d{2})\b", str(raw_year))
        if match:
            return int(match.group(1))
    searchable = " ".join(
        str(metadata.get(field) or "") for field in ("document_id", "document_title")
    )
    match = re.search(r"\b(20\d{2})\b", searchable)
    return int(match.group(1)) if match else None


def detect_version_intent(query: str) -> dict[str, Any]:
    """Nhận diện phiên bản luật và ý định so sánh từ query."""

    normalized = _normalize(query)
    years = {int(year) for year in re.findall(r"\b(2013|2024)\b", normalized)}
    signals = ("so sánh", "khác nhau", "khác biệt", "đối chiếu")
    is_comparison = any(signal in normalized for signal in signals) or years == {2013, 2024}
    if is_comparison:
        return {"mode": "comparison", "target_years": {2013, 2024}, "mentioned_years": years}
    if years:
        return {"mode": "explicit", "target_years": years, "mentioned_years": years}
    return {"mode": "current_default", "target_years": {2024}, "mentioned_years": years}


def apply_version_boost(
    query: str,
    results: list[dict[str, Any]],
    *,
    explicit_boost: float = 0.020,
    comparison_boost: float = 0.010,
    current_boost: float = 0.005,
    top_k: int | None = None,
) -> list[dict[str, Any]]:
    """Cộng boost nhẹ theo phiên bản và giữ hai luật cho query so sánh."""

    intent = detect_version_intent(query)
    boost_by_mode = {
        "explicit": explicit_boost,
        "comparison": comparison_boost,
        "current_default": current_boost,
    }
    boosted: list[dict[str, Any]] = []
    for original in results:
        item = dict(original)
        year = metadata_year(item.get("metadata", {}))
        version_score = boost_by_mode[intent["mode"]] if year in intent["target_years"] else 0.0
        item["version_year"] = year
        item["version_intent"] = intent["mode"]
        item["version_score"] = round(version_score, 8)
        item["final_score"] = round(float(item.get("rrf_score", 0.0)) + version_score, 8)
        boosted.append(item)

    def rank_key(item: dict[str, Any]) -> tuple[Any, ...]:
        return (
            item.get("exact_match_count", 0), item["final_score"],
            item.get("bm25_score") if item.get("bm25_score") is not None else float("-inf"),
            item["chunk_id"],
        )

    boosted.sort(key=rank_key, reverse=True)
    if top_k is None:
        return boosted
    selected = boosted[:top_k]
    if intent["mode"] == "comparison" and top_k >= 2:
        required = [
            next((item for item in boosted if item["version_year"] == year), None)
            for year in (2013, 2024)
        ]
        selected = [item for item in required if item is not None]
        selected_ids = {item["chunk_id"] for item in selected}
        selected.extend(
            item for item in boosted
            if item["chunk_id"] not in selected_ids
        )
        selected = selected[:top_k]
        selected.sort(key=rank_key, reverse=True)
    return selected


class BM25Retriever:
    """Adapter chuẩn hóa output của BM25Index."""

    def __init__(self, index: BM25Index) -> None:
        self.index = index

    def search(self, query: str, top_k: int) -> list[dict[str, Any]]:
        return [{
            "chunk_id": item["chunk_id"], "text": item["text"],
            "metadata": item["metadata"], "score": float(item["score"]), "rank": rank,
        } for rank, item in enumerate(self.index.query(query, top_k=top_k), start=1)]


class VectorRetriever:
    """Adapter chuẩn hóa output của VectorIndex."""

    def __init__(self, index: VectorIndex) -> None:
        self.index = index

    def search(self, query: str, top_k: int) -> list[dict[str, Any]]:
        return [{
            "chunk_id": item["chunk_id"], "text": item["text"],
            "metadata": item["metadata"], "score": float(item["vector_score"]), "rank": rank,
        } for rank, item in enumerate(self.index.query(query, top_k=top_k), start=1)]


class HybridRetriever:
    """Hợp nhất BM25 và vector results bằng RRF, deduplicate theo chunk_id."""

    def __init__(self, bm25: Retriever, vector: Retriever, config: HybridConfig | None = None) -> None:
        self.bm25 = bm25
        self.vector = vector
        self.config = config or HybridConfig()
        if self.config.rrf_k < 0:
            raise ValueError("rrf_k không được âm")

    def search(self, query: str, top_k: int | None = None) -> list[dict[str, Any]]:
        query = query.strip()
        if not query:
            raise ValueError("Query không được rỗng")
        limit = top_k or self.config.final_top_k
        if limit <= 0:
            raise ValueError("top_k phải lớn hơn 0")

        source_results = (
            ("bm25", self.bm25.search(query, self.config.bm25_top_n)),
            ("vector", self.vector.search(query, self.config.vector_top_n)),
        )
        fused: dict[str, dict[str, Any]] = {}
        for source, results in source_results:
            for item in results:
                record = fused.setdefault(item["chunk_id"], {
                    "chunk_id": item["chunk_id"], "text": item["text"],
                    "metadata": item["metadata"], "bm25_score": None,
                    "vector_score": None, "bm25_rank": None, "vector_rank": None,
                    "rrf_score": 0.0,
                })
                record[f"{source}_score"] = item["score"]
                record[f"{source}_rank"] = item["rank"]
                record["rrf_score"] += 1.0 / (self.config.rrf_k + item["rank"])

        references = extract_legal_references(query)
        for record in fused.values():
            record["exact_match_count"] = _exact_match_count(record["metadata"], references)
        ranked = apply_version_boost(
            query,
            list(fused.values()),
            explicit_boost=self.config.explicit_version_boost,
            comparison_boost=self.config.comparison_version_boost,
            current_boost=self.config.current_version_boost,
            top_k=limit,
        )
        for rank, item in enumerate(ranked, start=1):
            item["rank"] = rank
            item["rrf_score"] = round(item["rrf_score"], 8)
        return ranked


def hybrid_search(query: str, top_k: int, retriever: HybridRetriever) -> list[dict[str, Any]]:
    """Function-style API thuận tiện cho notebook và pipeline M6."""

    return retriever.search(query, top_k=top_k)
