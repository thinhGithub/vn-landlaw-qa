"""Smoke checks for the optional audio environment; no model download needed."""
import asyncio
import wave
from types import SimpleNamespace

import pytest

from landlaw_rag.audio import AudioInteraction, WhisperSTT


def test_gradio_builds_and_handles_text_request():
    pytest.importorskip('gradio')
    from landlaw_rag.audio.demo import build_demo
    demo = build_demo(AudioInteraction(lambda q: {'answer': q, 'citations': []}))
    assert demo.config['components']
    queue_message = next(fn.fn for fn in demo.fns.values() if fn.fn.__name__ == 'queue_user_message')
    respond = next(fn.fn for fn in demo.fns.values() if fn.fn.__name__ == 'respond')
    queued = queue_message('Câu hỏi thử', [])
    assert queued[0] == 'Câu hỏi thử'
    assert queued[1] == [{'role': 'user', 'content': 'Câu hỏi thử'}]
    assert queued[3] == ''
    assert queued[4] == 'Đang xử lý câu hỏi…'
    result = asyncio.run(respond(queued[0], {}, False, queued[2]))
    assert result[0] == [{'role': 'user', 'content': 'Câu hỏi thử'},
                         {'role': 'assistant', 'content': 'Câu hỏi thử'}]
    assert result[1] == result[0]
    assert result[2] is None
    assert result[5] == ''
    failed = asyncio.run(respond('', {}, False, result[1]))
    assert failed[0] == result[0]
    assert failed[5] == 'Vui lòng nhập câu hỏi.'


def test_source_cards_escape_pipeline_text():
    from landlaw_rag.audio.demo import render_sources, EMPTY_SOURCES
    assert render_sources({}) == EMPTY_SOURCES
    rendered = render_sources({'citations': [
        {'number': 2, 'text': '<script>alert(1)</script>', 'chunk_ids': ['a&b']}
    ]})
    assert 'NGUỒN [2]' in rendered
    assert '<script>' not in rendered
    assert '&lt;script&gt;' in rendered
    assert 'a&amp;b' in rendered


def test_real_decoder_and_whisper_adapter_cache(tmp_path, monkeypatch):
    pytest.importorskip('av')
    fw = pytest.importorskip('faster_whisper')
    path = tmp_path / 'short.wav'
    with wave.open(str(path), 'wb') as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes(b'\x00\x00' * 3200)
    # Exercise faster-whisper's actual decoder too: catches incompatible PyAV APIs.
    from faster_whisper.audio import decode_audio
    assert len(decode_audio(str(path), sampling_rate=16000)) == 3200
    loads = []
    class Model:
        def __init__(self, *args, **kwargs):
            loads.append(1)
        def transcribe(self, path, **kwargs):
            assert kwargs['language'] == 'vi'
            return iter([SimpleNamespace(text='Xin chào')]), None
    monkeypatch.setattr(fw, 'WhisperModel', Model)
    stt = WhisperSTT()
    assert stt.transcribe(str(path)) == 'Xin chào'
    assert stt.transcribe(str(path)) == 'Xin chào'
    assert len(loads) == 1


def test_notebook_schema():
    nbformat = pytest.importorskip('nbformat')
    from pathlib import Path
    path = Path(__file__).parents[1] / '09_audio_interaction.ipynb'
    nbformat.validate(nbformat.read(path, as_version=4))
