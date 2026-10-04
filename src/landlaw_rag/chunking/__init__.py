"""Chia đoạn thích ứng theo Chương/Mục/Điều/Khoản/Điểm."""

from .legal_parser import chunk_document, parse_document, process_manifest

__all__ = ["chunk_document", "parse_document", "process_manifest"]
