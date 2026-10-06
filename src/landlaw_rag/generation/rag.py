"""Tiện ích dựng context và prompt evidence-grounded cho Local LLM RAG."""

from __future__ import annotations

import re
from typing import Any, Literal


INSUFFICIENT_EVIDENCE_MESSAGE = "Chưa đủ căn cứ trong dữ liệu truy xuất."

VersionIntent = Literal["current", "2013", "comparison"]

_COMPARISON_MARKERS = (
    "so sánh",
    "đối chiếu",
    "khác nhau",
    "khác biệt",
    "thay đổi",
    "điểm mới",
    "2013 và 2024",
    "2013 với 2024",
    "2024 và 2013",
    "2024 với 2013",
)


def detect_version_intent(query: str) -> VersionIntent:
    """Xác định phiên bản luật cần dùng từ chính câu hỏi."""

    normalized = re.sub(r"\s+", " ", query.lower()).strip()
    if any(marker in normalized for marker in _COMPARISON_MARKERS):
        return "comparison"
    if "2013" in normalized or "45/2013/qh13" in normalized:
        return "2013"
    return "current"


def filter_results_by_version(
    results: list[dict[str, Any]], query: str
) -> list[dict[str, Any]]:
    """Cô lập evidence hiện hành và Luật 2013 trước khi dựng prompt."""

    intent = detect_version_intent(query)
    if intent == "comparison":
        return results

    def is_2013(result: dict[str, Any]) -> bool:
        metadata = result.get("metadata", {})
        identity = " ".join(
            str(metadata.get(field) or "")
            for field in ("document_id", "document_title", "source_file")
        ).lower()
        return "45-2013-qh13" in identity or "45/2013/qh13" in identity

    if intent == "2013":
        return [result for result in results if is_2013(result)]
    return [result for result in results if not is_2013(result)]


def format_source(metadata: dict[str, Any]) -> str:
    """Định dạng đầy đủ cây pháp lý của một chunk."""

    article = str(metadata.get("article") or "").strip()
    article_title = str(metadata.get("article_title") or "").strip()
    if article and article_title:
        article = f"{article}. {article_title}"
    values = [
        str(metadata.get("document_title") or metadata.get("document_id") or "").strip(),
        str(metadata.get("chapter") or "").strip(),
        str(metadata.get("section") or "").strip(),
        article,
        str(metadata.get("clause") or "").strip(),
        str(metadata.get("point") or "").strip(),
    ]
    return " → ".join(value for value in values if value) or "Không rõ nguồn"


def _chunk_key(chunk: dict[str, Any]) -> str:
    metadata = chunk.get("metadata", {})
    fallback = (format_source(metadata), str(chunk.get("text") or chunk.get("content") or ""))
    return str(chunk.get("chunk_id") or metadata.get("chunk_id") or fallback)


def _article_key(chunk: dict[str, Any]) -> tuple[str, str] | None:
    metadata = chunk.get("metadata", {})
    document_id = str(metadata.get("document_id") or "").strip().lower()
    article = str(metadata.get("article") or "").strip().lower()
    if not document_id or not article:
        return None
    return document_id, article


def _context_block(result: dict[str, Any], position: int) -> str:
    text = str(result.get("text") or result.get("content") or "").strip()
    return (
        f"[Nguồn {position}]\n"
        f"Cấu trúc: {format_source(result.get('metadata', {}))}\n"
        f"Nội dung:\n{text}"
    )


def expand_article_context(
    results: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    max_tokens: int,
    tokenizer: Any | None = None,
) -> list[dict[str, Any]]:
    """Bổ sung Khoản/Điểm cùng Điều khi Điều đó có từ hai hit trở lên."""

    if max_tokens <= 0:
        raise ValueError("max_tokens phải lớn hơn 0")

    deduplicated: list[dict[str, Any]] = []
    seen: set[str] = set()
    for result in results:
        key = _chunk_key(result)
        if key not in seen:
            deduplicated.append(result)
            seen.add(key)

    article_counts: dict[tuple[str, str], int] = {}
    for result in deduplicated:
        key = _article_key(result)
        if key is not None:
            article_counts[key] = article_counts.get(key, 0) + 1
    target_articles = {key for key, count in article_counts.items() if count >= 2}
    if not target_articles:
        return deduplicated

    corpus_positions = {_chunk_key(chunk): index for index, chunk in enumerate(chunks)}

    def token_count(items: list[dict[str, Any]]) -> int:
        rendered = "\n\n".join(
            _context_block(item, position)
            for position, item in enumerate(items, start=1)
        )
        if tokenizer is None:
            return len(rendered.split())
        return len(tokenizer.encode(rendered, add_special_tokens=False))

    selected = list(deduplicated)
    ordered_targets = sorted(
        target_articles,
        key=lambda key: next(
            index for index, result in enumerate(deduplicated) if _article_key(result) == key
        ),
    )
    for article_key in ordered_targets:
        hit_positions = [
            corpus_positions.get(_chunk_key(result), 0)
            for result in deduplicated
            if _article_key(result) == article_key
        ]
        siblings = [chunk for chunk in chunks if _article_key(chunk) == article_key]
        siblings.sort(
            key=lambda chunk: (
                min(
                    abs(corpus_positions.get(_chunk_key(chunk), 0) - hit)
                    for hit in hit_positions
                ),
                corpus_positions.get(_chunk_key(chunk), 0),
            )
        )
        for sibling in siblings:
            sibling_key = _chunk_key(sibling)
            if sibling_key in seen:
                continue
            expanded = dict(sibling)
            expanded["text"] = str(sibling.get("text") or sibling.get("content") or "")
            expanded.update({"expanded": True, "rank": None, "final_score": None})
            if token_count(selected + [expanded]) <= max_tokens:
                selected.append(expanded)
                seen.add(sibling_key)

    # Đặt các Khoản/Điểm cùng Điều cạnh nhau theo thứ tự trong corpus.
    ordered: list[dict[str, Any]] = []
    emitted_articles: set[tuple[str, str]] = set()
    for result in deduplicated:
        article_key = _article_key(result)
        if article_key not in target_articles:
            ordered.append(result)
        elif article_key not in emitted_articles:
            group = [item for item in selected if _article_key(item) == article_key]
            group.sort(key=lambda item: corpus_positions.get(_chunk_key(item), 10**12))
            ordered.extend(group)
            emitted_articles.add(article_key)
    return ordered


def build_context(
    results: list[dict[str, Any]],
    tokenizer: Any,
    max_context_tokens: int = 6000,
) -> tuple[str, list[dict[str, Any]]]:
    """Đóng gói Top-k chunks theo ngân sách token và giữ metadata đã sử dụng."""

    if max_context_tokens <= 0:
        raise ValueError("max_context_tokens phải lớn hơn 0")
    blocks: list[str] = []
    used_results: list[dict[str, Any]] = []
    used_tokens = 0
    for position, result in enumerate(results, start=1):
        block = _context_block(result, position)
        token_ids = tokenizer.encode(block, add_special_tokens=False)
        remaining = max_context_tokens - used_tokens
        if remaining <= 0:
            break
        if len(token_ids) > remaining:
            if not blocks:
                blocks.append(tokenizer.decode(token_ids[:remaining], skip_special_tokens=True))
                used_results.append(result)
            break
        blocks.append(block)
        used_results.append(result)
        used_tokens += len(token_ids)
    return "\n\n".join(blocks), used_results


def build_messages(query: str, context: str) -> list[dict[str, str]]:
    """Tạo chat prompt buộc câu trả lời bám theo evidence được retrieve."""

    query = query.strip()
    if not query:
        raise ValueError("Query không được rỗng")
    intent = detect_version_intent(query)
    version_instruction = {
        "current": (
            "Câu hỏi không chỉ định năm: chỉ dùng quy định hiện hành từ Luật "
            "31/2024/QH15 và văn bản sửa đổi, bổ sung liên quan trong evidence; "
            "không dùng Luật Đất đai 2013."
        ),
        "2013": (
            "Câu hỏi yêu cầu Luật Đất đai 2013: chỉ dùng evidence thuộc Luật "
            "45/2013/QH13; không trộn quy định hiện hành."
        ),
        "comparison": (
            "Câu hỏi yêu cầu so sánh: tách rõ quy định năm 2013 và quy định "
            "hiện hành; không gán nội dung của phiên bản này cho phiên bản kia."
        ),
    }[intent]
    system_prompt = (
        "Bạn là trợ lý hỏi đáp pháp luật đất đai Việt Nam. "
        "Chỉ trả lời dựa trên thông tin xuất hiện trực tiếp trong EVIDENCE được cung cấp. "
        "Không bắt buộc sử dụng toàn bộ EVIDENCE; chỉ chọn các đoạn trực tiếp liên quan "
        "đến câu hỏi. Evidence được sử dụng phải phù hợp đúng chủ thể, hành vi, đối tượng "
        "và phạm vi pháp lý mà người dùng hỏi. Không trộn quy định dành cho chủ thể, hành "
        "vi, đối tượng hoặc trường hợp pháp lý khác nếu không cần thiết để trả lời. "
        "Không dùng kiến thức bên ngoài; không tự bổ sung ví dụ, điều kiện, trường hợp "
        "hoặc suy luận không được EVIDENCE hỗ trợ. Không nêu Điều, Khoản, Điểm, tên văn bản "
        "hoặc căn cứ pháp lý nếu thông tin đó không xuất hiện trong EVIDENCE. "
        f"{version_instruction} "
        "Nếu EVIDENCE thiếu, không liên quan, mâu thuẫn hoặc không đủ để trả lời, "
        f"hãy trả lời đúng nguyên văn: '{INSUFFICIENT_EVIDENCE_MESSAGE}' "
        "Không dùng các cụm từ mơ hồ như 'v.v.' hoặc 'etc.'. "
        "Trả lời ngắn gọn, rõ ràng, tập trung trực tiếp vào câu hỏi, bám sát EVIDENCE "
        "và không mở rộng sang vấn đề khác. Mỗi claim pháp lý phải nằm trên một dòng "
        "riêng và kết thúc bằng một hoặc nhiều nhãn [Nguồn n] đúng với đoạn EVIDENCE "
        "trực tiếp hỗ trợ claim đó. Dùng lại cùng nhãn nếu nhiều claim dùng cùng nguồn. "
        "Không tự tạo số nguồn và không viết danh mục căn cứ pháp lý; hệ thống sẽ kiểm "
        "tra nhãn nguồn và sinh citation từ metadata."
    )
    user_prompt = (
        f"CÂU HỎI:\n{query}\n\n"
        f"CHẾ ĐỘ PHIÊN BẢN: {intent}\n\n"
        f"EVIDENCE:\n{context or '[Không có evidence phù hợp]'}\n\n"
        "Chỉ chọn evidence trực tiếp phù hợp với câu hỏi, tuân thủ đúng chế độ phiên bản "
        "và gắn [Nguồn n] ở cuối từng claim."
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
