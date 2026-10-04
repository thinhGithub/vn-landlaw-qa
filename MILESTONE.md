# Milestones — Hệ thống Hybrid RAG pháp luật đất đai

Tài liệu này theo dõi lộ trình phát triển hệ thống hỏi đáp và đối chiếu pháp
luật đất đai Việt Nam. Phạm vi hiện tại tập trung vào Hybrid RAG, chưa bao gồm
GraphRAG hoặc Multi-Agent.

## Tổng quan

| Milestone | Nội dung | Sản phẩm đầu ra | Trạng thái |
|---|---|---|---|
| M1 | Chuẩn hóa dữ liệu luật | Bộ dữ liệu gốc sạch | Hoàn thành |
| M2 | Legal Parsing & Chunking | `chunks.json` có cấu trúc | Hoàn thành |
| M3 | BM25 Retrieval Baseline | Keyword retrieval hoạt động | Hoàn thành |
| M4 | Vector Retrieval | Semantic search hoạt động | Hoàn thành |
| M5 | Hybrid Retrieval | Retriever hoàn chỉnh | Hoàn thành |
| M6 | Local LLM RAG | Hỏi đáp dựa trên nguồn luật | Hoàn thành |
| M7 | Citation & Legal Comparison | QA + citation + comparison | Chưa bắt đầu |
| M8 | Evaluation | Bảng đánh giá hệ thống | Chưa bắt đầu |
| M9 | Web Demo | Demo hoàn chỉnh | Chưa bắt đầu |
| M10 | Hoàn thiện báo cáo | Báo cáo + kết quả thực nghiệm | Chưa bắt đầu |

---

## M1. Chuẩn hóa dữ liệu luật

### Mục tiêu

Đưa bốn văn bản DOCX vào project, kiểm tra nội dung và loại bỏ các phần thừa
nếu có mà không làm thay đổi nội dung pháp lý.

### Đầu vào

- Bốn file DOCX gốc trong `data/raw_doc/`:
  - Luật số 45/2013/QH13.
  - Luật số 31/2024/QH15.
  - Luật số 43/2024/QH15.
  - Nghị quyết số 254/2025/QH15.
- Cấu hình đường dẫn trong `configs/paths.yaml`.
- Thư viện `python-docx` để đọc nội dung DOCX mà không chỉnh sửa file gốc.

### Công việc

- [x] Kiểm tra đủ bốn file trong `data/raw_doc/`.
- [x] Kiểm tra file có thể mở và đọc đầy đủ nội dung.
- [x] Đối chiếu số hiệu, tên văn bản và phạm vi nội dung.
- [x] Phát hiện header, footer, số trang hoặc phần lặp không cần thiết.
- [x] Chuẩn hóa Unicode, khoảng trắng và ký tự đặc biệt.
- [x] Không sửa nội dung pháp lý của văn bản gốc.
- [x] Lưu dữ liệu đã làm sạch vào `data/processed/`.
- [x] Ghi log các thay đổi để có thể kiểm tra và tái lập.

### Tiêu chí hoàn thành

- Có đủ bốn văn bản gốc và phiên bản đã làm sạch.
- Nội dung điều, khoản, điểm không bị mất hoặc thay đổi.
- Các phần thừa đã được loại bỏ có ghi nhận rõ ràng.
- Pipeline làm sạch có thể chạy lại trên Google Colab.

### Đầu ra

**Bộ dữ liệu gốc sạch.**

---

## M2. Legal Parsing & Chunking

### Mục tiêu

Nhận diện cấu trúc `Chương → Mục → Điều → Khoản → Điểm`, thực hiện adaptive
chunking và gắn metadata phục vụ truy xuất và trích dẫn.

### Đầu vào

- `data/processed/manifest.json` do M1 tạo, chứa danh sách văn bản và đường dẫn
  đến file đã làm sạch.
- Bốn file văn bản UTF-8 `data/processed/*.txt` do M1 tạo.
- Các file `*.stats.json` của M1 để đối chiếu thống kê khi cần.
- Cấu hình chunking trong `configs/pipeline.yaml`.

### Công việc

- [x] Xây parser cho cấu trúc văn bản pháp luật Việt Nam.
- [x] Nhận diện Chương, Mục, Điều, Khoản và Điểm.
- [x] Xử lý các điều không có Mục hoặc Khoản.
- [x] Xử lý nội dung tiếp nối qua nhiều đoạn DOCX.
- [x] Thiết kế adaptive chunking theo cấu trúc pháp lý và độ dài văn bản.
- [x] Bảo toàn ngữ cảnh Điều khi chunk ở cấp Khoản hoặc Điểm.
- [x] Gắn metadata: văn bản, số hiệu, chương, mục, điều, khoản, điểm và nguồn.
- [x] Kiểm tra cấu trúc và độ bao phủ nội dung của chunk cho mỗi văn bản.

### Tiêu chí hoàn thành

- Parser nhận diện đúng cấu trúc trên tập kiểm tra đại diện.
- Mỗi chunk truy ngược được về văn bản và đơn vị pháp lý gốc.
- Không tạo chunk cắt ngang làm sai nghĩa Điều/Khoản/Điểm.
- File đầu ra có schema nhất quán và được kiểm tra hợp lệ.

### Đầu ra

**`chunks.json` có cấu trúc.**

Ngoài ra còn có `structured_documents.json` và `parsing_report.json`.

---

## M3. BM25 Retrieval Baseline

### Mục tiêu

Xây dựng baseline tìm kiếm từ khóa trên các chunks pháp luật.

### Đầu vào

- `data/processed/chunks.json` từ M2, bao gồm nội dung chunk và metadata pháp lý.
- `data/processed/parsing_report.json` để xác nhận dữ liệu đầu vào đã qua
  validation.
- Cấu hình BM25 như tokenizer, tham số `k1`, `b` và số lượng `top_k`.
- Danh sách truy vấn thử nghiệm theo từ khóa, số hiệu văn bản, Điều và Khoản.

### Công việc

- [x] Tiền xử lý văn bản tiếng Việt cho BM25.
- [x] Xây và lưu BM25 index.
- [x] Cài đặt truy vấn Top-k.
- [x] Thử truy vấn theo từ khóa pháp lý.
- [x] Thử truy vấn trực tiếp theo Điều/Khoản/số hiệu văn bản.
- [x] Hiển thị score và metadata của kết quả.

### Tiêu chí hoàn thành

- Truy vấn từ khóa trả về các chunks phù hợp.
- Truy vấn có Điều/Khoản ưu tiên đúng đơn vị pháp lý.
- Index có thể lưu trên Drive và tải lại mà không cần xây lại.

### Đầu ra

**Keyword retrieval hoạt động.**

---

## M4. Vector Retrieval

### Mục tiêu

Tạo embedding cho các chunks và xây FAISS index để tìm kiếm theo ngữ nghĩa.

### Đầu vào

- `data/processed/chunks.json` từ M2.
- Embedding model tiếng Việt hoặc multilingual tải từ nguồn miễn phí.
- Cấu hình model, batch size, độ dài đầu vào, metric và `top_k`.
- Môi trường Google Colab T4 và thư mục Google Drive để lưu embedding/index.

### Công việc

- [x] Chọn embedding model tiếng Việt hoặc multilingual phù hợp.
- [x] Benchmark tốc độ và bộ nhớ trên Colab T4.
- [x] Cài đặt sinh embedding theo batch.
- [x] Cài đặt chuẩn hóa vector theo cosine similarity.
- [x] Cài đặt xây và lưu FAISS index.
- [x] Cài đặt ánh xạ FAISS ID với chunk ID và metadata.
- [x] Thử các truy vấn diễn đạt khác với từ ngữ trong luật.

### Tiêu chí hoàn thành

- Semantic search trả về nội dung đúng chủ đề.
- FAISS index và metadata tải lại chính xác.
- Quá trình embedding chạy được trong giới hạn Colab T4.

### Đầu ra

**Semantic search hoạt động.**

---

## M5. Hybrid Retrieval

### Mục tiêu

Kết hợp kết quả BM25 và Vector Retrieval, thực hiện fusion/reranking và trả về
Top-k context tốt nhất.

### Đầu vào

- BM25 index và interface keyword retrieval từ M3.
- FAISS index, embedding model và interface semantic retrieval từ M4.
- `chunks.json` cùng ánh xạ `chunk_id`/metadata tương ứng với hai index.
- Cấu hình fusion, trọng số, reranker và các mức `top_k`.
- Tập truy vấn có relevance label để so sánh BM25, Vector và Hybrid.

### Công việc

- [x] Chuẩn hóa interface chung cho BM25 và Vector Retriever.
- [x] Kết hợp hai danh sách kết quả bằng Reciprocal Rank Fusion (RRF).
- [x] Khử chunk trùng theo `chunk_id` và giữ score/rank theo từng retriever.
- [x] Ưu tiên phiên bản luật theo năm, số hiệu văn bản và ý định query.
- [x] Giữ evidence của cả hai phiên bản đối với query so sánh.
- [x] Cấu hình Top-N cho từng retriever và Top-k cuối sau fusion.
- [x] So sánh kết quả BM25, Vector và Hybrid trên các truy vấn mẫu.

### Tiêu chí hoàn thành

- Một interface nhận câu hỏi và trả về Top-k chunks kèm score, nguồn.
- Hybrid Retrieval tốt hơn hoặc ổn định hơn từng retriever đơn lẻ trên tập test.
- Kết quả có thể truy vết score qua từng giai đoạn.

### Đầu ra

**Retriever hoàn chỉnh.**

---

## M6. Local LLM RAG

### Mục tiêu

Load mô hình Qwen 7B/8B lượng tử hóa 4-bit trên Colab T4 và xây prompt từ
Top-k context để trả lời dựa trên nguồn luật.

### Đầu vào

- Hybrid Retriever hoàn chỉnh từ M5.
- Top-k chunks kèm nội dung, score và metadata pháp lý.
- Checkpoint Qwen 7B/8B miễn phí và cấu hình quantization 4-bit.
- Prompt template, giới hạn context, tham số generation và quy tắc từ chối khi
  evidence không đủ.
- Môi trường Google Colab T4 và Google Drive để lưu model cache/cấu hình.

### Công việc

- [x] Chọn `Qwen/Qwen2.5-7B-Instruct` làm checkpoint local LLM.
- [x] Load model bằng quantization NF4 4-bit trên Colab T4.
- [x] Theo dõi VRAM, token và thời gian retrieval/generation/toàn pipeline.
- [x] Xây context có cấu trúc từ kết quả Hybrid Retrieval.
- [x] Cô lập phiên bản luật: hiện hành, Luật 2013 và chế độ so sánh.
- [x] Mở rộng các Khoản/Điểm cùng Điều khi nhiều hit cùng trỏ đến Điều đó.
- [x] Khử chunk trùng, giữ thứ tự pháp lý và giới hạn expansion theo token budget.
- [x] Thiết kế grounded prompt chỉ dùng evidence trực tiếp liên quan đến câu hỏi.
- [x] Không trộn chủ thể, hành vi, đối tượng hoặc trường hợp pháp lý khác.
- [x] Cấm tự bổ sung ví dụ, điều kiện, suy luận và căn cứ không có trong evidence.
- [x] Từ chối bằng câu `Chưa đủ căn cứ trong dữ liệu truy xuất.` khi evidence thiếu.
- [x] Kiểm soát độ dài context/output và sinh xác định với `do_sample=False`.
- [x] Kiểm thử query hiện hành và query Luật Đất đai 2013.

### Tiêu chí hoàn thành

- Model chạy ổn định trên Google Colab T4.
- Câu trả lời sử dụng thông tin trong Top-k context.
- Hạn chế phát sinh thông tin không có trong nguồn truy xuất.
- Không trộn Luật 2013 vào câu hỏi hiện hành hoặc ngược lại.
- Context expansion chỉ bổ sung chunk cùng văn bản và cùng Điều trong token budget.

### Đầu ra

**Hỏi đáp dựa trên nguồn luật.**

Artifacts chính:

- `06_local_llm_rag.ipynb`: notebook end-to-end trên Colab T4.
- `src/landlaw_rag/generation/rag.py`: dựng context, version isolation,
  context expansion và grounded prompt.
- `tests/test_rag_generation.py`: unit test cho prompt và kiểm soát evidence.

Citation pháp lý chuẩn hóa từ metadata vẫn thuộc phạm vi M7; nhãn `[Nguồn n]`
trong M6 chỉ dùng để phân biệt các đoạn context nội bộ.

---

## M7. Citation & Legal Comparison

### Mục tiêu

Sinh trích dẫn theo cấu trúc pháp lý đầy đủ
`Văn bản – Chương – Mục – Điều – Khoản – Điểm` và hỗ trợ đối chiếu Luật Đất
đai 2013 với Luật Đất đai 2024. Thành phần không tồn tại trong văn bản hoặc
không có trong metadata được lược bỏ khi hiển thị, không tự suy đoán.

### Đầu vào

- Pipeline Local LLM RAG từ M6.
- Top-k context và metadata `document_title`, `chapter`, `section`, `article`,
  `article_title`, `clause`, `point` từ `chunks.json`.
- Kết quả retrieval được lọc theo từng văn bản khi chạy chế độ đối chiếu.
- Câu hỏi người dùng và tín hiệu/chế độ yêu cầu đối chiếu 2013–2024.
- Quy tắc định dạng và validation citation.

### Công việc

- [ ] Tạo citation từ metadata thay vì chỉ dựa vào nội dung LLM sinh ra.
- [ ] Kiểm tra citation tồn tại trong context truy xuất.
- [ ] Chuẩn hóa cách hiển thị tên/số hiệu văn bản, Chương, Mục, Điều, Khoản và
  Điểm; chỉ hiển thị các cấp có trong metadata.
- [ ] Phân loại yêu cầu hỏi đáp thông thường và yêu cầu đối chiếu.
- [ ] Truy xuất evidence riêng cho văn bản năm 2013 và năm 2024.
- [ ] Sinh bảng hoặc nội dung đối chiếu theo cùng chủ đề pháp lý.
- [ ] Nêu rõ điểm giống, khác và nguồn của từng nhận định.
- [ ] Xử lý trường hợp không tìm thấy quy định tương ứng.

### Tiêu chí hoàn thành

- Mỗi nhận định pháp lý quan trọng có citation hợp lệ.
- Citation dẫn đúng văn bản, Chương, Mục, Điều, Khoản và Điểm khi có.
- Chế độ comparison không trộn lẫn quy định giữa hai phiên bản luật.

### Đầu ra

**QA + citation + comparison.**

---

## M8. Evaluation

### Mục tiêu

Tạo bộ câu hỏi kiểm thử và đánh giá retrieval, trích dẫn, câu trả lời và hiệu
năng hệ thống.

### Đầu vào

- Các pipeline BM25, Vector và Hybrid Retrieval từ M3–M5.
- Pipeline QA, citation và legal comparison từ M6–M7.
- Bộ câu hỏi đánh giá kèm đáp án, evidence, văn bản và Điều/Khoản chuẩn.
- Cấu hình thí nghiệm cố định: model, index, `top_k`, seed và phần cứng.
- Log score, citation, câu trả lời và latency của từng lần chạy.

### Công việc

- [ ] Xây bộ câu hỏi theo nhiều chủ đề và độ khó.
- [ ] Gắn đáp án chuẩn và evidence chuẩn cho từng câu hỏi.
- [ ] Có nhóm câu hỏi từ khóa, ngữ nghĩa, Điều/Khoản và đối chiếu.
- [ ] Đo Recall@K cho BM25, Vector và Hybrid Retrieval.
- [ ] Đo citation accuracy.
- [ ] Đánh giá correctness/faithfulness của câu trả lời.
- [ ] Đo retrieval latency, generation latency và total latency.
- [ ] Ghi lại cấu hình model/index của mỗi lần đánh giá.

### Tiêu chí hoàn thành

- Bộ test có định dạng và hướng dẫn đánh giá rõ ràng.
- Kết quả có thể tái lập từ cùng cấu hình.
- Có bảng so sánh giữa các cấu hình hệ thống.

### Đầu ra

**Bảng đánh giá hệ thống.**

---

## M9. Web Demo

### Mục tiêu

Xây dựng Gradio UI cho phép nhập câu hỏi, xem câu trả lời và nguồn pháp luật.

### Đầu vào

- Pipeline hoàn chỉnh từ câu hỏi đến câu trả lời của M5–M7.
- BM25/FAISS indexes, embedding model và local LLM đã kiểm tra.
- Cấu hình đường dẫn Google Drive và tham số inference.
- Thiết kế giao diện cho chế độ hỏi đáp, đối chiếu và hiển thị evidence.
- Một số câu hỏi mẫu và kết quả đánh giá từ M8 để demo.

### Công việc

- [ ] Tạo giao diện nhập câu hỏi.
- [ ] Thêm chế độ hỏi đáp và đối chiếu.
- [ ] Hiển thị câu trả lời có citation.
- [ ] Hiển thị Top-k nguồn, score và nội dung liên quan.
- [ ] Hiển thị trạng thái xử lý và thời gian phản hồi.
- [ ] Xử lý lỗi khi model/index chưa được tải.
- [ ] Chuẩn bị notebook chạy demo trên Colab.

### Tiêu chí hoàn thành

- Người dùng có thể thực hiện luồng hỏi đáp từ đầu đến cuối.
- Citation và evidence dễ kiểm tra trên giao diện.
- Demo chạy được trên Google Colab T4.

### Đầu ra

**Demo hoàn chỉnh.**

---

## M10. Hoàn thiện báo cáo

### Mục tiêu

Hoàn thiện tài liệu kiến trúc, pipeline, thực nghiệm và phân tích kết quả.

### Đầu vào

- Mô tả dữ liệu, source code, cấu hình và artifacts từ M1–M9.
- Sơ đồ kiến trúc và pipeline của hệ thống.
- Bảng thống kê parsing/chunking và bộ ảnh chụp Web Demo.
- Kết quả đánh giá, latency và ablation BM25 vs Vector vs Hybrid từ M8.
- Log thí nghiệm, bảng biểu, phân tích lỗi và các giới hạn đã ghi nhận.

### Công việc

- [ ] Mô tả bài toán và phạm vi nghiên cứu.
- [ ] Trình bày dữ liệu và quá trình chuẩn hóa.
- [ ] Trình bày kiến trúc và pipeline hệ thống.
- [ ] Giải thích lựa chọn chunking, embedding, fusion và reranking.
- [ ] Thực hiện ablation: BM25 vs Vector vs Hybrid.
- [ ] Báo cáo chất lượng retrieval, citation, answer và latency.
- [ ] Phân tích lỗi và giới hạn của hệ thống.
- [ ] Nêu hướng phát triển sau giai đoạn Hybrid RAG.

### Tiêu chí hoàn thành

- Báo cáo có đầy đủ kiến trúc, phương pháp, thiết lập và kết quả thực nghiệm.
- Các bảng/biểu đồ có thể truy ngược về dữ liệu đánh giá.
- Kết luận phản ánh đúng kết quả, không vượt quá bằng chứng thực nghiệm.

### Đầu ra

**Báo cáo và kết quả thực nghiệm.**

---

## Quy ước trạng thái

- `Chưa bắt đầu`: chưa thực hiện công việc chính.
- `Đang thực hiện`: đã bắt đầu nhưng chưa đạt đủ tiêu chí hoàn thành.
- `Hoàn thành`: đạt tiêu chí hoàn thành và đã kiểm tra đầu ra.
- `Tạm dừng`: chưa thể tiếp tục do phụ thuộc hoặc lỗi cần xử lý.
