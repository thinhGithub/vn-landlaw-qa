import json
from pathlib import Path

import pytest

from landlaw_rag.retrieval.vector import (
    format_passage,
    format_query,
    load_and_validate_chunks,
    sha256_file,
    validate_parsing_report,
)


def _chunk(chunk_id: str = "chunk-1", text: str = "Nội dung pháp luật") -> dict:
    return {
        "chunk_id": chunk_id,
        "text": text,
        "metadata": {"chunk_id": chunk_id, "article": "Điều 1"},
    }


def test_e5_prefix_and_whitespace_normalization() -> None:
    assert format_passage("  Nội dung\n pháp luật ") == "passage: Nội dung pháp luật"
    assert format_query("  cấp giấy chứng nhận ") == "query: cấp giấy chứng nhận"


def test_chunk_validation_rejects_duplicate_ids(tmp_path: Path) -> None:
    path = tmp_path / "chunks.json"
    path.write_text(json.dumps([_chunk(), _chunk()]), encoding="utf-8")
    with pytest.raises(ValueError, match="chunk_id trùng"):
        load_and_validate_chunks(path)


def test_chunk_validation_accepts_valid_input(tmp_path: Path) -> None:
    path = tmp_path / "chunks.json"
    path.write_text(json.dumps([_chunk()], ensure_ascii=False), encoding="utf-8")
    assert load_and_validate_chunks(path)[0]["chunk_id"] == "chunk-1"
    assert len(sha256_file(path)) == 64


def test_parsing_report_must_have_no_warnings(tmp_path: Path) -> None:
    path = tmp_path / "report.json"
    path.write_text(json.dumps([{"document_id": "law", "warnings": ["parse error"]}]), encoding="utf-8")
    with pytest.raises(ValueError, match="parse error"):
        validate_parsing_report(path)
