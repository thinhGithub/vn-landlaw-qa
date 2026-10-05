"""Citation pháp lý deterministic từ metadata của evidence đã dùng."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence


class CitationValidationError(ValueError):
    """Citation yêu cầu một chunk không thuộc context/evidence."""


@dataclass(frozen=True)
class Citation:
    """Một nguồn pháp lý đã khử trùng và các chunk chứng minh nguồn đó."""

    number: int
    text: str
    chunk_ids: tuple[str, ...]

    @property
    def marker(self) -> str:
        return f"[{self.number}]"

    def render(self) -> str:
        return f"{self.marker} {self.text}"


@dataclass(frozen=True)
class ClaimSupport:
    """Ánh xạ nội bộ giữa một ý trong câu trả lời và evidence hỗ trợ."""

    claim: str
    chunk_ids: tuple[str, ...]


@dataclass(frozen=True)
class ClaimCitationMapping:
    """Mapping đã validate từ claim tới citation và evidence cụ thể."""

    claim: str
    citation_ids: tuple[int, ...]
    chunk_ids: tuple[str, ...]


@dataclass(frozen=True)
class CitedAnswer:
    """Câu trả lời đã gắn nguồn cùng dữ liệu truy vết nội bộ."""

    text: str
    citations: tuple[Citation, ...]
    claim_supports: tuple[ClaimSupport, ...]
    claim_mappings: tuple[ClaimCitationMapping, ...] = ()


_SOURCE_TAG_RE = re.compile(r"\[Nguồn\s+(\d+)\]", flags=re.IGNORECASE)
_SOURCE_ONLY_RE = re.compile(r"(?:\[Nguồn\s+\d+\]\s*)+", flags=re.IGNORECASE)
_GROUPED_SOURCE_TAG_RE = re.compile(
    r"\[(?:Nguồn\s+\d+\s*,\s*)+Nguồn\s+\d+\]", flags=re.IGNORECASE
)


def _normalize_grouped_source_tags(answer: str) -> str:
    """Chuẩn hóa nhãn model đã chọn, không thêm hoặc suy đoán nguồn mới."""

    def expand(match: re.Match[str]) -> str:
        numbers = re.findall(r"Nguồn\s+(\d+)", match.group(0), flags=re.IGNORECASE)
        return " ".join(f"[Nguồn {number}]" for number in numbers)

    return _GROUPED_SOURCE_TAG_RE.sub(expand, answer)


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _chunk_id(chunk: Mapping[str, Any]) -> str:
    metadata = chunk.get("metadata") or {}
    if not isinstance(metadata, Mapping):
        metadata = {}
    return _clean(chunk.get("chunk_id") or metadata.get("chunk_id"))


def _metadata(chunk: Mapping[str, Any]) -> Mapping[str, Any]:
    metadata = chunk.get("metadata") or {}
    return metadata if isinstance(metadata, Mapping) else {}


def format_citation(metadata: Mapping[str, Any]) -> str:
    """Định dạng nguồn ngắn; không đưa tiêu đề/nội dung điều vào citation."""

    document = _clean(metadata.get("document_title") or metadata.get("document_id"))
    if not document:
        raise CitationValidationError("Metadata thiếu document_title/document_id")

    levels = [document]
    for field in ("article", "clause", "point"):
        value = _clean(metadata.get(field))
        if value:
            levels.append(value)
    return " → ".join(levels)


def _evidence_by_id(
    evidence: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Mapping[str, Any]], list[str]]:
    by_id: dict[str, Mapping[str, Any]] = {}
    order: list[str] = []
    for chunk in evidence:
        chunk_id = _chunk_id(chunk)
        if not chunk_id:
            raise CitationValidationError("Evidence thiếu chunk_id")
        if chunk_id not in by_id:
            by_id[chunk_id] = chunk
            order.append(chunk_id)
    return by_id, order


def build_citations(
    evidence: Sequence[Mapping[str, Any]],
    cited_chunk_ids: Iterable[str] | None = None,
) -> tuple[Citation, ...]:
    """Sinh citation từ một tập con hợp lệ của evidence, theo thứ tự ổn định."""

    by_id, evidence_order = _evidence_by_id(evidence)
    if cited_chunk_ids is None:
        selected_ids = evidence_order
    else:
        requested = {_clean(chunk_id) for chunk_id in cited_chunk_ids}
        requested.discard("")
        unknown = requested.difference(by_id)
        if unknown:
            joined = ", ".join(sorted(unknown))
            raise CitationValidationError(f"Chunk không thuộc context/evidence: {joined}")
        selected_ids = [chunk_id for chunk_id in evidence_order if chunk_id in requested]

    grouped: dict[str, list[str]] = {}
    for chunk_id in selected_ids:
        text = format_citation(_metadata(by_id[chunk_id]))
        grouped.setdefault(text, []).append(chunk_id)

    return tuple(
        Citation(number=index, text=text, chunk_ids=tuple(chunk_ids))
        for index, (text, chunk_ids) in enumerate(grouped.items(), start=1)
    )


def _append_marker(claim: str, markers: Sequence[str]) -> str:
    suffix = "".join(markers)
    return f"{claim.rstrip()} {suffix}" if suffix else claim.rstrip()


def cite_answer(
    answer: str,
    evidence: Sequence[Mapping[str, Any]],
    claim_supports: Sequence[ClaimSupport] | None = None,
    cited_chunk_ids: Iterable[str] | None = None,
) -> CitedAnswer:
    """Gắn marker theo claim và thêm danh mục căn cứ ở cuối câu trả lời.

    Nếu chỉ có một nguồn, nguồn chỉ xuất hiện trong mục ``Căn cứ pháp lý``.
    Với nhiều nguồn, caller truyền ``ClaimSupport`` để gắn marker sau đúng ý;
    hàm không tự suy đoán quan hệ claim–evidence.
    """

    clean_answer = answer.strip()
    supports = tuple(claim_supports or ())
    support_ids = [chunk_id for support in supports for chunk_id in support.chunk_ids]
    selected_ids = support_ids if supports else cited_chunk_ids
    citations = build_citations(evidence, selected_ids)

    rendered_answer = clean_answer
    if len(citations) > 1 and supports:
        marker_by_chunk = {
            chunk_id: citation.marker
            for citation in citations
            for chunk_id in citation.chunk_ids
        }
        for support in supports:
            if not support.claim or support.claim not in rendered_answer:
                raise CitationValidationError(
                    f"Claim không tồn tại trong câu trả lời: {support.claim!r}"
                )
            markers: list[str] = []
            for chunk_id in support.chunk_ids:
                marker = marker_by_chunk.get(_clean(chunk_id))
                if marker is None:
                    raise CitationValidationError(
                        f"Chunk không thuộc context/evidence: {chunk_id}"
                    )
                if marker not in markers:
                    markers.append(marker)
            rendered_answer = rendered_answer.replace(
                support.claim, _append_marker(support.claim, markers), 1
            )

    if citations:
        bibliography = "\n".join(citation.render() for citation in citations)
        rendered_answer = f"{rendered_answer}\n\nCăn cứ pháp lý:\n{bibliography}"

    return CitedAnswer(
        text=rendered_answer,
        citations=citations,
        claim_supports=supports,
    )


def cite_tagged_answer(
    answer: str,
    evidence: Sequence[Mapping[str, Any]],
) -> CitedAnswer:
    """Validate ``[Nguồn n]`` theo context rồi đổi thành inline citation.

    Mỗi dòng nội dung là một claim và phải kết thúc bằng ít nhất một nhãn nguồn.
    Dòng tiêu đề kết thúc bằng dấu hai chấm được phép không có nguồn.
    """

    clean_answer = _normalize_grouped_source_tags(answer.strip())
    if not clean_answer:
        raise CitationValidationError("Câu trả lời rỗng")

    source_ids: list[str] = []
    for chunk in evidence:
        chunk_id = _chunk_id(chunk)
        if not chunk_id:
            raise CitationValidationError("Evidence thiếu chunk_id")
        source_ids.append(chunk_id)

    normalized_lines: list[str] = []
    for raw_line in clean_answer.splitlines():
        line = raw_line.strip()
        if line and _SOURCE_ONLY_RE.fullmatch(line):
            previous = next(
                (
                    index
                    for index in range(len(normalized_lines) - 1, -1, -1)
                    if normalized_lines[index].strip()
                ),
                None,
            )
            if previous is None:
                raise CitationValidationError("Nhãn nguồn không có claim đứng trước")
            normalized_lines[previous] = f"{normalized_lines[previous].rstrip()} {line}"
            continue
        normalized_lines.append(raw_line)

    parsed_lines: list[tuple[str, tuple[str, ...]] | None] = []
    cited_chunk_ids: list[str] = []
    for raw_line in normalized_lines:
        line = raw_line.strip()
        if not line:
            parsed_lines.append(None)
            continue

        matches = list(_SOURCE_TAG_RE.finditer(line))
        if not matches:
            if line.endswith(":"):
                parsed_lines.append((line, ()))
                continue
            raise CitationValidationError(f"Claim thiếu nhãn [Nguồn n]: {line!r}")

        chunk_ids: list[str] = []
        for match in matches:
            source_number = int(match.group(1))
            if source_number < 1 or source_number > len(source_ids):
                raise CitationValidationError(
                    f"Nhãn nguồn không thuộc context: [Nguồn {source_number}]"
                )
            chunk_id = source_ids[source_number - 1]
            if chunk_id not in chunk_ids:
                chunk_ids.append(chunk_id)
            if chunk_id not in cited_chunk_ids:
                cited_chunk_ids.append(chunk_id)

        claim = _SOURCE_TAG_RE.sub("", line).rstrip()
        if not claim:
            raise CitationValidationError("Claim rỗng sau khi bỏ nhãn nguồn")
        parsed_lines.append((claim, tuple(chunk_ids)))

    citations = build_citations(evidence, cited_chunk_ids)
    citation_by_chunk = {
        chunk_id: citation
        for citation in citations
        for chunk_id in citation.chunk_ids
    }
    rendered_lines: list[str] = []
    mappings: list[ClaimCitationMapping] = []
    for parsed in parsed_lines:
        if parsed is None:
            rendered_lines.append("")
            continue
        claim, chunk_ids = parsed
        if not chunk_ids:
            rendered_lines.append(claim)
            continue
        claim_citations: list[Citation] = []
        for chunk_id in chunk_ids:
            citation = citation_by_chunk[chunk_id]
            if citation not in claim_citations:
                claim_citations.append(citation)
        rendered_lines.append(
            _append_marker(claim, [citation.marker for citation in claim_citations])
        )
        mappings.append(
            ClaimCitationMapping(
                claim=claim,
                citation_ids=tuple(citation.number for citation in claim_citations),
                chunk_ids=chunk_ids,
            )
        )

    bibliography = "\n".join(citation.render() for citation in citations)
    rendered_answer = "\n".join(rendered_lines).strip()
    if bibliography:
        rendered_answer = f"{rendered_answer}\n\nCăn cứ pháp lý:\n{bibliography}"
    return CitedAnswer(
        text=rendered_answer,
        citations=citations,
        claim_supports=(),
        claim_mappings=tuple(mappings),
    )
