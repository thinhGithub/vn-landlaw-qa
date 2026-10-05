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
| M7 | Citation & Source Validation | QA + validated legal citations | Hoàn thành |
| M8 | Legal Comparison | Legal comparison with validated citations | Hoàn thành cơ bản |
| M9 | Evaluation | Evaluation results + ablation tables + system metrics | Chưa bắt đầu |
| M10 | Web Demo | End-to-end Web Demo | Chưa bắt đầu |

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

## M7. Citation & Source Validation

### Mục tiêu

Bổ sung citation pháp lý có cấu trúc cho câu trả lời của pipeline RAG.

Citation phải được sinh **deterministic từ metadata của retrieved evidence**, không để LLM tự tạo hoặc tự suy đoán citation.

Citation sử dụng cấu trúc ngắn gọn:

`Văn bản → Điều → Khoản → Điểm`

Chỉ hiển thị những cấp thực sự tồn tại trong metadata.

### Đầu vào

- Pipeline Local LLM RAG hoàn chỉnh từ M6.
- Retrieved context/evidence từ Hybrid Retriever.
- Metadata của từng chunk, bao gồm nếu có:
  - `document_title`
  - `document_id`
  - `chapter`
  - `section`
  - `article`
  - `article_title`
  - `clause`
  - `point`
  - `chunk_id`
- Câu trả lời generated từ Local LLM.
- Quy tắc format citation.

### Công việc
- [x] Xây citation formatter từ metadata.
- [x] Citation không được lấy từ text do LLM tự sinh.
- [x] Chuẩn hóa format citation:
  `Văn bản → Điều → Khoản → Điểm`.
- [x] Tự động bỏ qua các cấp metadata không tồn tại.
- [x] Liên kết citation với đúng evidence/chunk đã được đưa vào context.
- [x] Không cho phép citation tới chunk không xuất hiện trong evidence của câu hỏi.
- [x] Loại citation trùng lặp.
- [x] Giữ thứ tự citation ổn định và dễ kiểm tra.
- [x] Gắn inline marker cho từng claim và lưu mapping về `chunk_id` hỗ trợ.
- [x] Xử lý metadata thiếu hoặc malformed.
- [x] Thêm unit test cho citation formatter và source validation.
- [x] Kiểm thử trên câu hỏi luật hiện hành và câu hỏi Luật Đất đai 2013.

### Tiêu chí hoàn thành

- Mỗi citation được sinh trực tiếp từ metadata.
- Citation truy ngược được tới đúng `chunk_id` và văn bản gốc.
- Không xuất hiện Điều/Khoản/Điểm không tồn tại trong evidence.
- Không để LLM tự tạo nguồn.
- Các cấp metadata không tồn tại được bỏ qua thay vì suy đoán.
- Citation format nhất quán giữa các câu hỏi.
- Unit test cho citation/source validation chạy thành công.

### Đầu ra

**QA + validated legal citations.**

---

## M8. Legal Comparison

### Mục tiêu

Mở rộng hệ thống để hỗ trợ đối chiếu quy định giữa:

- Luật Đất đai 2013.
- Luật Đất đai 2024 và các văn bản thuộc phạm vi dữ liệu hiện hành.

Comparison phải dựa trên evidence được retrieve riêng cho từng phiên bản luật và sử dụng citation validation từ M7.

Không giả định rằng cùng một nội dung pháp lý sẽ nằm ở cùng số Điều giữa hai phiên bản.

### Đầu vào

- Pipeline RAG từ M6.
- Citation & Source Validation từ M7.
- Hybrid Retriever từ M5.
- Metadata về phiên bản/năm/số hiệu văn bản.
- Query của người dùng.
- Evidence tách riêng cho Luật 2013 và hệ thống luật hiện hành.

### Công việc

- [x] Xây rule-based intent detection để phân biệt:
  - QA thông thường.
  - Legal comparison.
- [x] Nhận diện các query có ý định như:
  - so sánh,
  - khác nhau,
  - thay đổi,
  - trước đây,
  - hiện nay,
  - 2013,
  - 2024.
- [x] Khi comparison, retrieve evidence của Luật 2013 riêng.
- [x] Retrieve evidence của Luật 2024/hiện hành riêng.
- [x] Không trộn evidence của hai phiên bản trước bước comparison.
- [x] Đối chiếu theo cùng chủ đề/nội dung pháp lý.
- [x] Không map Điều 2013 sang Điều 2024 chỉ dựa trên số Điều.
- [x] Xây structured comparison context cho LLM.
- [x] Prompt LLM sinh kết quả gồm:
  - Quy định năm 2013.
  - Quy định năm 2024/hiện hành.
  - Điểm giống.
  - Điểm khác hoặc thay đổi.
  - Citation tương ứng cho từng phía.
- [x] Mỗi nhận định comparison phải truy ngược được về evidence.
- [x] Nếu một phía không tìm được evidence phù hợp, phải nêu rõ:
  `Chưa tìm thấy quy định tương ứng trong dữ liệu truy xuất.`
- [x] Không cho phép LLM tự suy đoán sự thay đổi pháp luật khi evidence không đủ.
- [x] Viết test cho comparison routing, version isolation và evidence mapping.

### Tiêu chí hoàn thành

- Hệ thống nhận diện được QA thông thường và comparison query.
- Evidence của Luật 2013 và 2024 được retrieve và quản lý riêng biệt.
- Không trộn nguồn giữa hai phiên bản.
- Mỗi nhận định so sánh có citation tương ứng.
- Citation sử dụng cơ chế validation từ M7.
- Không giả định số Điều giữa hai luật phải tương ứng.
- Hệ thống xử lý rõ trường hợp thiếu evidence một phía.
- Comparison có thể truy vết từ output về retrieved chunks.

### Đầu ra

**Legal comparison with validated citations.**

Trạng thái hiện tại: **Hoàn thành cơ bản**. Luồng comparison, cô lập phiên bản,
structured prompt, evidence mapping và citation validation đã được triển khai và có
unit test. Việc đánh giá định lượng trên tập câu hỏi lớn hơn được thực hiện trong M9.

---

## M9. Evaluation

### Mục tiêu

Đánh giá định lượng và định tính toàn bộ hệ thống từ retrieval đến generation, citation và legal comparison.

Đồng thời thực hiện ablation giữa:

- BM25 Retrieval.
- Vector Retrieval.
- Hybrid Retrieval.

### Đầu vào

- BM25 Retriever từ M3.
- Vector Retriever từ M4.
- Hybrid Retriever từ M5.
- Local LLM RAG từ M6.
- Citation pipeline từ M7.
- Legal Comparison từ M8.
- Bộ câu hỏi evaluation có ground truth/evidence chuẩn.
- Cấu hình cố định của model/index/retrieval.

### Công việc

- [ ] Xây evaluation dataset theo nhiều nhóm câu hỏi:
  - keyword query,
  - semantic query,
  - Điều/Khoản cụ thể,
  - QA luật hiện hành,
  - QA Luật Đất đai 2013,
  - comparison 2013–2024,
  - insufficient-evidence query.
- [ ] Gắn relevant chunks/evidence chuẩn cho từng câu hỏi.
- [ ] Đo Retrieval Recall@K.
- [ ] Có thể bổ sung Precision@K hoặc MRR nếu phù hợp.
- [ ] So sánh:
  - BM25,
  - Vector,
  - Hybrid.
- [ ] Đo citation accuracy/source accuracy.
- [ ] Kiểm tra citation hallucination rate nếu cần.
- [ ] Đánh giá answer correctness.
- [ ] Đánh giá faithfulness/groundedness.
- [ ] Đánh giá comparison correctness.
- [ ] Kiểm tra version isolation giữa 2013 và 2024.
- [ ] Đo:
  - retrieval latency,
  - generation latency,
  - total latency.
- [ ] Ghi cấu hình của từng experiment:
  - embedding model,
  - LLM,
  - quantization,
  - top_k,
  - fusion parameters,
  - hardware,
  - seed nếu có.
- [ ] Sinh bảng kết quả phục vụ báo cáo.

### Tiêu chí hoàn thành

- Có evaluation dataset rõ ràng và có thể tái lập.
- Có metric retrieval cho BM25, Vector và Hybrid.
- Có metric citation.
- Có đánh giá answer correctness/faithfulness.
- Có đánh giá legal comparison.
- Có số liệu latency.
- Có bảng so sánh/ablation giữa các cấu hình retrieval.
- Kết quả có thể chạy lại với cùng cấu hình.

### Đầu ra

**Evaluation results + ablation tables + system metrics.**

---

## M10. Web Demo

### Mục tiêu

Xây dựng giao diện demo end-to-end cho toàn bộ hệ thống Hybrid RAG pháp luật đất đai.

Sử dụng Gradio và chạy được trên Google Colab T4.

### Đầu vào

- Hybrid Retrieval từ M5.
- Local LLM RAG từ M6.
- Citation & Source Validation từ M7.
- Legal Comparison từ M8.
- Kết quả/configuration tốt nhất từ M9.
- BM25/FAISS index.
- Embedding model.
- Local Qwen model.
- Google Drive paths/config.

### Công việc

- [ ] Tạo Gradio UI.
- [ ] Có ô nhập câu hỏi.
- [ ] Có chế độ:
  - QA thông thường.
  - Legal Comparison.
- [ ] Có thể tự động detect comparison nếu pipeline đã hỗ trợ.
- [ ] Hiển thị câu trả lời.
- [ ] Hiển thị validated citations.
- [ ] Hiển thị danh sách evidence/source.
- [ ] Cho phép xem metadata:
  - văn bản,
  - Điều,
  - Khoản,
  - Điểm,
  - chunk_id.
- [ ] Có thể hiển thị retrieval score/rank nếu cần cho demo/debug.
- [ ] Với comparison, hiển thị rõ hai phía:
  - Luật 2013.
  - Luật 2024/hiện hành.
- [ ] Hiển thị phần giống/khác hoặc thay đổi.
- [ ] Hiển thị retrieval latency, generation latency và total latency.
- [ ] Xử lý lỗi khi index/model chưa được load.
- [ ] Có một số sample questions.
- [ ] Tạo notebook/script chạy demo trên Google Colab T4.

### Tiêu chí hoàn thành

- Người dùng có thể thực hiện end-to-end:
  `Question → Retrieval → Generation → Citation → Result`.
- QA thông thường hoạt động.
- Legal comparison hoạt động.
- Citation và evidence dễ kiểm tra.
- Không trộn phiên bản luật trong UI.
- Demo chạy ổn định trên Google Colab T4.
- Có thể sử dụng các câu hỏi evaluation từ M9 để demo.

### Đầu ra

**End-to-end Web Demo.**

---

## Quy ước trạng thái

- `Chưa bắt đầu`: chưa thực hiện công việc chính.
- `Đang thực hiện`: đã bắt đầu nhưng chưa đạt đủ tiêu chí hoàn thành.
- `Hoàn thành`: đạt tiêu chí hoàn thành và đã kiểm tra đầu ra.
- `Tạm dừng`: chưa thể tiếp tục do phụ thuộc hoặc lỗi cần xử lý.
