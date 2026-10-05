from typing import Any

import pytest

from landlaw_rag.comparison import (
    build_comparison_messages,
    canonicalize_comparison_structure,
    detect_legal_intent,
    extract_comparison_topic,
    isolate_version,
    offset_source_labels,
    rerank_legal_focus,
    retrieve_comparison_evidence,
    validate_comparison_mapping,
    validate_comparison_structure,
)
from landlaw_rag.generation import CitationValidationError, cite_tagged_answer


def _result(chunk_id: str, document_id: str, article: str = "Điều 1") -> dict[str, Any]:
    return {
        "chunk_id": chunk_id,
        "text": "Nội dung evidence",
        "metadata": {
            "chunk_id": chunk_id,
            "document_id": document_id,
            "document_title": document_id,
            "article": article,
        },
    }


class StubRetriever:
    def __init__(self, results: list[dict[str, Any]]) -> None:
        self.results = results
        self.calls: list[tuple[str, int]] = []

    def search(self, query: str, top_k: int) -> list[dict[str, Any]]:
        self.calls.append((query, top_k))
        return self.results[:top_k]


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("Điều kiện chuyển nhượng quyền sử dụng đất là gì?", "qa"),
        ("Theo Luật Đất đai 2013 quy định thế nào?", "qa"),
        ("Hiện nay điều kiện chuyển nhượng là gì?", "qa"),
        ("So sánh điều kiện chuyển nhượng năm 2013 và 2024", "comparison"),
        ("Quy định trước đây và hiện nay khác nhau thế nào?", "comparison"),
        ("Đối chiếu quyền của người sử dụng đất", "comparison"),
    ],
)
def test_intent_routing(query: str, expected: str) -> None:
    assert detect_legal_intent(query) == expected


def test_empty_intent_query_is_rejected() -> None:
    with pytest.raises(ValueError, match="không được rỗng"):
        detect_legal_intent("  ")


def test_topic_is_shared_instead_of_mapping_article_numbers() -> None:
    topic = extract_comparison_topic(
        "So sánh điều kiện chuyển nhượng giữa Luật Đất đai 2013 và 2024"
    )
    assert "điều kiện chuyển nhượng" in topic.lower()
    assert "so sánh" not in topic.lower()


def test_version_isolation_uses_metadata_not_article_number() -> None:
    mixed = [
        _result("legacy-45", "45-2013-QH13", "Điều 45"),
        _result("current-45", "31-2024-QH15", "Điều 45"),
        _result("amendment", "43-2024-QH15", "Điều 2"),
    ]
    assert [item["chunk_id"] for item in isolate_version(mixed, "2013")] == ["legacy-45"]
    assert [item["chunk_id"] for item in isolate_version(mixed, "current")] == [
        "current-45",
        "amendment",
    ]


def test_comparison_runs_two_searches_and_keeps_separate_pools() -> None:
    retriever = StubRetriever(
        [
            _result("legacy", "45-2013-QH13"),
            _result("current", "31-2024-QH15"),
            _result("resolution", "254-2025-QH15"),
        ]
    )
    evidence = retrieve_comparison_evidence(
        retriever,
        "So sánh điều kiện chuyển nhượng năm 2013 và 2024",
        top_k_per_side=2,
    )
    assert len(retriever.calls) == 2
    assert "45/2013/QH13" in retriever.calls[0][0]
    assert "31/2024/QH15" in retriever.calls[1][0]
    assert [item["chunk_id"] for item in evidence.legacy] == ["legacy"]
    assert [item["chunk_id"] for item in evidence.current] == ["current", "resolution"]
    assert evidence.complete


def test_legal_focus_prefers_matching_intent_subject_and_action() -> None:
    transition = _result("transition", "45-2013-QH13", "Điều 210")
    transition["metadata"]["article_title"] = "Điều khoản chuyển tiếp"
    transition["text"] = (
        "Hộ gia đình, cá nhân tiếp tục sử dụng đất khi hết thời hạn sử dụng đất."
    )
    conditions = _result("conditions", "45-2013-QH13", "Điều 188")
    conditions["metadata"]["article_title"] = (
        "Điều kiện thực hiện các quyền chuyển nhượng quyền sử dụng đất"
    )
    conditions["text"] = (
        "Người sử dụng đất được chuyển nhượng quyền sử dụng đất khi có các điều kiện."
    )
    ranked = rerank_legal_focus(
        "điều kiện để cá nhân được chuyển nhượng quyền sử dụng đất",
        [transition, conditions],
    )
    assert ranked[0]["chunk_id"] == "conditions"
    assert ranked[0]["legal_focus"]["intent_title_matches"] >= 1
    assert ranked[0]["legal_focus"]["action_matches"] == 1
    assert ranked[0]["legal_focus"]["general_rights_condition_match"] == 1


def test_legal_focus_does_not_use_article_number_as_correspondence() -> None:
    wrong_same_number = _result("same-number", "45-2013-QH13", "Điều 45")
    wrong_same_number["metadata"]["article_title"] = "Quản lý đất công"
    right_topic = _result("right-topic", "45-2013-QH13", "Điều 999")
    right_topic["metadata"]["article_title"] = "Điều kiện chuyển nhượng quyền sử dụng đất"
    ranked = rerank_legal_focus(
        "điều kiện chuyển nhượng quyền sử dụng đất",
        [wrong_same_number, right_topic],
    )
    assert ranked[0]["chunk_id"] == "right-topic"


def test_source_labels_are_global_across_two_contexts() -> None:
    assert offset_source_labels("[Nguồn 1]\n[Nguồn 2]", 3) == (
        "[Nguồn 4]\n[Nguồn 5]"
    )


def test_prompt_requires_structure_and_forbids_article_number_mapping() -> None:
    messages = build_comparison_messages(
        "So sánh quyền sử dụng đất năm 2013 và 2024",
        "[Nguồn 1] evidence cũ",
        "[Nguồn 2] evidence mới",
    )
    prompt = " ".join(message["content"] for message in messages)
    assert "không ghép hai quy định chỉ vì chúng có cùng số Điều" in prompt
    assert "1. Quy định năm 2013:" in prompt
    assert "4. Điểm khác/thay đổi:" in prompt
    assert "M7" in prompt
    assert "NHÃN ĐƯỢC PHÉP CHO PHÍA 2013: [Nguồn 1]" in prompt
    assert "NHÃN ĐƯỢC PHÉP CHO PHÍA HIỆN HÀNH: [Nguồn 2]" in prompt
    assert "Không viết dòng nào mà thiếu [Nguồn n]" in prompt


def test_two_stage_prompt_requests_only_its_sections() -> None:
    first = build_comparison_messages(
        "So sánh quyền sử dụng đất năm 2013 và 2024",
        "[Nguồn 1] evidence cũ",
        "[Nguồn 2] evidence mới",
        sections=(1, 2),
    )
    second = build_comparison_messages(
        "So sánh quyền sử dụng đất năm 2013 và 2024",
        "[Nguồn 1] evidence cũ",
        "[Nguồn 2] evidence mới",
        sections=(3, 4),
    )
    assert "Chỉ trả lời các mục 1, 2" in first[1]["content"]
    assert "Chỉ trả lời các mục 3, 4" in second[1]["content"]
    assert "Dòng 1 bắt đầu chính xác bằng '1. Quy định năm 2013:'" in first[1]["content"]
    assert "3. Điểm giống:" in second[1]["content"]
    assert "4. Điểm khác/thay đổi:" in second[1]["content"]
    assert "Không được chỉ in nhãn nguồn" in second[1]["content"]
    assert "Dòng 1 phải có nhãn phía 2013" not in second[1]["content"]


def test_numbered_output_is_canonicalized_without_changing_claim_or_sources() -> None:
    raw = (
        "1. Theo Luật 2013, cần có Giấy chứng nhận [Nguồn 1].\n\n"
        "2. Theo luật hiện hành, cần có Giấy chứng nhận [Nguồn 5]."
    )
    normalized = canonicalize_comparison_structure(raw)
    assert normalized == (
        "1. Quy định năm 2013: Theo Luật 2013, cần có Giấy chứng nhận [Nguồn 1].\n"
        "2. Quy định hiện hành: Theo luật hiện hành, cần có Giấy chứng nhận [Nguồn 5]."
    )


def test_canonical_output_is_not_duplicated() -> None:
    raw = "3. Điểm giống: Cùng yêu cầu Giấy chứng nhận. [Nguồn 1] [Nguồn 5]"
    assert canonicalize_comparison_structure(raw) == raw


def test_multiline_bullets_are_folded_into_their_numbered_sections() -> None:
    raw = (
        "3. Điểm giống:\n"
        "- Cả hai đều yêu cầu Giấy chứng nhận [Nguồn 1] [Nguồn 5].\n"
        "4. Điểm khác/thay đổi:\n"
        "- Luật hiện hành bổ sung một điều kiện [Nguồn 1] [Nguồn 5].\n"
        "- Có thêm trường hợp riêng [Nguồn 7]."
    )
    assert canonicalize_comparison_structure(raw) == (
        "3. Điểm giống: Cả hai đều yêu cầu Giấy chứng nhận [Nguồn 1] [Nguồn 5].\n"
        "4. Điểm khác/thay đổi: Luật hiện hành bổ sung một điều kiện "
        "[Nguồn 1] [Nguồn 5]. Có thêm trường hợp riêng [Nguồn 7]."
    )


def test_source_tag_spacing_and_case_are_canonicalized() -> None:
    raw = "3. Điểm giống: Có nội dung chung [ nguồn 1 ] [ NGUỒN 6 ]"
    assert canonicalize_comparison_structure(raw) == (
        "3. Điểm giống: Có nội dung chung [Nguồn 1] [Nguồn 6]"
    )


def test_evidence_mapping_accepts_correct_sides() -> None:
    legacy = [_result("legacy", "45-2013-QH13", "Điều 188")]
    current = [_result("current", "31-2024-QH15", "Điều 45")]
    raw = (
        "1. Quy định năm 2013: Nội dung cũ. [Nguồn 1]\n"
        "2. Quy định hiện hành: Nội dung mới. [Nguồn 2]\n"
        "3. Điểm giống: Có điểm chung được hai phía hỗ trợ. [Nguồn 1] [Nguồn 2]\n"
        "4. Điểm khác/thay đổi: Có thay đổi được hai phía hỗ trợ. [Nguồn 1] [Nguồn 2]"
    )
    validate_comparison_structure(raw)
    cited = cite_tagged_answer(raw, legacy + current)
    validate_comparison_mapping(cited.claim_mappings, legacy, current)
    assert cited.claim_mappings[0].chunk_ids == ("legacy",)
    assert cited.claim_mappings[1].chunk_ids == ("current",)


def test_evidence_mapping_rejects_crossed_version_source() -> None:
    legacy = [_result("legacy", "45-2013-QH13")]
    current = [_result("current", "31-2024-QH15")]
    cited = cite_tagged_answer(
        "1. Quy định năm 2013: Nội dung gắn nhầm. [Nguồn 2]",
        legacy + current,
    )
    with pytest.raises(CitationValidationError, match="2013 trỏ sai"):
        validate_comparison_mapping(cited.claim_mappings, legacy, current)


def test_similarity_requires_evidence_from_both_sides() -> None:
    legacy = [_result("legacy", "45-2013-QH13")]
    current = [_result("current", "31-2024-QH15")]
    cited = cite_tagged_answer(
        "3. Điểm giống: Chỉ gắn một phía. [Nguồn 1]",
        legacy + current,
    )
    with pytest.raises(CitationValidationError, match="cả hai phía"):
        validate_comparison_mapping(cited.claim_mappings, legacy, current)
