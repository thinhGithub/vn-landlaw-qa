import asyncio
from copy import deepcopy
import pytest
from landlaw_rag.audio import AudioInteraction, WhisperSTT, normalize_transcript, speech_text
from landlaw_rag.audio.runtime import RAGAdapter
from landlaw_rag.generation import CitationValidationError, INSUFFICIENT_EVIDENCE_MESSAGE
from landlaw_rag.comparison import MISSING_COUNTERPART_MESSAGE


@pytest.mark.parametrize('raw,expected', [
    ('điều bốn mươi lăm, khoản một, điểm a', 'Điều 45, Khoản 1, Điểm a'),
    ('năm hai nghìn không trăm hai mươi bốn', 'năm 2024'),
    ('Điều một trăm tám mươi tám', 'Điều một trăm tám mươi tám'),
    ('31/2024/QH15', '31/2024/QH15'),
    ('chuyển nhượng một phần đất', 'chuyển nhượng một phần đất'),
])
def test_normalization(raw, expected):
    assert normalize_transcript(raw) == expected


def test_speech_text():
    assert speech_text('Điều 45 năm 2024. [1]\n\nCăn cứ pháp lý:\n[1] Luật') == 'Điều 45 năm 2024.'


class STT:
    def transcribe(self, path):
        return 'điều bốn mươi lăm'


class TTS:
    def __init__(self):
        self.spoken = []
    async def synthesize(self, text, path):
        self.spoken.append(text)
        return path


class Broken:
    def transcribe(self, path):
        raise RuntimeError('offline')
    async def synthesize(self, text, path):
        raise TimeoutError('offline')


def test_confirmation_preserves_rag_and_exact_query():
    calls = []
    rag = {'answer': 'Nội dung. [1]\n\nCăn cứ pháp lý:\n[1] Luật', 'citations': [{'chunk_ids': ['c1']}]}
    before = deepcopy(rag)
    tts = TTS()
    voice = AudioInteraction(lambda q: calls.append(q) or rag, STT(), tts)
    transcript = voice.transcribe('input.wav')
    assert calls == []
    assert transcript['normalized_transcript'] == 'Điều 45'
    result = asyncio.run(voice.answer(' Điều 46? ', transcript))
    assert calls == [' Điều 46? ']
    assert result['rag'] == rag == before
    assert tts.spoken == ['Nội dung.']
    assert result['total_latency_ms'] >= result['stt_latency_ms']


def test_errors_fall_back_to_text():
    voice = AudioInteraction(lambda q: {'answer': q}, Broken(), Broken())
    transcript = voice.transcribe('bad.wav')
    assert transcript['warnings']
    result = asyncio.run(voice.answer('Nhập tay', transcript))
    assert result['rag']['answer'] == 'Nhập tay'
    assert result['audio_path'] is None and result['warnings']
    result = asyncio.run(voice.answer('Nhập tay', speak=False))
    assert not result['warnings'] and result['tts_latency_ms'] == 0


def test_invalid_citation_never_spoken():
    def invalid(query):
        raise CitationValidationError('bad source')
    tts = TTS()
    with pytest.raises(CitationValidationError):
        asyncio.run(AudioInteraction(invalid, tts=tts).answer('Câu hỏi'))
    assert not tts.spoken


@pytest.mark.parametrize('text', ['', ' ', None])
def test_empty_query(text):
    with pytest.raises(ValueError):
        asyncio.run(AudioInteraction(lambda q: pytest.fail('RAG called')).answer(text))


def test_invalid_audio_before_model_load(tmp_path):
    stt = WhisperSTT()
    with pytest.raises(ValueError):
        stt.transcribe(str(tmp_path / 'missing.wav'))
    path = tmp_path / 'bad.txt'
    path.write_text('not audio')
    with pytest.raises(ValueError, match='Định dạng'):
        stt.transcribe(str(path))
    assert stt._model is None


def chunk(cid, doc):
    return {'chunk_id': cid, 'text': 'Nghĩa vụ sử dụng đất.',
            'metadata': {'document_id': doc, 'article': 'Điều 1', 'clause': 'Khoản 1'}}


class Tokenizer:
    def encode(self, text, **kwargs):
        return list(text)
    def decode(self, ids, **kwargs):
        return ''.join(ids)


class Retriever:
    def __init__(self, hits):
        self.hits = hits
    def search(self, query, top_k):
        return self.hits[:top_k]


def test_qa_uses_real_validation_and_isolation():
    hits = [chunk('old', '45-2013-QH13'), chunk('new', '31-2024-QH15')]
    adapter = RAGAdapter(Retriever(hits), hits, Tokenizer(), lambda _: 'Nội dung. [Nguồn 1]')
    result = asyncio.run(AudioInteraction(adapter, tts=TTS()).answer('Quy định hiện hành?'))
    assert [s['chunk_id'] for s in result['rag']['sources']] == ['new']
    assert result['rag']['citations'][0]['chunk_ids'] == ('new',)


def test_comparison_through_voice():
    hits = [chunk('old', '45-2013-QH13'), chunk('new', '31-2024-QH15')]
    outputs = iter([
        '1. Quy định năm 2013: Cũ. [Nguồn 1]\n2. Quy định hiện hành: Mới. [Nguồn 2]',
        '3. Điểm giống: Chung. [Nguồn 1] [Nguồn 2]\n4. Điểm khác/thay đổi: Khác. [Nguồn 1] [Nguồn 2]',
    ])
    adapter = RAGAdapter(Retriever(hits), hits, Tokenizer(), lambda _: next(outputs))
    result = asyncio.run(AudioInteraction(adapter, tts=TTS()).answer('So sánh năm 2013 và 2024'))
    assert result['rag']['mode'] == 'comparison'
    assert len(result['rag']['claim_citation_mapping']) == 4
    assert result['rag']['claim_citation_mapping'][2]['chunk_ids'] == ('old', 'new')


@pytest.mark.parametrize('question,expected', [
    ('Câu hỏi?', INSUFFICIENT_EVIDENCE_MESSAGE),
    ('So sánh năm 2013 và 2024', MISSING_COUNTERPART_MESSAGE),
])
def test_missing_evidence(question, expected):
    adapter = RAGAdapter(Retriever([]), [], Tokenizer(), lambda _: pytest.fail('Generation called'))
    assert adapter(question)['answer'] == expected


def test_hallucinated_source_rejected():
    hits = [chunk('new', '31-2024-QH15')]
    adapter = RAGAdapter(Retriever(hits), hits, Tokenizer(), lambda _: 'Claim. [Nguồn 99]')
    with pytest.raises(CitationValidationError):
        adapter('Câu hỏi?')


def test_demo_mode_allows_uncited_claim_but_rejects_fake_source():
    hits = [chunk('new', '31-2024-QH15')]
    adapter = RAGAdapter(
        Retriever(hits), hits, Tokenizer(),
        lambda _: 'Claim demo chưa có nhãn nguồn.',
        strict_citations=False,
    )
    assert adapter('Câu hỏi?')['answer'] == 'Claim demo chưa có nhãn nguồn.'

    adapter.generate = lambda _: 'Claim có nguồn giả. [Nguồn 99]'
    with pytest.raises(CitationValidationError):
        adapter('Câu hỏi?')


def test_tts_timeout_cleans_partial_output(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace
    from landlaw_rag.audio import EdgeTTS
    class Communicate:
        def __init__(self, *args):
            pass
        async def save(self, path):
            from pathlib import Path
            Path(path).write_bytes(b'partial')
            await asyncio.sleep(1)
    monkeypatch.setitem(sys.modules, 'edge_tts', SimpleNamespace(Communicate=Communicate))
    path = tmp_path / 'partial.mp3'
    with pytest.raises(TimeoutError):
        asyncio.run(EdgeTTS(timeout=0.01).synthesize('Xin chào', str(path)))
    assert not path.exists()


def test_audio_duration_limit_before_model_load(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace
    class Container:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def decode(self, audio):
            yield SimpleNamespace(samples=16000 * 121, sample_rate=16000)
    monkeypatch.setitem(sys.modules, 'av', SimpleNamespace(open=lambda _: Container()))
    path = tmp_path / 'long.wav'
    path.write_bytes(b'audio')
    stt = WhisperSTT()
    with pytest.raises(ValueError, match='120'):
        stt.transcribe(str(path))
    assert stt._model is None


def test_comparison_retry_then_success():
    hits = [chunk('old', '45-2013-QH13'), chunk('new', '31-2024-QH15')]
    outputs = iter([
        'Invalid ungrounded output',
        '1. Quy định năm 2013: Cũ. [Nguồn 1]\n2. Quy định hiện hành: Mới. [Nguồn 2]',
        '3. Điểm giống: Chung. [Nguồn 1] [Nguồn 2]\n4. Điểm khác/thay đổi: Khác. [Nguồn 1] [Nguồn 2]',
    ])
    adapter = RAGAdapter(Retriever(hits), hits, Tokenizer(), lambda _: next(outputs))
    assert len(adapter('So sánh năm 2013 và 2024')['citations']) == 2


def test_notebook_is_thin_and_valid_python():
    import ast
    import json
    from pathlib import Path
    notebook = json.loads((Path(__file__).parents[1] / '09_audio_interaction.ipynb').read_text(encoding='utf-8'))
    assert notebook['nbformat'] == 4
    for cell in notebook['cells']:
        if cell['cell_type'] != 'code':
            continue
        source = ''.join(cell['source'])
        if source.startswith(('%', '!')):
            continue
        tree = ast.parse(source)
        assert not any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) for node in ast.walk(tree))
