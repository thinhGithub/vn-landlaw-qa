# Dependency groups

Các dependency được chia theo giai đoạn để tránh cài package GPU/LLM khi chỉ
làm preprocessing hoặc retrieval.

| File | Phạm vi |
|---|---|
| `base.txt` | M1–M2: đọc DOCX, preprocessing, parsing và chunking |
| `retrieval.txt` | M3–M5: BM25, embedding, FAISS và Hybrid Retrieval |
| `generation.txt` | M6–M7: local LLM, Transformers và quantization 4-bit |
| `dev.txt` | Kiểm thử local bằng pytest |

## Cài đặt đề xuất

Chỉ chạy M1–M2 và test:

```powershell
python -m pip install -r requirements/dev.txt
```

Phát triển M3–M5:

```powershell
python -m pip install -r requirements/retrieval.txt
python -m pip install -r requirements/dev.txt
```

Chạy toàn bộ project, bao gồm local LLM:

```powershell
python -m pip install -r requirements.txt
```

`generation.txt` nên được cài trên Google Colab T4. Phiên bản CUDA của PyTorch
cần được chọn theo runtime Colab tại thời điểm cài đặt; chưa khóa version cho
đến khi cấu hình M6 được chốt.
