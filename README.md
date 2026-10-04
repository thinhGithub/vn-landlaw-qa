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

```bash
python scripts/preprocess_m1.py
```

Mỗi DOCX tạo một file `.txt` sạch và một file `.stats.json` trong
`data/processed/`. File `manifest.json` tổng hợp thống kê và log các dòng bị
loại. Bước này chưa thực hiện parsing, chunking, embedding hoặc RAG.

## Luồng xử lý dự kiến

```text
DOCX -> parse -> normalize -> adaptive chunking -> BM25 + FAISS
     -> hybrid retrieval -> fusion/reranking -> prompt -> local LLM
```
