"""Dựng prompt, sinh câu trả lời và kiểm soát trích dẫn."""

from .rag import (
    INSUFFICIENT_EVIDENCE_MESSAGE,
    build_context,
    build_messages,
    detect_version_intent,
    expand_article_context,
    filter_results_by_version,
    format_source,
)

__all__ = [
    "INSUFFICIENT_EVIDENCE_MESSAGE",
    "format_source",
    "build_context",
    "build_messages",
    "detect_version_intent",
    "expand_article_context",
    "filter_results_by_version",
]
