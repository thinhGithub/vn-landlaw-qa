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

## Luồng xử lý dự kiến

```text
DOCX -> parse -> normalize -> adaptive chunking -> BM25 + FAISS
     -> hybrid retrieval -> fusion/reranking -> prompt -> local LLM
```
