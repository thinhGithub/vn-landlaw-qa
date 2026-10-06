from landlaw_rag.chunking.legal_parser import chunk_document, parse_document, validate_document


SAMPLE = """LUẬT
ĐẤT ĐAI
Chương 1.
QUY ĐỊNH CHUNG
Mục 1
NGUYÊN TẮC
Điều 1. Phạm vi điều chỉnh
Nội dung mở đầu.
1. Khoản thứ nhất gồm:
a) Điểm a;
b) Điểm b.
2. Khoản thứ hai.
Điều 2. Điều ngắn
Nội dung điều ngắn.
Luật này được Quốc hội thông qua.
CHỦ TỊCH QUỐC HỘI
"""


def test_parse_hierarchy_and_normalization() -> None:
    document, warnings = parse_document(SAMPLE, "Luật-45-2013-QH13.txt")
    chapter = document["chapters"][0]
    section = chapter["sections"][0]
    article = section["articles"][0]
    assert chapter["label"] == "Chương I"
    assert section["label"] == "Mục 1"
    assert article["label"] == "Điều 1"
    assert [item["label"] for item in article["clauses"]] == ["Khoản 1", "Khoản 2"]
    assert [item["label"] for item in article["clauses"][0]["points"]] == ["Điểm a", "Điểm b"]
    assert document["validation"]["all_lines_assigned"]
    assert not warnings


def test_adaptive_chunking_and_stable_ids() -> None:
    document, _ = parse_document(SAMPLE, "Luật-45-2013-QH13.txt")
    first = chunk_document(document, max_chars=65)
    second = chunk_document(document, max_chars=65)
    assert [item["chunk_id"] for item in first] == [item["chunk_id"] for item in second]
    assert len({item["chunk_id"] for item in first}) == len(first)
    assert all(set(item["metadata"]) >= {
        "document_id", "document_title", "chapter", "section", "article",
        "article_title", "clause", "point", "source_file", "chunk_id",
    } for item in first)
    assert not validate_document(document, first)


def test_short_article_still_chunks_by_clause_and_point_for_precise_citation() -> None:
    sample = """Điều 10. Xác định loại đất
1. Việc xác định loại đất dựa trên các căn cứ sau:
a) Giấy chứng nhận quyền sử dụng đất;
b) Giấy tờ về quyền sử dụng đất.
2. Trường hợp không có giấy tờ thực hiện theo quy định của Chính phủ.
"""
    document, warnings = parse_document(sample, "Luật-31-2024-QH15.txt")
    chunks = chunk_document(document, max_chars=3200)

    assert not warnings
    locators = [
        (chunk["metadata"]["article"], chunk["metadata"]["clause"],
         chunk["metadata"]["point"])
        for chunk in chunks
    ]
    assert ("Điều 10", "Khoản 1", None) in locators
    assert ("Điều 10", "Khoản 1", "Điểm a") in locators
    assert ("Điều 10", "Khoản 1", "Điểm b") in locators
    assert ("Điều 10", "Khoản 2", None) in locators
    assert all("Điểm a-b" not in locator for locator in locators if locator[2])
    assert not validate_document(document, chunks)


def test_quoted_law_content_is_not_parsed_as_direct_clause() -> None:
    sample = """Điều 1. Sửa đổi luật khác
1. Sửa đổi Điều 2 như sau:
“2. Đây là khoản của luật được trích dẫn:
a) Điểm thuộc luật được trích dẫn;
b) Điểm tiếp theo.”.
2. Nội dung trực tiếp của Điều 1.
"""
    document, warnings = parse_document(sample, "Luật-43-2024-QH15.txt")
    article = document["standalone_articles"][0]
    assert [clause["number"] for clause in article["clauses"]] == ["1", "2"]
    assert not article["clauses"][0]["points"]
    assert not warnings


def test_section_title_can_be_inline_like_2013_law() -> None:
    sample = """Chương II
QUYỀN VÀ TRÁCH NHIỆM
MỤC 1. QUYỀN CỦA NHÀ NƯỚC ĐỐI VỚI ĐẤT ĐAI
Điều 10. Nội dung
Nội dung của điều.
"""
    document, warnings = parse_document(sample, "Luật-45-2013-QH13.txt")
    section = document["chapters"][0]["sections"][0]
    assert section["label"] == "Mục 1"
    assert section["title"] == "QUYỀN CỦA NHÀ NƯỚC ĐỐI VỚI ĐẤT ĐAI"
    assert section["articles"][0]["label"] == "Điều 10"
    assert not warnings
