"""CLI cho Milestone 2: legal parsing và adaptive chunking."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from landlaw_rag.chunking import process_manifest  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Legal parsing và adaptive chunking (M2)")
    parser.add_argument(
        "--manifest", type=Path, default=PROJECT_ROOT / "data" / "processed" / "manifest.json"
    )
    parser.add_argument(
        "--output-dir", type=Path, default=PROJECT_ROOT / "data" / "processed"
    )
    parser.add_argument(
        "--max-chars", type=int, default=3200,
        help="Giới hạn gần đúng cho một chunk; dùng ký tự để không phụ thuộc tokenizer",
    )
    return parser.parse_args()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args()
    result = process_manifest(args.manifest, args.output_dir, args.max_chars)
    print(f"Đã parse {len(result['documents'])} văn bản, tạo {len(result['chunks'])} chunks\n")
    for item in result["report"]:
        print(item["document_id"])
        print(
            f"  Chương: {item['chapters']} | Mục: {item['sections']} | "
            f"Điều: {item['articles']} | Khoản: {item['clauses']} | "
            f"Điểm: {item['points']} | Chunk: {item['chunks']}"
        )
        if item["warnings"]:
            print(f"  Cảnh báo ({len(item['warnings'])}):")
            for warning in item["warnings"][:10]:
                print(f"    - {warning}")
        else:
            print("  Validation: OK")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
