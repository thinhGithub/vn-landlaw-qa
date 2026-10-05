# Hybrid RAG for Vietnamese Land Law

Hệ thống hỏi đáp và đối chiếu pháp luật đất đai Việt Nam sử dụng Hybrid RAG.

## Cài đặt venv

Tạo môi trường ảo

```bash
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
# Hoặc: .venv\Scripts\activate   # Windows
```

## Cấu trúc project

```text
.
|-- data/
|   |-- raw_doc/                # DOCX pháp luật gốc (không chỉnh sửa)
|   |-- interim/                # Kết quả parse/trung gian để kiểm tra
|   |-- processed/              # Chunks + metadata đã chuẩn hóa
|   `-- samples/                # Tập dữ liệu nhỏ phục vụ test/demo
|-- indexes/
|   |-- bm25/                   # BM25 index
|   |-- faiss/                  # FAISS vector index
|   `-- metadata/               # Ánh xạ index ID -> chunk/metadata
|-- configs/                    # Cấu hình theo môi trường/pipeline
|-- notebooks/                  # Notebook chạy theo từng giai đoạn trên Colab
|-- scripts/                    # Entry point cho các bước pipeline
|-- src/landlaw_rag/
|   |-- ingestion/              # Đọc DOCX, parse cấu trúc pháp luật
|   |-- chunking/               # Adaptive chunking
|   |-- indexing/               # Tạo BM25/FAISS index
|   |-- retrieval/              # Hybrid search, fusion, reranking
|   |-- generation/             # Prompt và local LLM
|   |-- comparison/             # Đối chiếu Luật 2013/2024
|   |-- evaluation/             # Đánh giá retrieval/answer/citation
|   `-- utils/                  # Tiện ích dùng chung
|-- tests/                      # Unit/integration tests
|-- artifacts/                  # Báo cáo, biểu đồ, kết quả đánh giá
`-- requirements.txt
```

Các thư mục `data/processed`, `indexes` và model cache nên đặt trên Google Drive
khi chạy Colab; đường dẫn được khai báo trong `configs/paths.yaml`.

## Chạy Milestone 1

Tạo môi trường local và cài dependency tối thiểu cho M1–M2:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements/dev.txt
```

```bash
python scripts/preprocess_m1.py
```

Mỗi DOCX tạo một file `.txt` sạch và một file `.stats.json` trong
`data/processed/`. File `manifest.json` tổng hợp thống kê và log các dòng bị
loại. Bước này chưa thực hiện parsing, chunking, embedding hoặc RAG.

## Chạy Milestone 2

```bash
python scripts/process_m2.py
```

Kết quả gồm `structured_documents.json`, `chunks.json` và
`parsing_report.json` trong `data/processed/`. Có thể điều chỉnh giới hạn gần
đúng của chunk bằng `--max-chars`, ví dụ `--max-chars 2800`. Bước này chưa tạo
embedding, BM25, FAISS hoặc retrieval.

## Chạy Milestone 3

Build BM25 index và chạy các truy vấn mẫu:

```powershell
python scripts\run_m3.py --rebuild
```

Những lần sau có thể load index đã lưu mà không build lại:

```powershell
python scripts\run_m3.py --query "Khoản 2 Điều 57 Luật 45/2013/QH13" --top-k 5
```

Index được lưu tại `indexes/bm25/bm25_index.json.gz`. Tham số BM25, metadata
boost và đường dẫn được cấu hình trong `configs/bm25.yaml`.

## Chạy Milestone 4 trên Colab T4

Notebook [colab_notebook_milestone4.ipynb](colab_notebook_milestone4.ipynb) chứa quy trình đầy đủ để
mount Drive, đồng bộ private repository, kiểm tra dữ liệu, chạy test, sinh
embedding và thử semantic search.

Chạy trực tiếp bằng CLI trên runtime có GPU:

```bash
python scripts/run_m4.py --rebuild --build-only --device cuda
python scripts/run_m4.py --device cuda --top-k 5
```

Artifacts được lưu trong `indexes/faiss/`:

- `faiss.index`: FAISS `IndexFlatIP`.
- `embeddings.npy`: vector đã L2-normalize.
- `vector_metadata.json`: ánh xạ `faiss_id` với chunk và metadata pháp lý.
- `embedding_manifest.json`: model, checksum, dimension và benchmark build.

Tham số model/batch/index nằm trong `configs/vector.yaml`. M4 dùng
`intfloat/multilingual-e5-base` với prefix `query:`/`passage:` và cosine
similarity. Hybrid fusion với BM25 chỉ được triển khai từ M5.

## Chạy Milestone 5 — Hybrid Retrieval

Notebook [05_hybrid_retrieval.ipynb](05_hybrid_retrieval.ipynb) tải lại BM25 và
FAISS index đã có, sau đó hợp nhất hai danh sách kết quả bằng Reciprocal Rank
Fusion (RRF). Kết quả được khử trùng theo `chunk_id`, giữ score của từng
retriever và ưu tiên phiên bản luật phù hợp với câu hỏi.

Các thành phần chính nằm trong `src/landlaw_rag/retrieval/`:

- `BM25Retriever` và `VectorRetriever` dùng chung interface `search()`.
- `HybridRetriever` lấy Top-N từ hai retriever và hợp nhất bằng RRF.
- Query không chỉ định năm ưu tiên Luật 31/2024/QH15 và văn bản sửa đổi, bổ
  sung; query nêu năm 2013 ưu tiên Luật 45/2013/QH13.
- Query so sánh cho phép giữ evidence của cả hai phiên bản.

## Chạy Milestone 6 — Local LLM RAG

Notebook [06_local_llm_rag.ipynb](06_local_llm_rag.ipynb) chạy pipeline:

```text
query -> Hybrid Retrieval -> version isolation -> context expansion
      -> grounded prompt -> Qwen2.5-7B-Instruct 4-bit -> answer
```

M6 sử dụng `Qwen/Qwen2.5-7B-Instruct`, quantization NF4 4-bit và được thiết kế
để chạy trên Google Colab T4. Cài dependency bằng:

```bash
python -m pip install -r requirements/generation.txt
```

Các cơ chế kiểm soát evidence:

- Chỉ trả lời từ evidence được truy xuất; không tự bổ sung ví dụ, điều kiện hay
  căn cứ pháp lý.
- Chỉ chọn evidence đúng chủ thể, hành vi, đối tượng và phạm vi câu hỏi.
- Tách biệt quy định hiện hành và Luật Đất đai 2013 theo ý định của query.
- Khi nhiều hit thuộc cùng một Điều, bổ sung các Khoản/Điểm cùng Điều trong giới
  hạn token; không mở rộng sang văn bản hoặc Điều khác.
- Context giữ cấu trúc `Văn bản → Chương/Mục → Điều → Khoản/Điểm → nội dung`.
- Nếu evidence không đủ, trả lời: `Chưa đủ căn cứ trong dữ liệu truy xuất.`
- Generation dùng `do_sample=False`; notebook ghi nhận token, latency và VRAM.

Sau khi thay đổi code trong `src/`, cần restart runtime hoặc reload module trong
Colab trước khi chạy lại notebook.

Chạy unit test cho prompt, version isolation và context expansion:

```powershell
$env:PYTHONPATH = "src"
python -m pytest tests\test_rag_generation.py -q
```

## Chạy Milestone 7 — Citation & Source Validation

M7 bổ sung lớp hậu xử lý độc lập, không thay đổi retrieval hoặc generation của
M1–M6. Citation được tạo deterministic từ metadata của các chunk thực sự có
trong context, theo dạng ngắn:

```text
[1] Luật Đất đai số 31/2024/QH15 → Điều 45 → Khoản 1 → Điểm a
```

API chính nằm trong `landlaw_rag.generation`:

- `format_citation(metadata)`: định dạng nguồn, không đưa nội dung hoặc tiêu đề
  Điều vào citation.
- `build_citations(evidence, cited_chunk_ids)`: kiểm tra nguồn thuộc evidence,
  khử trùng và giữ thứ tự retrieval ổn định.
- `cite_tagged_answer(...)`: validate nhãn `[Nguồn n]` do model chọn từ context,
  đổi thành marker inline và tạo mapping `claim → citation_id → chunk_id`.
- `cite_answer(...)`: API thủ công cho caller đã có sẵn `ClaimSupport`.

Prompt yêu cầu mỗi claim nằm trên một dòng và kết thúc bằng `[Nguồn n]`. Lớp M7
từ chối claim thiếu nguồn hoặc nhãn không thuộc context, dùng lại cùng marker cho
cùng nguồn và chỉ liệt kê mỗi căn cứ một lần. Chạy test bằng:

```powershell
$env:PYTHONPATH = "src"
python -m pytest tests\test_citation.py -q
```

## Luồng xử lý hiện tại

```text
DOCX -> parse -> normalize -> adaptive chunking -> BM25 + FAISS
     -> hybrid retrieval (RRF) -> version isolation -> context expansion
     -> grounded prompt -> local LLM -> validated citations
```

M1–M7 đã hoàn thành. M8 Legal Comparison đã hoàn thành cơ bản với routing,
cô lập evidence theo phiên bản, structured comparison prompt và validated citations;
M9 bổ sung giao tiếp giọng nói tiếng Việt. Đánh giá định lượng trên tập câu hỏi lớn
hơn thuộc phạm vi M10; Web Demo end-to-end thuộc M11.
