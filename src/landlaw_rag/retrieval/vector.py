"""Vector retrieval với Sentence Transformers và FAISS cho Milestone 4."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


INDEX_FILENAME = "faiss.index"
METADATA_FILENAME = "vector_metadata.json"
MANIFEST_FILENAME = "embedding_manifest.json"
EMBEDDINGS_FILENAME = "embeddings.npy"
FORMAT_VERSION = 1


@dataclass(frozen=True)
class VectorConfig:
    model_name: str = "intfloat/multilingual-e5-base"
    batch_size: int = 32
    max_seq_length: int = 512
    top_k: int = 10
    normalize_embeddings: bool = True
    passage_prefix: str = "passage: "
    query_prefix: str = "query: "
    save_embeddings: bool = True


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def format_passage(text: str, prefix: str = "passage: ") -> str:
    text = " ".join(str(text).split())
    if not text:
        raise ValueError("Passage không được rỗng")
    return f"{prefix}{text}"


def format_query(text: str, prefix: str = "query: ") -> str:
    text = " ".join(str(text).split())
    if not text:
        raise ValueError("Query không được rỗng")
    return f"{prefix}{text}"


def load_and_validate_chunks(chunks_path: Path) -> list[dict[str, Any]]:
    chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
    if not isinstance(chunks, list) or not chunks:
        raise ValueError("chunks.json phải là danh sách không rỗng")
    ids: list[str] = []
    for position, chunk in enumerate(chunks):
        chunk_id = str(chunk.get("chunk_id", "")).strip()
        text = str(chunk.get("text", "")).strip()
        metadata = chunk.get("metadata")
        if not chunk_id or not text or not isinstance(metadata, dict):
            raise ValueError(f"Chunk tại vị trí {position} thiếu id/text/metadata")
        if metadata.get("chunk_id") != chunk_id:
            raise ValueError(f"Metadata chunk_id không khớp: {chunk_id}")
        ids.append(chunk_id)
    if len(ids) != len(set(ids)):
        raise ValueError("chunks.json chứa chunk_id trùng")
    return chunks


def validate_parsing_report(report_path: Path) -> None:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    warnings = [
        f"{item.get('document_id')}: {warning}"
        for item in report
        for warning in item.get("warnings", [])
    ]
    if warnings:
        raise ValueError("Parsing report còn cảnh báo:\n" + "\n".join(warnings[:10]))


def _runtime_modules() -> tuple[Any, Any, Any, Any]:
    try:
        import faiss
        import numpy as np
        import torch
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "Thiếu dependency M4. Chạy: pip install -r requirements/retrieval.txt"
        ) from exc
    return faiss, np, torch, SentenceTransformer


def _resolve_device(requested: str | None, torch_module: Any) -> str:
    if requested:
        if requested == "cuda" and not torch_module.cuda.is_available():
            raise RuntimeError("Đã yêu cầu CUDA nhưng runtime không có GPU khả dụng")
        return requested
    return "cuda" if torch_module.cuda.is_available() else "cpu"


class VectorIndex:
    """Build/load FAISS index và cung cấp semantic search Top-k."""

    def __init__(
        self,
        index: Any,
        records: list[dict[str, Any]],
        manifest: dict[str, Any],
        config: VectorConfig,
        device: str | None = None,
        encoder: Any | None = None,
    ) -> None:
        self.index = index
        self.records = records
        self.manifest = manifest
        self.config = config
        self.device = device
        self._encoder = encoder
        self._validate_loaded_artifacts()

    @classmethod
    def build(
        cls,
        chunks_path: Path,
        parsing_report_path: Path,
        output_dir: Path,
        config: VectorConfig | None = None,
        device: str | None = None,
    ) -> "VectorIndex":
        config = config or VectorConfig()
        validate_parsing_report(parsing_report_path)
        chunks = load_and_validate_chunks(chunks_path)
        faiss, np, torch, SentenceTransformer = _runtime_modules()
        resolved_device = _resolve_device(device, torch)

        encoder = SentenceTransformer(config.model_name, device=resolved_device)
        encoder.max_seq_length = config.max_seq_length
        passages = [format_passage(chunk["text"], config.passage_prefix) for chunk in chunks]

        if resolved_device == "cuda":
            torch.cuda.reset_peak_memory_stats()
        started = time.perf_counter()
        embeddings = encoder.encode(
            passages,
            batch_size=config.batch_size,
            show_progress_bar=True,
            convert_to_numpy=True,
            normalize_embeddings=config.normalize_embeddings,
        )
        elapsed = time.perf_counter() - started
        embeddings = np.ascontiguousarray(embeddings, dtype="float32")
        if embeddings.ndim != 2 or embeddings.shape[0] != len(chunks):
            raise ValueError(f"Embedding shape không hợp lệ: {embeddings.shape}")
        if not np.isfinite(embeddings).all():
            raise ValueError("Embedding chứa NaN hoặc Inf")

        index = faiss.IndexFlatIP(int(embeddings.shape[1]))
        index.add(embeddings)
        records = [
            {
                "faiss_id": position,
                "chunk_id": chunk["chunk_id"],
                "text": chunk["text"],
                "metadata": chunk["metadata"],
            }
            for position, chunk in enumerate(chunks)
        ]
        peak_gpu_mb = None
        if resolved_device == "cuda":
            peak_gpu_mb = round(torch.cuda.max_memory_allocated() / 1024**2, 2)
        manifest = {
            "format_version": FORMAT_VERSION,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "chunks_path": str(chunks_path.resolve()),
            "chunks_sha256": sha256_file(chunks_path),
            "chunk_count": len(chunks),
            "embedding_dimension": int(embeddings.shape[1]),
            "faiss_index_type": "IndexFlatIP",
            "similarity": "cosine" if config.normalize_embeddings else "inner_product",
            "config": asdict(config),
            "build_metrics": {
                "device": resolved_device,
                "elapsed_seconds": round(elapsed, 4),
                "chunks_per_second": round(len(chunks) / elapsed, 4),
                "peak_gpu_memory_mb": peak_gpu_mb,
            },
        }

        output_dir.mkdir(parents=True, exist_ok=True)
        faiss.write_index(index, str(output_dir / INDEX_FILENAME))
        (output_dir / METADATA_FILENAME).write_text(
            json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (output_dir / MANIFEST_FILENAME).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        if config.save_embeddings:
            np.save(output_dir / EMBEDDINGS_FILENAME, embeddings)
        return cls(index, records, manifest, config, resolved_device, encoder)

    @classmethod
    def load(
        cls,
        output_dir: Path,
        device: str | None = None,
        load_encoder: bool = True,
        chunks_path: Path | None = None,
    ) -> "VectorIndex":
        faiss, _, torch, SentenceTransformer = _runtime_modules()
        manifest = json.loads((output_dir / MANIFEST_FILENAME).read_text(encoding="utf-8"))
        records = json.loads((output_dir / METADATA_FILENAME).read_text(encoding="utf-8"))
        index = faiss.read_index(str(output_dir / INDEX_FILENAME))
        config = VectorConfig(**manifest["config"])
        if chunks_path is not None and sha256_file(chunks_path) != manifest["chunks_sha256"]:
            raise ValueError("FAISS index không khớp phiên bản chunks.json hiện tại; cần rebuild")
        resolved_device = _resolve_device(device, torch)
        encoder = None
        if load_encoder:
            encoder = SentenceTransformer(config.model_name, device=resolved_device)
            encoder.max_seq_length = config.max_seq_length
        return cls(index, records, manifest, config, resolved_device, encoder)

    def _validate_loaded_artifacts(self) -> None:
        expected_count = int(self.manifest.get("chunk_count", -1))
        expected_dimension = int(self.manifest.get("embedding_dimension", -1))
        if self.index.ntotal != len(self.records) or len(self.records) != expected_count:
            raise ValueError("Số vector, metadata và manifest không khớp")
        if self.index.d != expected_dimension:
            raise ValueError("Số chiều FAISS index không khớp manifest")
        ids = [record["chunk_id"] for record in self.records]
        if len(ids) != len(set(ids)):
            raise ValueError("Vector metadata chứa chunk_id trùng")
        if any(record["faiss_id"] != position for position, record in enumerate(self.records)):
            raise ValueError("Ánh xạ faiss_id không liên tục")

    def query(self, query: str, top_k: int | None = None) -> list[dict[str, Any]]:
        if self._encoder is None:
            raise RuntimeError("Encoder chưa được load; gọi load(..., load_encoder=True)")
        _, np, _, _ = _runtime_modules()
        limit = min(top_k or self.config.top_k, len(self.records))
        if limit <= 0:
            raise ValueError("top_k phải lớn hơn 0")
        query_embedding = self._encoder.encode(
            [format_query(query, self.config.query_prefix)],
            convert_to_numpy=True,
            normalize_embeddings=self.config.normalize_embeddings,
            show_progress_bar=False,
        )
        query_embedding = np.ascontiguousarray(query_embedding, dtype="float32")
        scores, indices = self.index.search(query_embedding, limit)
        results: list[dict[str, Any]] = []
        for score, faiss_id in zip(scores[0], indices[0]):
            if faiss_id < 0:
                continue
            record = self.records[int(faiss_id)]
            results.append(
                {
                    "chunk_id": record["chunk_id"],
                    "vector_score": float(score),
                    "text": record["text"],
                    "metadata": record["metadata"],
                    "faiss_id": int(faiss_id),
                }
            )
        return results
