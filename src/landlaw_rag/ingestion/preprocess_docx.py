"""Tiền xử lý DOCX cho Milestone 1.

Module chỉ làm sạch văn bản, chưa phân tích Điều/Khoản/Điểm và chưa chunking.
File DOCX nguồn luôn được mở ở chế độ chỉ đọc bởi ``python-docx``.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterator

from docx import Document
from docx.document import Document as DocumentObject
from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P


PAGE_NUMBER_PATTERNS = (
    # Không xóa số đứng riêng (ví dụ năm 2024), chỉ nhận số trang có dấu bao quanh.
    re.compile(r"^\s*[-–—]\s*\d{1,4}\s*[-–—]\s*$", re.IGNORECASE),
    re.compile(r"^\s*(?:trang|page)\s+\d{1,4}(?:\s*/\s*\d{1,4})?\s*$", re.IGNORECASE),
)


@dataclass
class CleaningStats:
    source_file: str
    output_file: str = ""
    sha256: str = ""
    paragraph_count: int = 0
    empty_paragraph_count: int = 0
    table_count: int = 0
    table_row_count: int = 0
    header_footer_lines_excluded: int = 0
    page_number_lines_removed: int = 0
    duplicate_lines_removed: int = 0
    empty_lines_removed: int = 0
    removed_line_count: int = 0
    output_line_count: int = 0
    removal_log: list[dict[str, str | int]] = field(default_factory=list)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_text(text: str) -> str:
    """Chuẩn hóa Unicode và khoảng trắng trong một dòng, không đổi nội dung."""

    text = unicodedata.normalize("NFC", text)
    text = text.replace("\u00a0", " ").replace("\u200b", "")
    text = text.replace("\r", "\n")
    parts = [re.sub(r"[ \t\f\v]+", " ", part).strip() for part in text.split("\n")]
    return "\n".join(parts)


def _iter_blocks(document: DocumentObject) -> Iterator[Paragraph | Table]:
    """Duyệt paragraph và table theo đúng thứ tự xuất hiện trong XML."""

    for child in document.element.body.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, document)
        elif isinstance(child, CT_Tbl):
            yield Table(child, document)


def _table_lines(table: Table) -> Iterator[str]:
    """Biểu diễn mỗi hàng bảng thành một dòng, bỏ cell gộp bị lặp trong hàng."""

    for row in table.rows:
        cells: list[str] = []
        for cell in row.cells:
            # Một hàng bảng tương ứng đúng một dòng output để thống kê nhất quán.
            value = normalize_text(" ".join(p.text for p in cell.paragraphs)).replace("\n", " ")
            if value and (not cells or value != cells[-1]):
                cells.append(value)
        if cells:
            yield " | ".join(cells)


def _header_footer_lines(document: DocumentObject) -> list[str]:
    """Thu thập header/footer để thống kê; chúng không thuộc nội dung thân bài."""

    values: list[str] = []
    seen_parts: set[str] = set()
    for section in document.sections:
        for part in (section.header, section.first_page_header, section.even_page_header,
                     section.footer, section.first_page_footer, section.even_page_footer):
            part_key = str(part.part.partname)
            if part_key in seen_parts:
                continue
            seen_parts.add(part_key)
            for paragraph in part.paragraphs:
                value = normalize_text(paragraph.text)
                if value:
                    values.extend(line for line in value.split("\n") if line)
    return values


def _is_page_number(text: str) -> bool:
    return any(pattern.fullmatch(text) for pattern in PAGE_NUMBER_PATTERNS)


def clean_document(source: Path, output_dir: Path) -> CleaningStats:
    """Làm sạch một DOCX và ghi văn bản UTF-8 cùng log JSON."""

    source = source.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    document = Document(str(source))
    output_path = output_dir / f"{source.stem}.txt"
    stats = CleaningStats(source_file=str(source), output_file=str(output_path.resolve()))
    stats.sha256 = _sha256(source)
    stats.paragraph_count = len(document.paragraphs)
    stats.empty_paragraph_count = sum(not normalize_text(p.text) for p in document.paragraphs)

    header_footer = _header_footer_lines(document)
    stats.header_footer_lines_excluded = len(header_footer)
    for value, count in Counter(header_footer).items():
        stats.removal_log.append(
            {"reason": "header_footer", "text": value, "count": count}
        )

    raw_lines: list[str] = []
    for block in _iter_blocks(document):
        if isinstance(block, Paragraph):
            raw_lines.extend(normalize_text(block.text).split("\n"))
        else:
            stats.table_count += 1
            stats.table_row_count += len(block.rows)
            raw_lines.extend(_table_lines(block))

    clean_lines: list[str] = []
    previous_nonempty: str | None = None
    for line_number, line in enumerate(raw_lines, start=1):
        line = normalize_text(line)
        if not line:
            stats.empty_lines_removed += 1
            continue
        if _is_page_number(line):
            stats.page_number_lines_removed += 1
            stats.removal_log.append(
                {"reason": "page_number", "text": line, "line": line_number}
            )
            continue
        if line == previous_nonempty:
            stats.duplicate_lines_removed += 1
            stats.removal_log.append(
                {"reason": "consecutive_duplicate", "text": line, "line": line_number}
            )
            continue
        clean_lines.append(line)
        previous_nonempty = line

    stats.removed_line_count = (
        stats.empty_lines_removed
        + stats.page_number_lines_removed
        + stats.duplicate_lines_removed
        + stats.header_footer_lines_excluded
    )
    stats.output_line_count = len(clean_lines)
    output_path.write_text("\n".join(clean_lines) + "\n", encoding="utf-8")
    output_path.with_suffix(".stats.json").write_text(
        json.dumps(asdict(stats), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return stats


def process_directory(input_dir: Path, output_dir: Path) -> list[CleaningStats]:
    """Làm sạch toàn bộ DOCX trong thư mục và ghi manifest tổng hợp."""

    input_dir = input_dir.resolve()
    output_dir = output_dir.resolve()
    sources = sorted(input_dir.glob("*.docx"), key=lambda path: path.name.casefold())
    if not sources:
        raise FileNotFoundError(f"Không tìm thấy DOCX trong: {input_dir}")

    results = [clean_document(source, output_dir) for source in sources]
    (output_dir / "manifest.json").write_text(
        json.dumps([asdict(item) for item in results], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return results
