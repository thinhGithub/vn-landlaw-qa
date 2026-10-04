"""BM25 keyword retrieval có nhận biết metadata pháp lý."""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import re
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


INDEX_FORMAT_VERSION = 1
TOKEN_RE = re.compile(
    r"\d{1,4}[/-]\d{4}[/-]qh\d+|\d+[a-z]?|[^\W\d_]+",
    re.IGNORECASE | re.UNICODE,
)
DOCUMENT_ID_RE = re.compile(
    r"\b(\d{1,4})\s*[/-]\s*(\d{4})\s*[/-]\s*QH\s*(\d+)\b",
    re.IGNORECASE,
)
ARTICLE_RE = re.compile(r"\bđiều\s+(\d+[a-z]?)\b", re.IGNORECASE)
CLAUSE_RE = re.compile(r"\bkhoản\s+(\d+)\b", re.IGNORECASE)
POINT_RE = re.compile(r"\bđiểm\s+([a-zđ])\b", re.IGNORECASE)


@dataclass(frozen=True)
class BM25Config:
    k1: float = 1.5
    b: float = 0.75
    top_k: int = 10
    document_boost: float = 4.0
    article_boost: float = 10.0
    clause_boost: float = 6.0
    point_boost: float = 3.0


def normalize_for_search(text: str) -> str:
    """Chuẩn hóa bảo thủ, giữ chữ số và số hiệu văn bản pháp luật."""

    text = unicodedata.normalize("NFC", text).lower()
    text = text.replace("đ", "đ")  # Giữ phân biệt chữ đ trong tiếng Việt.
    return " ".join(text.split())


def tokenize_vi(text: str) -> list[str]:
    """Tokenize theo từ/số, gộp số hiệu như 31/2024/QH15 thành một token."""

    return [match.group(0).lower().replace("-", "/") for match in TOKEN_RE.finditer(normalize_for_search(text))]


def _chunks_sha256(chunks_path: Path) -> str:
    digest = hashlib.sha256()
    with chunks_path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_parsing_report(report_path: Path) -> None:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    warnings = [
        f"{item.get('document_id')}: {warning}"
        for item in report
        for warning in item.get("warnings", [])
    ]
    if warnings:
        preview = "\n".join(warnings[:10])
        raise ValueError(f"Parsing report còn cảnh báo, dừng build BM25:\n{preview}")


class BM25Index:
    """BM25 index có thể build, save, load và query độc lập."""

    def __init__(
        self,
        documents: list[dict[str, Any]],
        document_frequencies: dict[str, int],
        average_document_length: float,
        config: BM25Config | None = None,
        build_info: dict[str, Any] | None = None,
    ) -> None:
        self.documents = documents
        self.document_frequencies = document_frequencies
        self.average_document_length = average_document_length
        self.config = config or BM25Config()
        self.build_info = build_info or {}
        self._validate_index()

    @classmethod
    def build(
        cls,
        chunks_path: Path,
        parsing_report_path: Path,
        config: BM25Config | None = None,
    ) -> "BM25Index":
        validate_parsing_report(parsing_report_path)
        chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
        if not chunks:
            raise ValueError("chunks.json không có chunk")

        documents: list[dict[str, Any]] = []
        document_frequencies: Counter[str] = Counter()
        for chunk in chunks:
            text = str(chunk.get("text", "")).strip()
            chunk_id = str(chunk.get("chunk_id", "")).strip()
            metadata = chunk.get("metadata", {})
            if not text or not chunk_id:
                raise ValueError(f"Chunk thiếu text/chunk_id: {chunk!r}")
            # Index text cùng citation metadata để truy vấn Điều/Khoản vẫn có lexical signal.
            searchable = "\n".join(
                [
                    text,
                    str(metadata.get("document_id") or ""),
                    str(metadata.get("document_title") or ""),
                    str(metadata.get("article") or ""),
                    str(metadata.get("clause") or ""),
                    str(metadata.get("point") or ""),
                ]
            )
            tokens = tokenize_vi(searchable)
            term_frequencies = Counter(tokens)
            # Document frequency chỉ tăng một lần cho mỗi token trong một chunk,
            # không phải tăng theo tổng số lần token xuất hiện.
            document_frequencies.update(term_frequencies.keys())
            documents.append(
                {
                    "chunk_id": chunk_id,
                    "text": text,
                    "metadata": metadata,
                    "length": len(tokens),
                    "term_frequencies": dict(term_frequencies),
                }
            )

        average_length = sum(item["length"] for item in documents) / len(documents)
        return cls(
            documents=documents,
            document_frequencies=dict(document_frequencies),
            average_document_length=average_length,
            config=config,
            build_info={
                "format_version": INDEX_FORMAT_VERSION,
                "built_at_utc": datetime.now(timezone.utc).isoformat(),
                "chunks_sha256": _chunks_sha256(chunks_path),
                "chunk_count": len(documents),
                "source_chunks": str(chunks_path.resolve()),
                "source_parsing_report": str(parsing_report_path.resolve()),
            },
        )

    def _validate_index(self) -> None:
        ids = [item["chunk_id"] for item in self.documents]
        if len(ids) != len(set(ids)):
            raise ValueError("BM25 index chứa chunk_id trùng")
        if self.documents and self.average_document_length <= 0:
            raise ValueError("Độ dài trung bình của index không hợp lệ")

    def save(self, index_path: Path) -> None:
        index_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "format_version": INDEX_FORMAT_VERSION,
            "config": asdict(self.config),
            "build_info": self.build_info,
            "average_document_length": self.average_document_length,
            "document_frequencies": self.document_frequencies,
            "documents": self.documents,
        }
        with gzip.open(index_path, "wt", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, separators=(",", ":"))

    @classmethod
    def load(cls, index_path: Path) -> "BM25Index":
        with gzip.open(index_path, "rt", encoding="utf-8") as stream:
            payload = json.load(stream)
        if payload.get("format_version") != INDEX_FORMAT_VERSION:
            raise ValueError(
                f"BM25 index version không hỗ trợ: {payload.get('format_version')}"
            )
        return cls(
            documents=payload["documents"],
            document_frequencies=payload["document_frequencies"],
            average_document_length=float(payload["average_document_length"]),
            config=BM25Config(**payload["config"]),
            build_info=payload.get("build_info", {}),
        )

    def _idf(self, token: str) -> float:
        document_count = len(self.documents)
        frequency = self.document_frequencies.get(token, 0)
        return math.log(1.0 + (document_count - frequency + 0.5) / (frequency + 0.5))

    def _bm25_score(self, query_tokens: Iterable[str], document: dict[str, Any]) -> float:
        score = 0.0
        frequencies = document["term_frequencies"]
        length = document["length"]
        for token in set(query_tokens):
            term_frequency = frequencies.get(token, 0)
            if not term_frequency:
                continue
            denominator = term_frequency + self.config.k1 * (
                1.0 - self.config.b
                + self.config.b * length / self.average_document_length
            )
            score += self._idf(token) * term_frequency * (self.config.k1 + 1.0) / denominator
        return score

    def _extract_legal_filters(self, query: str) -> dict[str, str | None]:
        normalized = normalize_for_search(query)
        document_match = DOCUMENT_ID_RE.search(normalized)
        document_id = None
        if document_match:
            document_id = (
                f"{document_match.group(1)}-{document_match.group(2)}-"
                f"QH{document_match.group(3)}"
            )
        else:
            # Khi hỏi "Luật Đất đai 2013/2024", suy ra văn bản nếu năm là duy nhất.
            years = re.findall(r"\b(?:19|20)\d{2}\b", normalized)
            if "luật đất đai" in normalized and years:
                candidates = {
                    item["metadata"].get("document_id")
                    for item in self.documents
                    if years[0] in str(item["metadata"].get("document_id", ""))
                    and "luật đất đai" in normalize_for_search(
                        str(item["metadata"].get("document_title", ""))
                    )
                    and not normalize_for_search(
                        str(item["metadata"].get("document_title", ""))
                    ).startswith("luật số 43")
                }
                if len(candidates) == 1:
                    document_id = candidates.pop()
        article_match = ARTICLE_RE.search(normalized)
        clause_match = CLAUSE_RE.search(normalized)
        point_match = POINT_RE.search(normalized)
        return {
            "document_id": document_id,
            "article": f"Điều {article_match.group(1)}" if article_match else None,
            "clause": f"Khoản {clause_match.group(1)}" if clause_match else None,
            "point": f"Điểm {point_match.group(1).lower()}" if point_match else None,
        }

    def _metadata_boost(
        self, metadata: dict[str, Any], filters: dict[str, str | None]
    ) -> tuple[float, dict[str, bool]]:
        matches = {
            key: bool(expected) and normalize_for_search(str(metadata.get(key) or ""))
            == normalize_for_search(str(expected))
            for key, expected in filters.items()
        }
        boost = 0.0
        if matches["document_id"]:
            boost += self.config.document_boost
        if matches["article"]:
            boost += self.config.article_boost
        if matches["clause"]:
            boost += self.config.clause_boost
        if matches["point"]:
            boost += self.config.point_boost
        return boost, matches

    def query(self, query: str, top_k: int | None = None) -> list[dict[str, Any]]:
        """Trả Top-k gồm chunk_id, BM25 score, final score, text và metadata."""

        query = query.strip()
        if not query:
            raise ValueError("Query không được rỗng")
        query_tokens = tokenize_vi(query)
        if not query_tokens:
            raise ValueError("Query không tạo được token")
        filters = self._extract_legal_filters(query)
        results: list[dict[str, Any]] = []
        for document in self.documents:
            bm25_score = self._bm25_score(query_tokens, document)
            metadata_boost, matches = self._metadata_boost(document["metadata"], filters)
            final_score = bm25_score + metadata_boost
            if final_score <= 0:
                continue
            results.append(
                {
                    "chunk_id": document["chunk_id"],
                    "bm25_score": round(bm25_score, 6),
                    "metadata_boost": round(metadata_boost, 6),
                    "score": round(final_score, 6),
                    "text": document["text"],
                    "metadata": document["metadata"],
                    "exact_matches": matches,
                }
            )
        results.sort(
            key=lambda item: (item["score"], item["bm25_score"], item["chunk_id"]),
            reverse=True,
        )
        return results[: top_k or self.config.top_k]
