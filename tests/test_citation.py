import pytest

from landlaw_rag.generation import (
    CitationValidationError,
    ClaimSupport,
    build_citations,
    cite_answer,
    cite_tagged_answer,
    format_citation,
)


def _chunk(chunk_id: str, **metadata: str) -> dict:
    return {"chunk_id": chunk_id, "text": "Nội dung evidence", "metadata": metadata}


def test_format_citation_is_short_and_deterministic() -> None:
    metadata = {
        "document_title": "Luật Đất đai số 31/2024/QH15",
        "chapter": "Chương III",
        "section": "Mục 2",
        "article": "Điều 45",
        "article_title": "Điều kiện thực hiện các quyền",
        "clause": "Khoản 1",
        "point": "Điểm a",
    }
    assert format_citation(metadata) == (
        "Luật Đất đai số 31/2024/QH15 → Điều 45 → Khoản 1 → Điểm a"
    )
    assert "Điều kiện thực hiện các quyền" not in format_citation(metadata)
    assert "Chương" not in format_citation(metadata)


def test_duplicate_citations_are_merged_in_evidence_order() -> None:
    evidence = [
        _chunk("c1", document_title="Luật A", article="Điều 1", clause="Khoản 2"),
        _chunk("c2", document_title="Luật A", article="Điều 1", clause="Khoản 2"),
        _chunk("c3", document_title="Luật B", article="Điều 3"),
    ]
    citations = build_citations(evidence, ["c3", "c2", "c1", "c2"])
    assert [citation.text for citation in citations] == [
        "Luật A → Điều 1 → Khoản 2",
        "Luật B → Điều 3",
    ]
    assert citations[0].chunk_ids == ("c1", "c2")
    assert [citation.number for citation in citations] == [1, 2]


def test_missing_optional_metadata_is_omitted() -> None:
    citation = format_citation({"document_id": "31-2024-QH15", "article": "Điều 7"})
    assert citation == "31-2024-QH15 → Điều 7"


def test_legacy_law_uses_the_same_citation_rules() -> None:
    citation = format_citation(
        {
            "document_title": "Luật Đất đai số 45/2013/QH13",
            "article": "Điều 188",
            "clause": "Khoản 1",
        }
    )
    assert citation == "Luật Đất đai số 45/2013/QH13 → Điều 188 → Khoản 1"


def test_missing_document_identity_is_rejected() -> None:
    with pytest.raises(CitationValidationError, match="thiếu document"):
        format_citation({"article": "Điều 7"})


def test_citation_outside_context_is_rejected() -> None:
    evidence = [_chunk("in-context", document_title="Luật A", article="Điều 1")]
    with pytest.raises(CitationValidationError, match="không thuộc context/evidence"):
        build_citations(evidence, ["not-in-context"])


def test_single_source_is_only_listed_at_end() -> None:
    evidence = [
        _chunk(
            "c1",
            document_title="Luật Đất đai số 31/2024/QH15",
            article="Điều 45",
            clause="Khoản 1",
        )
    ]
    result = cite_answer("Người sử dụng đất phải đáp ứng điều kiện luật định.", evidence)
    assert result.text == (
        "Người sử dụng đất phải đáp ứng điều kiện luật định.\n\n"
        "Căn cứ pháp lý:\n"
        "[1] Luật Đất đai số 31/2024/QH15 → Điều 45 → Khoản 1"
    )
    assert "[1]" not in result.text.split("Căn cứ pháp lý:")[0]


def test_multiple_sources_are_attached_to_their_claims() -> None:
    claim_one = "Ý thứ nhất."
    claim_two = "Ý thứ hai."
    evidence = [
        _chunk("c1", document_title="Luật A", article="Điều 1"),
        _chunk("c2", document_title="Luật B", article="Điều 2", clause="Khoản 3"),
    ]
    supports = [
        ClaimSupport(claim_one, ("c1",)),
        ClaimSupport(claim_two, ("c2",)),
    ]
    result = cite_answer(f"{claim_one} {claim_two}", evidence, supports)
    assert "Ý thứ nhất. [1] Ý thứ hai. [2]" in result.text
    assert result.claim_supports == tuple(supports)
    assert result.citations[0].chunk_ids == ("c1",)
    assert result.citations[1].chunk_ids == ("c2",)


def test_multiple_sources_without_claim_mapping_are_only_listed_at_end() -> None:
    evidence = [
        _chunk("c1", document_title="Luật A", article="Điều 1"),
        _chunk("c2", document_title="Luật B", article="Điều 2"),
    ]
    result = cite_answer("Hai ý dùng hai nguồn.", evidence)
    body, bibliography = result.text.split("\n\nCăn cứ pháp lý:\n")
    assert body == "Hai ý dùng hai nguồn."
    assert "[1] Luật A → Điều 1" in bibliography
    assert "[2] Luật B → Điều 2" in bibliography
    assert result.claim_supports == ()


def test_tagged_claims_reuse_one_inline_marker_and_map_to_chunk() -> None:
    evidence = [
        _chunk(
            "c1",
            document_title="Luật Đất đai số 31/2024/QH15",
            article="Điều 45",
            clause="Khoản 1",
        )
    ]
    generated = (
        "1. Điều kiện thứ nhất. [Nguồn 1]\n"
        "2. Điều kiện thứ hai. [Nguồn 1]\n"
        "3. Điều kiện thứ ba. [Nguồn 1]"
    )
    result = cite_tagged_answer(generated, evidence)
    assert "1. Điều kiện thứ nhất. [1]" in result.text
    assert "2. Điều kiện thứ hai. [1]" in result.text
    assert "3. Điều kiện thứ ba. [1]" in result.text
    assert result.text.count("[1] Luật Đất đai") == 1
    assert len(result.citations) == 1
    assert [mapping.citation_ids for mapping in result.claim_mappings] == [(1,), (1,), (1,)]
    assert all(mapping.chunk_ids == ("c1",) for mapping in result.claim_mappings)


def test_tagged_claims_map_different_sources_to_different_markers() -> None:
    evidence = [
        _chunk("c1", document_title="Luật A", article="Điều 1"),
        _chunk("c2", document_title="Luật B", article="Điều 2"),
    ]
    result = cite_tagged_answer(
        "Ý thứ nhất. [Nguồn 1]\nÝ thứ hai. [Nguồn 2]", evidence
    )
    assert result.text.startswith("Ý thứ nhất. [1]\nÝ thứ hai. [2]")
    assert result.claim_mappings[0].chunk_ids == ("c1",)
    assert result.claim_mappings[1].chunk_ids == ("c2",)


def test_different_chunks_of_same_legal_source_reuse_marker() -> None:
    metadata = {
        "document_title": "Luật Đất đai số 31/2024/QH15",
        "article": "Điều 45",
        "clause": "Khoản 1",
    }
    evidence = [_chunk("c1", **metadata), _chunk("c2", **metadata)]
    result = cite_tagged_answer(
        "Ý thứ nhất. [Nguồn 1]\nÝ thứ hai. [Nguồn 2]", evidence
    )
    assert result.text.startswith("Ý thứ nhất. [1]\nÝ thứ hai. [1]")
    assert len(result.citations) == 1
    assert result.citations[0].chunk_ids == ("c1", "c2")
    assert result.text.count("[1] Luật Đất đai") == 1
    assert result.claim_mappings[0].chunk_ids == ("c1",)
    assert result.claim_mappings[1].chunk_ids == ("c2",)


def test_tagged_answer_rejects_unknown_source_and_uncited_claim() -> None:
    evidence = [_chunk("c1", document_title="Luật A", article="Điều 1")]
    with pytest.raises(CitationValidationError, match="không thuộc context"):
        cite_tagged_answer("Một claim. [Nguồn 2]", evidence)
    with pytest.raises(CitationValidationError, match="thiếu nhãn"):
        cite_tagged_answer("Một claim không có nguồn.", evidence)


def test_source_marker_on_next_line_is_joined_to_previous_claim() -> None:
    evidence = [_chunk("c1", document_title="Luật A", article="Điều 1")]
    result = cite_tagged_answer("Một claim pháp lý.\n[Nguồn 1]", evidence)
    assert result.text.startswith("Một claim pháp lý. [1]")
    assert result.claim_mappings[0].claim == "Một claim pháp lý."
    assert result.claim_mappings[0].chunk_ids == ("c1",)


def test_grouped_source_markers_are_normalized_without_inferring_sources() -> None:
    evidence = [
        _chunk("c1", document_title="Luật A", article="Điều 1"),
        _chunk("c2", document_title="Luật B", article="Điều 2"),
    ]
    result = cite_tagged_answer(
        "Điểm giống được cả hai phía hỗ trợ. [Nguồn 1, Nguồn 2]", evidence
    )
    assert result.claim_mappings[0].chunk_ids == ("c1", "c2")
    assert result.text.startswith("Điểm giống được cả hai phía hỗ trợ. [1][2]")


def test_orphan_source_marker_is_rejected() -> None:
    evidence = [_chunk("c1", document_title="Luật A", article="Điều 1")]
    with pytest.raises(CitationValidationError, match="không có claim"):
        cite_tagged_answer("[Nguồn 1]", evidence)
