"""Dựng prompt, sinh câu trả lời và kiểm soát trích dẫn."""

from .citation import (
    CitedAnswer,
    Citation,
    CitationValidationError,
    ClaimCitationMapping,
    ClaimSupport,
    build_citations,
    cite_answer,
    cite_tagged_answer,
    format_citation,
)
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
    "CitedAnswer",
    "Citation",
    "CitationValidationError",
    "ClaimCitationMapping",
    "ClaimSupport",
    "INSUFFICIENT_EVIDENCE_MESSAGE",
    "build_citations",
    "cite_answer",
    "cite_tagged_answer",
    "format_citation",
    "format_source",
    "build_context",
    "build_messages",
    "detect_version_intent",
    "expand_article_context",
    "filter_results_by_version",
]
