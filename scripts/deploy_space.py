"""Upload the runnable Gradio app and its RAG artifacts to an existing Space."""

from __future__ import annotations

import os
from pathlib import Path

from huggingface_hub import HfApi


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPACE_ID = os.environ.get("HF_SPACE_ID", "").strip()
TOKEN = os.environ.get("HF_TOKEN", "").strip()


def main() -> None:
    if not SPACE_ID or "/" not in SPACE_ID:
        raise SystemExit("Set HF_SPACE_ID to the existing Space id, e.g. username/landlaw-ai.")
    if not TOKEN:
        raise SystemExit("Set HF_TOKEN to a Hugging Face token with write access to the Space.")

    api = HfApi(token=TOKEN)
    api.upload_folder(
        repo_id=SPACE_ID,
        repo_type="space",
        folder_path=PROJECT_ROOT,
        allow_patterns=[
            "README.md",
            "app.py",
            "requirements.txt",
            "requirements/**",
            "src/**",
            "data/processed/chunks.json",
            "indexes/bm25/bm25_index.json.gz",
            "indexes/faiss/faiss.index",
            "indexes/faiss/vector_metadata.json",
            "indexes/faiss/embedding_manifest.json",
        ],
        commit_message="Deploy LandLaw Gradio app",
    )
    print(f"Uploaded app and RAG artifacts to https://huggingface.co/spaces/{SPACE_ID}")


if __name__ == "__main__":
    main()
