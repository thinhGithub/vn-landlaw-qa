"""Build/load BM25 index và chạy các truy vấn kiểm tra Milestone 3."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from landlaw_rag.retrieval import BM25Config, BM25Index  # noqa: E402


DEFAULT_QUERIES = (
    "điều kiện cấp Giấy chứng nhận quyền sử dụng đất",
    "thu hồi đất để phát triển kinh tế xã hội vì lợi ích quốc gia công cộng",
    "Điều 75 Khoản 1 Luật Đất đai 2024",
    "Khoản 2 Điều 57 Luật 45/2013/QH13",
    "bảng giá đất Nghị quyết 254/2025/QH15",
)


def _resolve(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def load_config(config_path: Path) -> tuple[BM25Config, dict[str, Path]]:
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    bm25 = raw["bm25"]
    boost = raw["metadata_boost"]
    config = BM25Config(
        k1=float(bm25["k1"]), b=float(bm25["b"]), top_k=int(bm25["top_k"]),
        document_boost=float(boost["document"]),
        article_boost=float(boost["article"]),
        clause_boost=float(boost["clause"]), point_boost=float(boost["point"]),
    )
    return config, {key: _resolve(value) for key, value in raw["paths"].items()}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="BM25 Retrieval Baseline (M3)")
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / "configs" / "bm25.yaml")
    parser.add_argument("--rebuild", action="store_true", help="Build lại index dù file đã tồn tại")
    parser.add_argument("--query", action="append", help="Query tùy chọn; có thể truyền nhiều lần")
    parser.add_argument("--top-k", type=int, help="Ghi đè top_k trong config")
    return parser.parse_args()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args()
    config, paths = load_config(args.config)
    if args.rebuild or not paths["index"].exists():
        index = BM25Index.build(paths["chunks"], paths["parsing_report"], config)
        index.save(paths["index"])
        action = "Đã build và lưu"
    else:
        index = BM25Index.load(paths["index"])
        action = "Đã load"
    print(
        f"{action} BM25 index: {paths['index']}\n"
        f"Số chunk: {len(index.documents)} | Avg document length: "
        f"{index.average_document_length:.2f} token\n"
    )

    queries = args.query or DEFAULT_QUERIES
    for query in queries:
        print(f"QUERY: {query}")
        for rank, result in enumerate(index.query(query, args.top_k), start=1):
            metadata = result["metadata"]
            citation = " – ".join(
                str(value) for value in (
                    metadata.get("document_title"), metadata.get("article"),
                    metadata.get("clause"), metadata.get("point"),
                ) if value
            )
            print(
                f"  {rank}. score={result['score']:.4f} "
                f"(bm25={result['bm25_score']:.4f}, boost={result['metadata_boost']:.1f})\n"
                f"     {citation}\n"
                f"     chunk_id={result['chunk_id']}"
            )
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
