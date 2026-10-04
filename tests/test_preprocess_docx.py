from pathlib import Path

from landlaw_rag.ingestion.preprocess_docx import _is_page_number, normalize_text


def test_normalize_text_preserves_line_boundaries() -> None:
    assert normalize_text("  Điều 1.  Phạm vi\n  1. Nội dung  ") == (
        "Điều 1. Phạm vi\n1. Nội dung"
    )


def test_normalize_text_handles_unicode_spaces() -> None:
    assert normalize_text("Khoản\u00a01\t nội dung") == "Khoản 1 nội dung"


def test_page_number_detection_is_conservative() -> None:
    assert _is_page_number("- 12 -")
    assert _is_page_number("Trang 12/30")
    assert not _is_page_number("Điều 12. Giải thích từ ngữ")
    assert not _is_page_number("2024")
