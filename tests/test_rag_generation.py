import pytest

from landlaw_rag.generation import (
    build_context,
    build_messages,
    detect_version_intent,
    expand_article_context,
    filter_results_by_version,
    format_source,
)


class WordTokenizer:
    def encode(self, text: str, add_special_tokens: bool = False) -> list[str]:
        return text.split()

    def decode(self, tokens: list[str], skip_special_tokens: bool = True) -> str:
        return " ".join(tokens)


def test_format_source_uses_legal_metadata() -> None:
    metadata = {
        "document_title": "Luật Đất đai số 31/2024/QH15",
        "article": "Điều 98",
        "clause": "Khoản 1",
    }
    assert format_source(metadata) == "Luật Đất đai số 31/2024/QH15 → Điều 98 → Khoản 1"


def test_format_source_includes_full_legal_hierarchy() -> None:
    metadata = {
        "document_title": "Luật Đất đai số 31/2024/QH15",
        "chapter": "Chương III",
        "section": "Mục 2",
        "article": "Điều 45",
        "article_title": "Điều kiện thực hiện các quyền",
        "clause": "Khoản 1",
        "point": "Điểm a",
    }
    assert format_source(metadata) == (
        "Luật Đất đai số 31/2024/QH15 → Chương III → Mục 2 → "
        "Điều 45. Điều kiện thực hiện các quyền → Khoản 1 → Điểm a"
    )


def test_build_context_respects_token_budget() -> None:
    results = [
        {"text": "một hai ba", "metadata": {"document_id": "31-2024-QH15"}},
        {"text": "bốn năm sáu", "metadata": {"document_id": "45-2013-QH13"}},
    ]
    context, used = build_context(results, WordTokenizer(), max_context_tokens=12)
    assert context
    assert len(context.split()) <= 12
    assert 1 <= len(used) <= 2


def test_prompt_requires_evidence_and_insufficient_answer() -> None:
    messages = build_messages("Điều kiện bồi thường là gì?", "[Nguồn 1] Nội dung luật")
    combined = " ".join(message["content"] for message in messages)
    assert "Chỉ trả lời dựa trên thông tin xuất hiện trực tiếp" in combined
    assert "Chưa đủ căn cứ trong dữ liệu truy xuất." in combined
    assert "Không bắt buộc sử dụng toàn bộ EVIDENCE" in combined
    assert "phù hợp đúng chủ thể, hành vi, đối tượng" in combined
    assert "Không trộn quy định dành cho chủ thể" in combined
    assert "không tự bổ sung ví dụ" in combined
    assert "Không nêu Điều, Khoản, Điểm" in combined
    assert "'v.v.'" in combined
    assert "Mỗi claim pháp lý phải nằm trên một dòng" in combined
    assert "[Nguồn n]" in combined
    assert "Điều kiện bồi thường là gì?" in combined


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("Điều kiện chuyển nhượng quyền sử dụng đất là gì?", "current"),
        ("Theo Luật Đất đai 2013, điều kiện chuyển nhượng là gì?", "2013"),
        ("So sánh điều kiện chuyển nhượng theo luật 2013 và 2024", "comparison"),
    ],
)
def test_detect_version_intent(query: str, expected: str) -> None:
    assert detect_version_intent(query) == expected


def test_version_isolation_filters_2013_from_current_queries() -> None:
    results = [
        {"text": "hiện hành", "metadata": {"document_id": "31-2024-QH15"}},
        {"text": "sửa đổi", "metadata": {"document_id": "43-2024-QH15"}},
        {"text": "cũ", "metadata": {"document_id": "45-2013-QH13"}},
    ]
    current = filter_results_by_version(results, "Điều kiện chuyển nhượng là gì?")
    legacy = filter_results_by_version(results, "Theo Luật Đất đai 2013 thì sao?")
    comparison = filter_results_by_version(results, "So sánh luật 2013 và 2024")
    assert [item["text"] for item in current] == ["hiện hành", "sửa đổi"]
    assert [item["text"] for item in legacy] == ["cũ"]
    assert comparison == results


def test_expand_article_context_adds_same_article_and_deduplicates() -> None:
    chunks = [
        {
            "chunk_id": f"2024-45-{clause}",
            "text": f"nội dung khoản {clause}",
            "metadata": {
                "document_id": "31-2024-QH15",
                "article": "Điều 45",
                "clause": f"Khoản {clause}",
            },
        }
        for clause in (1, 2, 3)
    ]
    chunks.append(
        {
            "chunk_id": "2013-45-2",
            "text": "nội dung luật cũ",
            "metadata": {
                "document_id": "45-2013-QH13",
                "article": "Điều 45",
                "clause": "Khoản 2",
            },
        }
    )
    results = [chunks[0], chunks[2], chunks[0]]
    expanded = expand_article_context(results, chunks, 1_000, WordTokenizer())
    assert [item["chunk_id"] for item in expanded] == ["2024-45-1", "2024-45-2", "2024-45-3"]
    assert all(item["metadata"]["document_id"] == "31-2024-QH15" for item in expanded)
    assert expanded[1]["expanded"] is True


def test_expand_article_context_requires_repeated_article_hits() -> None:
    chunks = [
        {"chunk_id": "a", "text": "một", "metadata": {"document_id": "doc", "article": "Điều 1"}},
        {"chunk_id": "b", "text": "hai", "metadata": {"document_id": "doc", "article": "Điều 1"}},
    ]
    assert expand_article_context(chunks[:1], chunks, 1_000, WordTokenizer()) == chunks[:1]


def test_expand_article_context_respects_token_budget() -> None:
    chunks = [
        {
            "chunk_id": str(index),
            "text": "nội dung rất dài " * 20,
            "metadata": {"document_id": "doc", "article": "Điều 1", "clause": f"Khoản {index}"},
        }
        for index in range(1, 5)
    ]
    expanded = expand_article_context(chunks[:2], chunks, 100, WordTokenizer())
    assert len(expanded) == 2


def test_prompt_declares_each_version_mode() -> None:
    current = " ".join(
        item["content"] for item in build_messages("Điều kiện chuyển nhượng?", "evidence")
    )
    legacy = " ".join(
        item["content"] for item in build_messages("Theo luật năm 2013?", "evidence")
    )
    comparison = " ".join(
        item["content"] for item in build_messages("So sánh luật 2013 và 2024", "evidence")
    )
    assert "CHẾ ĐỘ PHIÊN BẢN: current" in current
    assert "không dùng Luật Đất đai 2013" in current
    assert "CHẾ ĐỘ PHIÊN BẢN: 2013" in legacy
    assert "không trộn quy định hiện hành" in legacy
    assert "CHẾ ĐỘ PHIÊN BẢN: comparison" in comparison
    assert "tách rõ quy định năm 2013" in comparison


def test_empty_query_is_rejected() -> None:
    with pytest.raises(ValueError, match="Query không được rỗng"):
        build_messages(" ", "context")
