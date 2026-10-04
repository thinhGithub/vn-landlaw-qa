"""Build/load FAISS index và chạy semantic search cho Milestone 4."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from landlaw_rag.retrieval import VectorConfig, VectorIndex  # noqa: E402


DEFAULT_QUERIES = (
    "Điều kiện để người sử dụng đất được cấp giấy chứng nhận là gì?",
    "Khi nào Nhà nước thu hồi đất để phát triển kinh tế xã hội?",
    "Bảng giá đất được xây dựng và áp dụng như thế nào?",
    "Quyền chuyển nhượng quyền sử dụng đất của cá nhân",
)


def _resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def load_config(config_path: Path) -> tuple[VectorConfig, dict[str, Path]]:
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    embedding = raw["embedding"]
    config = VectorConfig(
        model_name=str(embedding["model_name"]),
        batch_size=int(embedding["batch_size"]),
        max_seq_length=int(embedding["max_seq_length"]),
        top_k=int(raw["retrieval"]["top_k"]),
        normalize_embeddings=bool(embedding["normalize_embeddings"]),
        passage_prefix=str(embedding["passage_prefix"]),
        query_prefix=str(embedding["query_prefix"]),
        save_embeddings=bool(embedding["save_embeddings"]),
    )
    return config, {key: _resolve(value) for key, value in raw["paths"].items()}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Vector Retrieval với FAISS (M4)")
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / "configs" / "vector.yaml")
    parser.add_argument("--rebuild", action="store_true", help="Sinh lại embedding và FAISS index")
    parser.add_argument("--build-only", action="store_true", help="Build/load và kiểm tra, không query")
    parser.add_argument("--query", action="append", help="Query tùy chọn; có thể truyền nhiều lần")
    parser.add_argument("--top-k", type=int, help="Ghi đè top_k trong config")
    parser.add_argument("--device", choices=("cpu", "cuda"), help="Thiết bị encode")
    return parser.parse_args()


def _print_summary(index: VectorIndex, action: str, output_dir: Path) -> None:
    metrics = index.manifest.get("build_metrics", {})
    print(f"{action} vector index: {output_dir}")
    print(
        f"Vectors: {index.index.ntotal} | Dimension: {index.index.d} | "
        f"Model: {index.config.model_name}"
    )
    if metrics:
        print("Build metrics:", json.dumps(metrics, ensure_ascii=False))


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args()
    config, paths = load_config(args.config)
    index_file = paths["output_dir"] / "faiss.index"
    if args.rebuild or not index_file.exists():
        index = VectorIndex.build(
            paths["chunks"], paths["parsing_report"], paths["output_dir"],
            config=config, device=args.device,
        )
        action = "Đã build và lưu"
    else:
        index = VectorIndex.load(
            paths["output_dir"], device=args.device,
            load_encoder=not args.build_only, chunks_path=paths["chunks"],
        )
        action = "Đã load"
    _print_summary(index, action, paths["output_dir"])
    if args.build_only:
        return 0

    for query in args.query or DEFAULT_QUERIES:
        print(f"\nQUERY: {query}")
        for rank, result in enumerate(index.query(query, args.top_k), start=1):
            metadata = result["metadata"]
            citation = " – ".join(
                str(value) for value in (
                    metadata.get("document_title"), metadata.get("article"),
                    metadata.get("clause"), metadata.get("point"),
                ) if value
            )
            print(
                f"  {rank}. vector_score={result['vector_score']:.6f}\n"
                f"     {citation}\n"
                f"     chunk_id={result['chunk_id']} | faiss_id={result['faiss_id']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
