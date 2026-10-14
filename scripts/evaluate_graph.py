"""Run a paired Hybrid vs Hybrid+Graph retrieval ablation (M10)."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
import sys
from pathlib import Path
from time import perf_counter
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from landlaw_rag.evaluation import evaluate_graph_ablation  # noqa: E402
from landlaw_rag.retrieval import (  # noqa: E402
    BM25Index, BM25Retriever, GraphConfig, GraphRetriever,
    HybridConfig, HybridRetriever, VectorIndex, VectorRetriever,
)


def _resolve(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _build_retrievers(args: argparse.Namespace):
    bm25_raw = yaml.safe_load(args.bm25_config.read_text(encoding="utf-8"))
    vector_raw = yaml.safe_load(args.vector_config.read_text(encoding="utf-8"))
    pipeline = yaml.safe_load(args.pipeline_config.read_text(encoding="utf-8"))

    bm25_paths = {key: _resolve(value) for key, value in bm25_raw["paths"].items()}
    bm25_path = bm25_paths["index"]
    bm25_index = BM25Index.load(bm25_path)

    vector_paths = {key: _resolve(value) for key, value in vector_raw["paths"].items()}
    vector_index = VectorIndex.load(
        vector_paths["output_dir"], device=args.device, load_encoder=True,
        chunks_path=vector_paths["chunks"],
    )

    retrieval = pipeline.get("retrieval", {})
    hybrid = HybridRetriever(
        BM25Retriever(bm25_index), VectorRetriever(vector_index),
        HybridConfig(
            bm25_top_n=int(retrieval.get("bm25_top_k", 20)),
            vector_top_n=int(retrieval.get("vector_top_k", 20)),
            final_top_k=int(retrieval.get("final_top_k", 8)),
            rrf_k=int(retrieval.get("rrf_k", 60)),
        ),
    )
    graph_args = dict(pipeline.get("graph", {}))
    if "allowed_relations" in graph_args:
        graph_args["allowed_relations"] = tuple(graph_args["allowed_relations"])
    chunks = json.loads(args.chunks.read_text(encoding="utf-8"))
    graph_config = GraphConfig(**graph_args)
    build_tick = perf_counter()
    graph = GraphRetriever(hybrid, chunks, graph_config)
    graph_build_ms = (perf_counter() - build_tick) * 1000
    if args.graph_snapshot:
        graph.save(args.graph_snapshot)
    run_config = {
        "embedding_model": vector_index.config.model_name,
        "hybrid": asdict(hybrid.config),
        "graph": asdict(graph.config),
        "graph_build_ms": graph_build_ms,
        "chunks_sha256": hashlib.sha256(args.chunks.read_bytes()).hexdigest(),
    }
    return hybrid, graph, run_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Hybrid vs Hybrid+Graph evaluation")
    parser.add_argument("--gold", type=Path, default=PROJECT_ROOT / "data/evaluation/graph_retrieval.jsonl")
    parser.add_argument("--judgments", type=Path, help="Optional human answer/citation review JSONL")
    parser.add_argument("--chunks", type=Path, default=PROJECT_ROOT / "data/processed/chunks.json")
    parser.add_argument("--bm25-config", type=Path, default=PROJECT_ROOT / "configs/bm25.yaml")
    parser.add_argument("--vector-config", type=Path, default=PROJECT_ROOT / "configs/vector.yaml")
    parser.add_argument("--pipeline-config", type=Path, default=PROJECT_ROOT / "configs/pipeline.yaml")
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--device", choices=("cpu", "cuda"))
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "artifacts/evaluation/graph_ablation.json")
    parser.add_argument("--graph-snapshot", type=Path, help="Optional JSON graph export for inspection")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    chunks = json.loads(args.chunks.read_text(encoding="utf-8"))
    cases = _read_jsonl(args.gold)
    judgments = _read_jsonl(args.judgments) if args.judgments else None
    if judgments:
        expected_ids = {str(case["question_id"]) for case in cases}
        seen_ids: set[str] = set()
        for row in judgments:
            question_id = str(row.get("question_id") or "")
            if question_id not in expected_ids:
                raise ValueError(f"Unknown judgment question_id: {question_id}")
            if question_id in seen_ids:
                raise ValueError(f"Duplicate judgment question_id: {question_id}")
            seen_ids.add(question_id)
    hybrid, graph, run_config = _build_retrievers(args)
    report = evaluate_graph_ablation(
        cases, chunks, hybrid, graph, top_k=args.top_k, answer_judgments=judgments,
    )
    report["configuration"] = run_config
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved report: {args.output}")
    print(json.dumps(report["systems"], ensure_ascii=False, indent=2))
    print("Human answer/citation judgments:", json.dumps(
        report["human_answer_and_citation_judgments"], ensure_ascii=False,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
