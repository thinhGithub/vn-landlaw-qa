"""Hugging Face Spaces entrypoint for the Gradio LandLaw RAG app."""

from __future__ import annotations

import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from landlaw_rag.audio import AudioInteraction, EdgeTTS, WhisperSTT
from landlaw_rag.audio.demo import build_demo
from landlaw_rag.audio.runtime import load_colab_rag


def create_demo():
    """Load indexes/models once, then expose the existing Gradio interface."""
    required = (
        PROJECT_ROOT / "data/processed/chunks.json",
        PROJECT_ROOT / "indexes/bm25/bm25_index.json.gz",
        PROJECT_ROOT / "indexes/faiss/faiss.index",
        PROJECT_ROOT / "indexes/faiss/vector_metadata.json",
        PROJECT_ROOT / "indexes/faiss/embedding_manifest.json",
    )
    missing = [str(path.relative_to(PROJECT_ROOT)) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("Space thiếu RAG artifacts: " + ", ".join(missing))

    rag = load_colab_rag(
        PROJECT_ROOT,
        model_name=os.getenv("LANDLAW_MODEL", "Qwen/Qwen3.5-4B"),
        strict_citations=True,
    )
    interaction = AudioInteraction(
        rag,
        stt=WhisperSTT(
            model_size=os.getenv("LANDLAW_STT_MODEL", "vinai/PhoWhisper-medium"),
            device="cuda",
            compute_type="float16",
            backend="transformers",
        ),
        tts=EdgeTTS(voice=os.getenv("LANDLAW_TTS_VOICE", "vi-VN-HoaiMyNeural")),
        output_dir=os.getenv("AUDIO_OUTPUT_DIR", "/tmp/landlaw-audio"),
    )
    return build_demo(interaction)


demo = create_demo()
