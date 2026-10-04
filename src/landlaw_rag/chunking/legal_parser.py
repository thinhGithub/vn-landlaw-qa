"""Parser cấu trúc pháp luật và adaptive chunking cho Milestone 2."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


CHAPTER_RE = re.compile(r"^Chương\s+([IVXLCDM]+|\d+)\.?$", re.IGNORECASE)
SECTION_RE = re.compile(
    r"^Mục\s+([IVXLCDM]+|\d+)\s*[.．]?\s*(.*)$", re.IGNORECASE
)
ARTICLE_RE = re.compile(r"^Điều\s+(\d+[A-Za-z]?)\s*[.．]\s*(.*)$", re.IGNORECASE)
CLAUSE_RE = re.compile(r"^(\d+)\s*[.．]\s+(.+)$")
POINT_RE = re.compile(r"^([a-zA-ZđĐ])\s*\)\s*(.+)$")
POSTAMBLE_RE = re.compile(r"^(?:Luật|Nghị quyết) này được Quốc hội\b", re.IGNORECASE)

DOCUMENT_TITLES = {
    "31-2024-QH15": "Luật Đất đai số 31/2024/QH15",
    "43-2024-QH15": (
        "Luật số 43/2024/QH15 sửa đổi, bổ sung một số điều của Luật Đất đai, "
        "Luật Nhà ở, Luật Kinh doanh bất động sản và Luật Các tổ chức tín dụng"
    ),
    "45-2013-QH13": "Luật Đất đai số 45/2013/QH13",
    "254-2025-QH15": "Nghị quyết số 254/2025/QH15",
}

ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def _roman_to_int(value: str) -> int:
    total = 0
    previous = 0
    for char in reversed(value.upper()):
        current = ROMAN_VALUES[char]
        total += -current if current < previous else current
        previous = max(previous, current)
    return total


def _int_to_roman(value: int) -> str:
    pairs = (
        (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
        (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
        (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
    )
    result = []
    for integer, roman in pairs:
        while value >= integer:
            result.append(roman)
            value -= integer
    return "".join(result)


def _normalize_chapter(value: str) -> tuple[int, str]:
    number = int(value) if value.isdigit() else _roman_to_int(value)
    return number, f"Chương {_int_to_roman(number)}"


def _normalize_section(value: str) -> tuple[int, str]:
    number = int(value) if value.isdigit() else _roman_to_int(value)
    return number, f"Mục {number}"


def _document_id(source_file: str) -> str:
    match = re.search(r"(\d+)[-/](\d{4})[-/]QH(\d+)", source_file, re.IGNORECASE)
    if not match:
        raise ValueError(f"Không nhận diện được số hiệu văn bản từ: {source_file}")
    return f"{match.group(1)}-{match.group(2)}-QH{match.group(3)}"


def _line_item(text: str, line_no: int) -> dict[str, Any]:
    return {"text": text, "line": line_no}


def parse_document(text: str, source_file: str) -> tuple[dict[str, Any], list[str]]:
    """Parse một văn bản thành Chương/Mục/Điều/Khoản/Điểm."""

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    doc_id = _document_id(source_file)
    document: dict[str, Any] = {
        "document_id": doc_id,
        "document_title": DOCUMENT_TITLES.get(doc_id, doc_id),
        "source_file": source_file,
        "source_line_count": len(lines),
        "preamble": [],
        "chapters": [],
        "standalone_articles": [],
        "postamble": [],
    }
    warnings: list[str] = []
    current_chapter: dict[str, Any] | None = None
    current_section: dict[str, Any] | None = None
    current_article: dict[str, Any] | None = None
    current_clause: dict[str, Any] | None = None
    current_point: dict[str, Any] | None = None
    in_postamble = False
    in_quotation = False
    assigned_lines: set[int] = set()

    index = 0
    while index < len(lines):
        text_line = lines[index]
        line_no = index + 1
        chapter_match = CHAPTER_RE.fullmatch(text_line)
        section_match = SECTION_RE.fullmatch(text_line)
        article_match = ARTICLE_RE.fullmatch(text_line)

        if in_postamble:
            document["postamble"].append(_line_item(text_line, line_no))
            assigned_lines.add(line_no)
            index += 1
            continue

        # Nội dung luật khác được dẫn nguyên văn trong “...” thuộc node hiện tại,
        # không phải Khoản/Điểm trực tiếp của Điều đang parse.
        if in_quotation:
            item = _line_item(text_line, line_no)
            if current_point is not None:
                current_point["continuation"].append(item)
            elif current_clause is not None:
                current_clause["continuation"].append(item)
            elif current_article is not None:
                current_article["intro"].append(item)
            else:
                document["preamble"].append(item)
            assigned_lines.add(line_no)
            if text_line.count("”") > text_line.count("“"):
                in_quotation = False
            index += 1
            continue

        if current_article and POSTAMBLE_RE.match(text_line):
            in_postamble = True
            current_article = current_clause = current_point = None
            continue

        if chapter_match:
            number, label = _normalize_chapter(chapter_match.group(1))
            title = ""
            title_line = None
            if index + 1 < len(lines) and not (
                CHAPTER_RE.fullmatch(lines[index + 1])
                or SECTION_RE.fullmatch(lines[index + 1])
                or ARTICLE_RE.fullmatch(lines[index + 1])
            ):
                title = lines[index + 1]
                title_line = index + 2
            current_chapter = {
                "number": number, "label": label, "title": title,
                "raw_heading": text_line, "line": line_no, "sections": [], "articles": [],
            }
            document["chapters"].append(current_chapter)
            current_section = current_article = current_clause = current_point = None
            assigned_lines.add(line_no)
            if title_line:
                assigned_lines.add(title_line)
                index += 1
            index += 1
            continue

        if section_match:
            number, label = _normalize_section(section_match.group(1))
            # Luật 2013: "MỤC 1. TIÊU ĐỀ" trên cùng dòng.
            # Luật 2024: "Mục 1" và tiêu đề ở dòng kế tiếp.
            title = section_match.group(2).strip()
            title_line = None
            if not title and index + 1 < len(lines) and not (
                CHAPTER_RE.fullmatch(lines[index + 1])
                or SECTION_RE.fullmatch(lines[index + 1])
                or ARTICLE_RE.fullmatch(lines[index + 1])
            ):
                title = lines[index + 1]
                title_line = index + 2
            current_section = {
                "number": number, "label": label, "title": title,
                "raw_heading": text_line, "line": line_no, "articles": [],
            }
            if current_chapter is None:
                warnings.append(f"Mục tại dòng {line_no} không thuộc Chương")
                # Giữ cấu trúc bằng một Chương ẩn thay vì làm mất Mục.
                current_chapter = {
                    "number": None, "label": None, "title": "", "raw_heading": "",
                    "line": None, "sections": [], "articles": [], "implicit": True,
                }
                document["chapters"].append(current_chapter)
            current_chapter["sections"].append(current_section)
            current_article = current_clause = current_point = None
            assigned_lines.add(line_no)
            if title_line:
                assigned_lines.add(title_line)
                index += 1
            index += 1
            continue

        if article_match:
            article_number = article_match.group(1)
            current_article = {
                "number": article_number,
                "label": f"Điều {article_number}",
                "title": article_match.group(2).strip(),
                "raw_heading": text_line,
                "line": line_no,
                "intro": [], "clauses": [],
            }
            target = (
                current_section["articles"] if current_section is not None
                else current_chapter["articles"] if current_chapter is not None
                else document["standalone_articles"]
            )
            target.append(current_article)
            current_clause = current_point = None
            assigned_lines.add(line_no)
            index += 1
            continue

        clause_match = CLAUSE_RE.fullmatch(text_line) if current_article else None
        if clause_match:
            current_clause = {
                "number": clause_match.group(1), "label": f"Khoản {clause_match.group(1)}",
                "text": text_line, "line": line_no, "continuation": [], "points": [],
            }
            current_article["clauses"].append(current_clause)
            current_point = None
            assigned_lines.add(line_no)
            index += 1
            continue

        point_match = POINT_RE.fullmatch(text_line) if current_article else None
        if point_match:
            point_value = point_match.group(1).lower()
            current_point = {
                "number": point_value, "label": f"Điểm {point_value}",
                "text": text_line, "line": line_no, "continuation": [],
            }
            if current_clause is None:
                warnings.append(
                    f"{current_article['label']}: Điểm {point_value} dòng {line_no} không thuộc Khoản"
                )
                current_article.setdefault("orphan_points", []).append(current_point)
            else:
                current_clause["points"].append(current_point)
            assigned_lines.add(line_no)
            index += 1
            continue

        item = _line_item(text_line, line_no)
        if current_point is not None:
            current_point["continuation"].append(item)
        elif current_clause is not None:
            current_clause["continuation"].append(item)
        elif current_article is not None:
            current_article["intro"].append(item)
        else:
            document["preamble"].append(item)
        assigned_lines.add(line_no)
        if text_line.count("“") > text_line.count("”"):
            in_quotation = True
        index += 1

    missing = sorted(set(range(1, len(lines) + 1)) - assigned_lines)
    if missing:
        warnings.append(f"Có {len(missing)} dòng chưa được gán cấu trúc: {missing[:10]}")
    document["validation"] = {
        "all_lines_assigned": not missing,
        "assigned_line_count": len(assigned_lines),
        "warnings": warnings,
    }
    return document, warnings


def _all_articles(document: dict[str, Any]) -> list[dict[str, Any]]:
    articles = list(document["standalone_articles"])
    for chapter in document["chapters"]:
        articles.extend(chapter["articles"])
        for section in chapter["sections"]:
            articles.extend(section["articles"])
    return sorted(articles, key=lambda item: item["line"])


def _node_text(node: dict[str, Any], include_points: bool = True) -> str:
    lines = [node["text"]]
    lines.extend(item["text"] for item in node.get("continuation", []))
    if include_points:
        for point in node.get("points", []):
            lines.append(point["text"])
            lines.extend(item["text"] for item in point["continuation"])
    return "\n".join(lines)


def _point_text(point: dict[str, Any]) -> str:
    return "\n".join([point["text"], *(item["text"] for item in point["continuation"])])


def _split_long_text(text: str, max_chars: int) -> list[str]:
    """Fallback bảo toàn ký tự, ưu tiên ranh giới câu trước giới hạn cứng."""

    if len(text) <= max_chars:
        return [text]
    pieces: list[str] = []
    remaining = text
    while len(remaining) > max_chars:
        boundary = max(remaining.rfind(". ", 0, max_chars), remaining.rfind("; ", 0, max_chars))
        if boundary < max_chars // 2:
            boundary = remaining.rfind(" ", 0, max_chars)
        if boundary <= 0:
            boundary = max_chars
        else:
            boundary += 1
        pieces.append(remaining[:boundary].strip())
        remaining = remaining[boundary:].strip()
    if remaining:
        pieces.append(remaining)
    return pieces


def _context_for_article(document: dict[str, Any], article: dict[str, Any]) -> tuple[str | None, str | None]:
    for chapter in document["chapters"]:
        chapter_value = None if chapter.get("implicit") else " - ".join(
            value for value in (chapter["label"], chapter["title"]) if value
        )
        if article in chapter["articles"]:
            return chapter_value, None
        for section in chapter["sections"]:
            if article in section["articles"]:
                section_value = " - ".join(value for value in (section["label"], section["title"]) if value)
                return chapter_value, section_value
    return None, None


def _make_chunk(
    document: dict[str, Any], article: dict[str, Any], content: str, sequence: int,
    clause: str | None = None, point: str | None = None,
) -> dict[str, Any]:
    chapter, section = _context_for_article(document, article)
    identity = "|".join(
        [document["document_id"], article["number"], clause or "", point or "", str(sequence), content]
    )
    chunk_id = f"{document['document_id'].lower()}-{hashlib.sha1(identity.encode('utf-8')).hexdigest()[:16]}"
    context = [document["document_title"]]
    context.extend(value for value in (chapter, section) if value)
    if content.startswith(article["raw_heading"]):
        context.append(content)
    else:
        context.extend([article["raw_heading"], content])
    return {
        "chunk_id": chunk_id,
        "text": "\n".join(context),
        "content": content,
        "metadata": {
            "document_id": document["document_id"],
            "document_title": document["document_title"],
            "chapter": chapter,
            "section": section,
            "article": article["label"],
            "article_title": article["title"],
            "clause": f"Khoản {clause}" if clause else None,
            "point": f"Điểm {point}" if point else None,
            "source_file": document["source_file"],
            "chunk_id": chunk_id,
        },
    }


def chunk_document(document: dict[str, Any], max_chars: int = 3200) -> list[dict[str, Any]]:
    """Adaptive chunking: Điều ngắn -> Khoản -> nhóm Điểm -> fallback theo câu."""

    chunks: list[dict[str, Any]] = []
    for article in _all_articles(document):
        article_parts = [article["raw_heading"]]
        article_parts.extend(item["text"] for item in article["intro"])
        article_parts.extend(_node_text(clause) for clause in article["clauses"])
        article_parts.extend(_point_text(point) for point in article.get("orphan_points", []))
        article_text = "\n".join(article_parts)
        sequence = 0
        if len(article_text) <= max_chars or not article["clauses"]:
            for piece in _split_long_text(article_text, max_chars):
                chunks.append(_make_chunk(document, article, piece, sequence))
                sequence += 1
            continue

        # Intro của Điều được gắn vào chunk Khoản đầu để không mất ngữ cảnh.
        intro = "\n".join(item["text"] for item in article["intro"])
        for clause_index, clause in enumerate(article["clauses"]):
            clause_text = _node_text(clause)
            prefix = intro + "\n" if clause_index == 0 and intro else ""
            if len(prefix + clause_text) <= max_chars or not clause["points"]:
                for piece in _split_long_text(prefix + clause_text, max_chars):
                    chunks.append(
                        _make_chunk(document, article, piece, sequence, clause=clause["number"])
                    )
                    sequence += 1
                continue

            clause_lead = "\n".join(
                [prefix + clause["text"], *(item["text"] for item in clause["continuation"])]
            ).strip()
            group: list[dict[str, Any]] = []
            group_length = len(clause_lead)
            for point in clause["points"]:
                point_text = _point_text(point)
                if group and group_length + 1 + len(point_text) > max_chars:
                    content = "\n".join([clause_lead, *(_point_text(item) for item in group)])
                    chunks.append(
                        _make_chunk(
                            document, article, content, sequence, clause["number"],
                            f"{group[0]['number']}-{group[-1]['number']}",
                        )
                    )
                    sequence += 1
                    group = []
                    group_length = len(clause_lead)
                if len(point_text) > max_chars:
                    if group:
                        content = "\n".join([clause_lead, *(_point_text(item) for item in group)])
                        chunks.append(_make_chunk(document, article, content, sequence, clause["number"]))
                        sequence += 1
                        group = []
                        group_length = len(clause_lead)
                    for piece in _split_long_text(point_text, max_chars - min(len(clause_lead), max_chars // 3)):
                        chunks.append(
                            _make_chunk(
                                document, article, f"{clause_lead}\n{piece}", sequence,
                                clause["number"], point["number"],
                            )
                        )
                        sequence += 1
                    continue
                group.append(point)
                group_length += 1 + len(point_text)
            if group:
                content = "\n".join([clause_lead, *(_point_text(item) for item in group)])
                point_label = group[0]["number"] if len(group) == 1 else f"{group[0]['number']}-{group[-1]['number']}"
                chunks.append(
                    _make_chunk(document, article, content, sequence, clause["number"], point_label)
                )
                sequence += 1
    return chunks


def validate_document(document: dict[str, Any], chunks: list[dict[str, Any]]) -> list[str]:
    warnings = list(document["validation"]["warnings"])
    articles = _all_articles(document)
    seen_articles: set[str] = set()
    for article in articles:
        number = article["number"]
        if number in seen_articles:
            warnings.append(f"Trùng {article['label']}")
        seen_articles.add(number)
        seen_clauses: set[str] = set()
        for clause in article["clauses"]:
            if clause["number"] in seen_clauses:
                warnings.append(f"{article['label']}: trùng {clause['label']}")
            seen_clauses.add(clause["number"])
    article_chunks = {chunk["metadata"]["article"] for chunk in chunks}
    for article in articles:
        if article["label"] not in article_chunks:
            warnings.append(f"{article['label']} không tạo được chunk")
            continue
        combined_chunk_content = "\n".join(
            chunk["text"] for chunk in chunks
            if chunk["metadata"]["article"] == article["label"]
        )
        source_lines = [article["raw_heading"]]
        source_lines.extend(item["text"] for item in article["intro"])
        for clause in article["clauses"]:
            source_lines.append(clause["text"])
            source_lines.extend(item["text"] for item in clause["continuation"])
            for point in clause["points"]:
                source_lines.append(point["text"])
                source_lines.extend(item["text"] for item in point["continuation"])
        for point in article.get("orphan_points", []):
            source_lines.append(point["text"])
            source_lines.extend(item["text"] for item in point["continuation"])
        missing_content = [line for line in source_lines if line not in combined_chunk_content]
        if missing_content:
            warnings.append(
                f"{article['label']}: {len(missing_content)} dòng không xuất hiện trong chunk"
            )
    ids = [chunk["chunk_id"] for chunk in chunks]
    if len(ids) != len(set(ids)):
        warnings.append("chunk_id không duy nhất")
    return warnings


def document_stats(document: dict[str, Any], chunks: list[dict[str, Any]]) -> dict[str, int]:
    articles = _all_articles(document)
    clauses = [clause for article in articles for clause in article["clauses"]]
    points = [point for clause in clauses for point in clause["points"]]
    points.extend(point for article in articles for point in article.get("orphan_points", []))
    return {
        "chapters": sum(not chapter.get("implicit", False) for chapter in document["chapters"]),
        "sections": sum(len(chapter["sections"]) for chapter in document["chapters"]),
        "articles": len(articles), "clauses": len(clauses), "points": len(points),
        "chunks": len(chunks),
    }


def process_manifest(manifest_path: Path, output_dir: Path, max_chars: int = 3200) -> dict[str, Any]:
    """Đọc manifest M1, parse/chunk mọi tài liệu và ghi hai JSON đầu ra."""

    entries = json.loads(manifest_path.read_text(encoding="utf-8"))
    documents: list[dict[str, Any]] = []
    all_chunks: list[dict[str, Any]] = []
    report: list[dict[str, Any]] = []
    for entry in entries:
        source_path = Path(entry["output_file"])
        if not source_path.is_absolute():
            source_path = manifest_path.parent / source_path
        if not source_path.exists():
            # Manifest có thể được tạo ở máy/Drive khác: dùng tên file cạnh manifest.
            source_path = manifest_path.parent / Path(entry["output_file"]).name
        if not source_path.exists():
            raise FileNotFoundError(f"Không tìm thấy file processed: {entry['output_file']}")
        document, _ = parse_document(source_path.read_text(encoding="utf-8"), source_path.name)
        chunks = chunk_document(document, max_chars=max_chars)
        warnings = validate_document(document, chunks)
        document["validation"]["warnings"] = warnings
        stats = document_stats(document, chunks)
        documents.append(document)
        all_chunks.extend(chunks)
        report.append({"document_id": document["document_id"], **stats, "warnings": warnings})

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "structured_documents.json").write_text(
        json.dumps(documents, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "chunks.json").write_text(
        json.dumps(all_chunks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "parsing_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {"documents": documents, "chunks": all_chunks, "report": report}
