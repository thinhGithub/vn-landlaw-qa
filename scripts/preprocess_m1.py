"""CLI cho Milestone 1: trích xuất và làm sạch DOCX."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from landlaw_rag.ingestion import process_directory  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tiền xử lý DOCX pháp luật (M1)")
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "raw_doc",
        help="Thư mục chứa DOCX nguồn",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "processed",
        help="Thư mục ghi TXT sạch và thống kê JSON",
    )
    return parser.parse_args()


def main() -> int:
    # Một số terminal Windows mặc định dùng CP1252 và không in được tiếng Việt.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args()
    results = process_directory(args.input_dir, args.output_dir)

    print(f"Đã xử lý {len(results)} văn bản\n")
    for item in results:
        print(Path(item.source_file).name)
        print(f"  Paragraph:             {item.paragraph_count}")
        print(f"  Paragraph rỗng:        {item.empty_paragraph_count}")
        print(f"  Header/footer loại:    {item.header_footer_lines_excluded}")
        print(f"  Số trang loại:         {item.page_number_lines_removed}")
        print(f"  Text lặp loại:         {item.duplicate_lines_removed}")
        print(f"  Dòng rỗng loại:        {item.empty_lines_removed}")
        print(f"  Tổng số dòng bị loại:  {item.removed_line_count}")
        print(f"  Số dòng đầu ra:        {item.output_line_count}")
        print(f"  Output: {item.output_file}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
