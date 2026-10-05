"""Đối chiếu quy định giữa các phiên bản luật."""

from .legal_comparison import (
    MISSING_COUNTERPART_MESSAGE,
    ComparisonEvidence,
    build_comparison_messages,
    build_validation_retry_messages,
    canonicalize_comparison_structure,
    detect_legal_intent,
    evidence_side,
    extract_comparison_topic,
    isolate_version,
    offset_source_labels,
    rerank_legal_focus,
    retrieve_comparison_evidence,
    validate_comparison_mapping,
    validate_comparison_structure,
)

__all__ = [
    "MISSING_COUNTERPART_MESSAGE",
    "ComparisonEvidence",
    "build_comparison_messages",
    "build_validation_retry_messages",
    "canonicalize_comparison_structure",
    "detect_legal_intent",
    "evidence_side",
    "extract_comparison_topic",
    "isolate_version",
    "offset_source_labels",
    "rerank_legal_focus",
    "retrieve_comparison_evidence",
    "validate_comparison_mapping",
    "validate_comparison_structure",
]

