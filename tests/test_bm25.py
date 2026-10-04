import json
from pathlib import Path

from landlaw_rag.retrieval.bm25 import BM25Config, BM25Index, tokenize_vi


def _build_index(tmp_path: Path) -> BM25Index:
    chunks = [
        {
            "chunk_id": "law-2024-a75-c1",
            "text": "Luật Đất đai 2024\nĐiều 75. Điều kiện bồi thường\n1. Có giấy chứng nhận.",
            "metadata": {
                "document_id": "31-2024-QH15", "document_title": "Luật Đất đai số 31/2024/QH15",
                "chapter": "Chương VII", "section": None, "article": "Điều 75",
                "article_title": "Điều kiện bồi thường", "clause": "Khoản 1",
                "point": None, "source_file": "law2024.txt", "chunk_id": "law-2024-a75-c1",
            },
        },
        {
            "chunk_id": "law-2013-a75-c1",
            "text": "Luật Đất đai 2013\nĐiều 75. Điều kiện được bồi thường về đất.",
            "metadata": {
                "document_id": "45-2013-QH13", "document_title": "Luật Đất đai số 45/2013/QH13",
                "chapter": "Chương VI", "section": "Mục 2", "article": "Điều 75",
                "article_title": "Điều kiện được bồi thường", "clause": None,
                "point": None, "source_file": "law2013.txt", "chunk_id": "law-2013-a75-c1",
            },
        },
    ]
    chunks_path = tmp_path / "chunks.json"
    report_path = tmp_path / "report.json"
    chunks_path.write_text(json.dumps(chunks, ensure_ascii=False), encoding="utf-8")
    report_path.write_text(json.dumps([{"document_id": "test", "warnings": []}]), encoding="utf-8")
    return BM25Index.build(chunks_path, report_path, BM25Config(top_k=2))


def test_tokenizer_preserves_legal_document_number() -> None:
    tokens = tokenize_vi("Khoản 2 Điều 57 Luật 45/2013/QH13")
    assert "45/2013/qh13" in tokens
    assert {"khoản", "2", "điều", "57"} <= set(tokens)


def test_explicit_metadata_is_prioritized(tmp_path: Path) -> None:
    index = _build_index(tmp_path)
    result = index.query("Khoản 1 Điều 75 Luật 31/2024/QH15", top_k=1)[0]
    assert result["chunk_id"] == "law-2024-a75-c1"
    assert result["metadata_boost"] == 20.0
    assert result["exact_matches"]["document_id"]
    assert result["exact_matches"]["article"]
    assert result["exact_matches"]["clause"]


def test_saved_index_loads_without_rebuild(tmp_path: Path) -> None:
    index = _build_index(tmp_path)
    index_path = tmp_path / "index.json.gz"
    index.save(index_path)
    loaded = BM25Index.load(index_path)
    assert loaded.query("bồi thường", top_k=2) == index.query("bồi thường", top_k=2)


def test_bm25_scores_are_non_negative(tmp_path: Path) -> None:
    index = _build_index(tmp_path)
    results = index.query("điều kiện bồi thường", top_k=2)
    assert results
    assert all(item["bm25_score"] >= 0 for item in results)
