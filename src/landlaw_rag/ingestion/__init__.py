"""Đọc và chuẩn hóa văn bản pháp luật từ DOCX."""

from .preprocess_docx import clean_document, process_directory

__all__ = ["clean_document", "process_directory"]
