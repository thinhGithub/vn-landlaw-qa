# M9 — Vietnamese Voice Interaction

## 1. Mục tiêu

M9 bổ sung lớp giao tiếp giọng nói tiếng Việt cho hệ thống Hybrid RAG pháp luật đất
đai. Voice là lớp vào/ra tùy chọn; toàn bộ retrieval, generation, comparison và
citation validation của M1–M8 tiếp tục là nguồn xử lý chính.

```text
Microphone / audio file
        ↓
Speech-to-Text (STT)
        ↓
Chuẩn hóa + transcript có thể chỉnh sửa
        ↓
QA / Legal Comparison / Citation Validation
        ↓
Câu trả lời văn bản + evidence
        ↓
Text-to-Speech (TTS)
```

## 2. Nguyên tắc thiết kế

- Không thay đổi câu hỏi sau khi người dùng đã xác nhận transcript.
- Không để STT/TTS can thiệp vào citation hoặc evidence mapping.
- Luôn hiển thị transcript trước khi gửi vào RAG.
- Luôn giữ chế độ nhập và nhận kết quả bằng văn bản làm fallback.
- Chỉ đọc phần trả lời chính; citation chi tiết, metadata và `chunk_id` hiển thị trên UI.
- Ghi thời gian riêng cho STT, retrieval, generation, citation, TTS và toàn pipeline.

## 3. Phạm vi

### Trong phạm vi

- Thu âm từ microphone hoặc nhận file audio phổ biến.
- Nhận dạng câu hỏi tiếng Việt.
- Chuẩn hóa các mẫu pháp lý thường gặp.
- Cho phép sửa transcript trước khi thực thi.
- Dùng transcript cho cả QA thông thường và Legal Comparison.
- Sinh audio tiếng Việt từ câu trả lời cuối.
- Xử lý timeout, audio rỗng, định dạng không hỗ trợ và lỗi model/dịch vụ.

### Ngoài phạm vi M9

- Hội thoại giọng nói streaming thời gian thực.
- Nhận dạng danh tính người nói hoặc tách nhiều người nói.
- Fine-tune mô hình STT/TTS riêng.
- Đọc nguyên văn toàn bộ evidence hoặc văn bản luật dài.
- Đánh giá định lượng quy mô lớn; nội dung này thuộc M10.

## 4. Thành phần đề xuất

### Speech-to-Text

Ưu tiên một adapter chung để có thể thay backend mà không sửa pipeline:

```python
class SpeechToText:
    def transcribe(self, audio_path: str) -> dict:
        # {"text": str, "language": str, "latency_ms": float}
        ...
```

Backend ban đầu có thể dùng `faster-whisper` với model `small` hoặc `medium`. Model
cần được cấu hình thay vì hard-code để cân bằng độ chính xác, latency và VRAM.

### Transcript normalization

Lớp chuẩn hóa chỉ sửa các mẫu có độ chắc chắn cao, chẳng hạn:

- “điều bốn mươi lăm” → “Điều 45”;
- “khoản một, điểm a” → “Khoản 1 Điểm a”;
- “luật đất đai năm hai nghìn không trăm hai mươi bốn” → “Luật Đất đai 2024”;
- chuẩn hóa khoảng trắng và dấu câu.

Không tự suy đoán số hiệu văn bản khi transcript không đủ rõ. Giá trị gốc và giá trị
đã chuẩn hóa cần được giữ để kiểm tra.

### Text-to-Speech

TTS nhận phiên bản câu trả lời dành cho giọng đọc:

- bỏ marker kỹ thuật và `chunk_id`;
- không đọc danh sách citation dài;
- giữ nguyên nội dung pháp lý của câu trả lời;
- có thể kết thúc bằng câu “Nguồn pháp lý được hiển thị trên màn hình.”

```python
class TextToSpeech:
    def synthesize(self, text: str, output_path: str) -> dict:
        # {"audio_path": str, "latency_ms": float}
        ...
```

## 5. Luồng xử lý

1. Người dùng thu âm hoặc tải file.
2. Hệ thống kiểm tra định dạng, dung lượng và thời lượng.
3. STT tạo transcript thô.
4. Normalizer tạo transcript đề xuất.
5. Người dùng kiểm tra/sửa và xác nhận.
6. Transcript đã xác nhận đi vào router QA/Comparison.
7. Pipeline hiện tại tạo answer, citation và evidence.
8. TTS tạo audio từ phần trả lời chính.
9. UI trả transcript, answer, citation, evidence, audio và latency.

Nếu STT lỗi, người dùng có thể nhập câu hỏi. Nếu TTS lỗi, câu trả lời văn bản và
citation vẫn phải được trả về đầy đủ.

## 6. Cấu trúc dữ liệu gợi ý

```python
@dataclass
class AudioInteractionResult:
    raw_transcript: str
    normalized_transcript: str
    answer: str
    citations: list
    evidence: list
    audio_path: str | None
    stt_latency_ms: float
    rag_latency_ms: float
    tts_latency_ms: float
    total_latency_ms: float
    warnings: list[str]
```

## 7. Xử lý tài nguyên trên Colab T4

- Load Qwen 4-bit trước và theo dõi VRAM còn lại.
- Chọn kích thước Whisper bằng cấu hình; có thể chạy STT trên CPU khi GPU thiếu bộ nhớ.
- Không giữ nhiều bản model STT trong bộ nhớ.
- TTS nên ưu tiên backend nhẹ; nếu dùng dịch vụ mạng phải có timeout và fallback.
- Cache model giữa các lượt hỏi, nhưng không cache audio chứa dữ liệu người dùng lâu dài.

## 8. Kiểm thử M9

### Unit test

- Chuẩn hóa năm, Điều, Khoản, Điểm và số hiệu phổ biến.
- Không sửa transcript khi quy tắc không đủ chắc chắn.
- Tạo văn bản TTS mà không đọc marker/citation kỹ thuật.
- Tính latency và cảnh báo đúng schema.

### Integration test

- Audio → transcript → QA → citation → audio.
- Audio comparison → tách evidence 2013/hiện hành → citation hai phía → audio.
- STT lỗi nhưng nhập văn bản vẫn hoạt động.
- TTS lỗi nhưng answer/citation/evidence vẫn được trả về.
- Không có citation nào được tạo từ transcript hoặc output TTS.

### Tập audio smoke test

Nên có tối thiểu 10–20 đoạn, bao gồm:

- câu hỏi ngắn và dài;
- “Điều”, “Khoản”, “Điểm”;
- năm 2013 và 2024;
- số hiệu `45/2013/QH13`, `31/2024/QH15`;
- câu hỏi so sánh;
- tiếng nền nhẹ hoặc tốc độ nói khác nhau.

Đánh giá chính thức về WER, latency và ảnh hưởng đến retrieval thuộc M10.

## 9. Tiêu chí nghiệm thu

- Transcript tiếng Việt được tạo và có thể chỉnh sửa trước khi gửi.
- QA và Legal Comparison hoạt động từ transcript đã xác nhận.
- Citation vẫn deterministic từ retrieved evidence.
- Sinh và phát được audio cho câu trả lời chính.
- Text fallback hoạt động độc lập khi voice backend lỗi.
- Có log latency theo từng giai đoạn.
- Unit/integration test của M9 chạy thành công.
- Có notebook hoặc script chạy được trên Google Colab T4.

## 10. Đầu ra dự kiến

- Module STT và TTS có interface độc lập backend.
- Module chuẩn hóa transcript pháp lý.
- Test cho normalization và voice integration.
- Notebook/script minh họa pipeline voice end-to-end.
- Một tập audio smoke test nhỏ kèm transcript tham chiếu.

