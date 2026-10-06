"""Two-step voice interaction with lazy optional dependencies."""
from __future__ import annotations

import asyncio
import re
import time
import unicodedata
from pathlib import Path
from uuid import uuid4


def normalize_transcript(text: str) -> str:
    """Conservative suggestions; never infer document identifiers."""
    text = " ".join(unicodedata.normalize("NFC", text).split())
    digits = {"một": 1, "hai": 2, "ba": 3, "bốn": 4, "năm": 5,
              "sáu": 6, "bảy": 7, "tám": 8, "chín": 9}
    numbers = dict(digits)
    for tens in range(1, 10):
        prefix = "mười" if tens == 1 else next(k for k, v in digits.items() if v == tens) + " mươi"
        numbers[prefix] = tens * 10
        for word, value in digits.items():
            numbers[prefix + " " + word] = tens * 10 + value
        numbers[prefix + " lăm"] = tens * 10 + 5
        if tens > 1:
            numbers[prefix + " mốt"] = tens * 10 + 1
    # Capture the entire spoken number so a long number cannot be partly converted.
    words = "|".join(list(digits) + ["mười", "mươi", "mốt", "lăm", "trăm", "nghìn", "ngàn", "linh", "lẻ", "không", "triệu"])
    pattern = rf"\b(điều|khoản)\s+((?:(?:{words})\b\s*)+)"
    def replace(match):
        phrase = match[2].strip().lower()
        if phrase not in numbers:
            return match[0]
        trailing = " " if match[2][-1].isspace() else ""
        return match[1].capitalize() + " " + str(numbers[phrase]) + trailing
    text = re.sub(pattern, replace, text, flags=re.I)
    text = re.sub(r"\bđiểm\s+([a-zđ])\b", lambda m: "Điểm " + m[1].lower(), text, flags=re.I)
    for spoken, year in (("hai nghìn không trăm hai mươi bốn", "2024"),
                         ("hai nghìn không trăm mười ba", "2013")):
        text = re.sub(r"\bnăm\s+" + spoken + r"\b", "năm " + year, text, flags=re.I)
    return text


def speech_text(answer: str) -> str:
    """Strip standard M7 bibliography and markers, preserving the answer body."""
    body = re.split(r"(?m)^Căn cứ pháp lý:\s*$", answer, maxsplit=1)[0]
    body = re.sub(r"\[(?:Nguồn\s+)?\d+(?:\s*[,;]\s*\d+)*\]", "", body, flags=re.I)
    return " ".join(body.split())


class WhisperSTT:
    def __init__(self, model_size="medium", device="cuda", compute_type="float16",
                 max_seconds=120, max_bytes=20 * 1024 * 1024,
                 backend="faster-whisper"):
        self.model_size, self.device, self.compute_type = model_size, device, compute_type
        self.max_seconds, self.max_bytes = max_seconds, max_bytes
        self.backend = backend
        self._model = None

    def load_model(self):
        if self._model is not None:
            return self._model
        if self.backend == "faster-whisper":
            from faster_whisper import WhisperModel
            self._model = WhisperModel(
                self.model_size, device=self.device, compute_type=self.compute_type
            )
            return self._model
        if self.backend != "transformers":
            raise ValueError(f"STT backend không được hỗ trợ: {self.backend}")

        import torch
        from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline

        if self.device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("Đã yêu cầu CUDA cho STT nhưng runtime không có GPU")
        dtype = torch.float16 if self.compute_type == "float16" else torch.float32
        model = AutoModelForSpeechSeq2Seq.from_pretrained(
            self.model_size, torch_dtype=dtype, low_cpu_mem_usage=True
        ).to(self.device).eval()
        processor = AutoProcessor.from_pretrained(self.model_size)
        self._model = pipeline(
            "automatic-speech-recognition", model=model,
            tokenizer=processor.tokenizer,
            feature_extractor=processor.feature_extractor,
            torch_dtype=dtype, device=0 if self.device == "cuda" else -1,
            chunk_length_s=30,
        )
        return self._model

    def transcribe(self, audio_path: str) -> str:
        path = Path(audio_path)
        if not path.is_file() or not 0 < path.stat().st_size <= self.max_bytes:
            raise ValueError("Audio rỗng, không tồn tại hoặc vượt giới hạn dung lượng.")
        if path.suffix.lower() not in {".wav", ".mp3", ".m4a", ".ogg", ".webm", ".flac", ".mp4"}:
            raise ValueError("Định dạng audio không được hỗ trợ.")
        import av
        # Decode incrementally to reject long files without retaining the waveform.
        with av.open(str(path)) as container:
            duration = 0.0
            for frame in container.decode(audio=0):
                duration += frame.samples / frame.sample_rate
                if duration > self.max_seconds:
                    raise ValueError(f"Audio vượt {self.max_seconds} giây.")
        if duration <= 0:
            raise ValueError("Audio không có mẫu âm thanh.")
        model = self.load_model()
        if self.backend == "transformers":
            result = model(
                str(path), generate_kwargs={"language": "vi", "task": "transcribe"}
            )
            text = str(result.get("text", "")).strip()
        else:
            segments, _ = model.transcribe(
                str(path), language="vi", beam_size=5, vad_filter=True
            )
            text = " ".join(segment.text.strip() for segment in segments).strip()
        if not text:
            raise ValueError("Không nhận diện được lời nói. Hãy nhập câu hỏi bằng văn bản.")
        return text


class EdgeTTS:
    """Online TTS: answer text is sent to Microsoft's Edge speech service."""
    def __init__(self, voice="vi-VN-HoaiMyNeural", timeout=45):
        self.voice, self.timeout = voice, timeout

    async def synthesize(self, text: str, output_path: str) -> str:
        import edge_tts
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            await asyncio.wait_for(edge_tts.Communicate(text, self.voice).save(str(path)), self.timeout)
            if not path.is_file() or not path.stat().st_size:
                raise RuntimeError("TTS không tạo được audio.")
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return str(path)


class AudioInteraction:
    """RAG receives exact confirmed text; its result stays untouched."""
    def __init__(self, answer_question, stt=None, tts=None, output_dir="artifacts/audio"):
        self.answer_question = answer_question
        self.stt = stt if stt is not None else WhisperSTT()
        self.tts = tts if tts is not None else EdgeTTS()
        self.output_dir = Path(output_dir)

    def transcribe(self, audio_path):
        start = time.perf_counter()
        result = {"raw_transcript": "", "normalized_transcript": "", "warnings": []}
        try:
            if not audio_path:
                raise ValueError("Chọn hoặc thu âm trước khi nhận dạng.")
            result["raw_transcript"] = self.stt.transcribe(audio_path)
            result["normalized_transcript"] = normalize_transcript(result["raw_transcript"])
        except Exception as exc:
            result["warnings"].append(f"STT: {exc}")
        result["stt_latency_ms"] = (time.perf_counter() - start) * 1000
        return result

    async def answer(self, confirmed_text, transcript=None, speak=True):
        if not isinstance(confirmed_text, str) or not confirmed_text.strip():
            raise ValueError("Vui lòng nhập hoặc xác nhận câu hỏi.")
        start = time.perf_counter()
        # RAG/citation failures propagate; invalid answers must not reach TTS.
        rag = await asyncio.to_thread(self.answer_question, confirmed_text)
        rag_ms = (time.perf_counter() - start) * 1000
        if not isinstance(rag.get("answer"), str) or not rag["answer"].strip():
            raise ValueError("Pipeline RAG không trả về câu trả lời hợp lệ.")
        result = {"query": confirmed_text, "rag": rag, "audio_path": None,
                  "transcript": dict(transcript or {}), "warnings": [],
                  "rag_latency_ms": rag_ms, "tts_latency_ms": 0.0,
                  "stt_latency_ms": (transcript or {}).get("stt_latency_ms", 0.0)}
        if speak:
            tts_start = time.perf_counter()
            try:
                result["audio_path"] = await self.tts.synthesize(
                    speech_text(rag["answer"]), str(self.output_dir / f"{uuid4().hex}.mp3"))
            except Exception as exc:
                result["warnings"].append(f"TTS: {exc}. Câu trả lời văn bản vẫn khả dụng.")
            result["tts_latency_ms"] = (time.perf_counter() - tts_start) * 1000
        # Excludes human transcript editing time.
        result["total_latency_ms"] = result["stt_latency_ms"] + (time.perf_counter() - start) * 1000
        return result
