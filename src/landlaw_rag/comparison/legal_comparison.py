"""Điều phối đối chiếu Luật Đất đai 2013 và pháp luật hiện hành.

Module M8 chỉ chịu trách nhiệm routing, cô lập phiên bản, dựng prompt so sánh
và kiểm tra mapping claim--evidence. Retrieval, context formatting và citation
validation tiếp tục dùng các API đã có từ M5--M7.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Literal, Mapping, Sequence

from landlaw_rag.generation import CitationValidationError, ClaimCitationMapping
from landlaw_rag.retrieval import Retriever, metadata_year


MISSING_COUNTERPART_MESSAGE = (
    "Chưa tìm thấy quy định tương ứng trong dữ liệu truy xuất."
)

Intent = Literal["qa", "comparison"]
VersionSide = Literal["2013", "current"]

_DIRECT_COMPARISON_MARKERS = (
    "so sánh",
    "đối chiếu",
    "khác nhau",
    "khác biệt",
    "thay đổi",
    "điểm mới",
)
_HISTORICAL_MARKERS = ("trước đây", "trước kia", "luật cũ", "năm 2013")
_CURRENT_MARKERS = ("hiện nay", "hiện hành", "năm 2024", "luật mới")
_REQUIRED_SECTIONS = (
    "1. Quy định năm 2013:",
    "2. Quy định hiện hành:",
    "3. Điểm giống:",
    "4. Điểm khác/thay đổi:",
)
_LEGAL_INTENTS = (
    "điều kiện", "thủ tục", "trình tự", "thời điểm", "thời hạn",
    "quyền", "nghĩa vụ", "bồi thường", "hỗ trợ", "thu hồi",
)
_LEGAL_ACTIONS = (
    "chuyển nhượng quyền sử dụng đất",
    "chuyển đổi quyền sử dụng đất",
    "tặng cho quyền sử dụng đất",
    "thừa kế quyền sử dụng đất",
    "thế chấp quyền sử dụng đất",
    "góp vốn bằng quyền sử dụng đất",
    "cho thuê quyền sử dụng đất",
    "chuyển mục đích sử dụng đất",
    "cấp giấy chứng nhận",
)
_SUBJECT_ALIASES = {
    "cá nhân": ("cá nhân", "người sử dụng đất"),
    "hộ gia đình": ("hộ gia đình", "người sử dụng đất"),
    "tổ chức": ("tổ chức", "người sử dụng đất"),
    "doanh nghiệp": ("doanh nghiệp", "tổ chức kinh tế", "người sử dụng đất"),
}
_FOCUS_STOPWORDS = {
    "so", "sánh", "theo", "luật", "đất", "đai", "năm", "pháp", "hiện",
    "hành", "để", "được", "và", "với", "giữa", "quy", "định", "của",
    "2013", "2024", "45", "31", "qh13", "qh15",
}


def _normalize(value: Any) -> str:
    return " ".join(
        unicodedata.normalize("NFC", str(value or "")).lower().split()
    )


def detect_legal_intent(query: str) -> Intent:
    """Phân luồng QA thông thường và yêu cầu đối chiếu bằng luật rõ ràng."""

    normalized = _normalize(query)
    if not normalized:
        raise ValueError("Query không được rỗng")
    years = set(re.findall(r"\b(?:2013|2024)\b", normalized))
    direct = any(marker in normalized for marker in _DIRECT_COMPARISON_MARKERS)
    temporal_pair = (
        any(marker in normalized for marker in _HISTORICAL_MARKERS)
        and any(marker in normalized for marker in _CURRENT_MARKERS)
    )
    return "comparison" if direct or years == {"2013", "2024"} or temporal_pair else "qa"


def extract_comparison_topic(query: str) -> str:
    """Bỏ tín hiệu routing nhưng giữ nguyên chủ đề pháp lý dùng cho cả hai lượt search."""

    topic = unicodedata.normalize("NFC", query).strip()
    # Chỉ bỏ các động từ routing chắc chắn. Giữ "thay đổi"/"điểm mới" vì
    # chúng có thể thuộc chính chủ đề, ví dụ "thay đổi mục đích sử dụng đất".
    removable = (
        "so sánh",
        "đối chiếu",
        "khác nhau như thế nào",
        "khác nhau thế nào",
        "giữa luật đất đai 2013 và 2024",
        "giữa năm 2013 và 2024",
        "theo luật đất đai 2013 và luật đất đai 2024",
        "theo luật 2013 và 2024",
        "2013 và 2024",
        "2024 và 2013",
    )
    for marker in sorted(removable, key=len, reverse=True):
        topic = re.sub(re.escape(marker), " ", topic, flags=re.IGNORECASE)
    topic = re.sub(r"\b(?:45[/-]2013[/-]QH13|31[/-]2024[/-]QH15)\b", " ", topic, flags=re.IGNORECASE)
    topic = re.sub(r"\s+", " ", topic).strip(" .,:;?-–—")
    return topic or query.strip()


def evidence_side(item: Mapping[str, Any]) -> VersionSide | None:
    """Xác định phía từ metadata; không dùng số Điều hay chunk_id để ghép luật."""

    year = metadata_year(dict(item.get("metadata") or {}))
    if year == 2013:
        return "2013"
    if year is not None and year >= 2024:
        return "current"
    return None


def isolate_version(
    results: Sequence[Mapping[str, Any]], side: VersionSide
) -> list[dict[str, Any]]:
    """Hard-filter kết quả theo phiên bản và khử trùng theo chunk_id."""

    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for result in results:
        if evidence_side(result) != side:
            continue
        metadata = result.get("metadata") or {}
        chunk_id = str(result.get("chunk_id") or metadata.get("chunk_id") or "").strip()
        if not chunk_id or chunk_id in seen:
            continue
        selected.append(dict(result))
        seen.add(chunk_id)
    return selected


def _focus_text(item: Mapping[str, Any]) -> tuple[str, str, str]:
    metadata = item.get("metadata") or {}
    article_title = _normalize(metadata.get("article_title"))
    heading = _normalize(" ".join(
        str(metadata.get(field) or "")
        for field in ("chapter", "section", "article", "article_title", "clause", "point")
    ))
    body = _normalize(item.get("text") or item.get("content"))
    return article_title, heading, body


def _keyword_coverage(query: str, candidate: str) -> float:
    terms = {
        token for token in re.findall(r"[0-9a-zà-ỹđ]+", _normalize(query))
        if len(token) > 1 and token not in _FOCUS_STOPWORDS
    }
    return sum(term in candidate for term in terms) / len(terms) if terms else 0.0


def rerank_legal_focus(
    query: str, results: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Rerank theo legal intent, subject và action; không ánh xạ bằng số Điều."""

    normalized_query = _normalize(query)
    requested_intents = [term for term in _LEGAL_INTENTS if term in normalized_query]
    requested_actions = [term for term in _LEGAL_ACTIONS if term in normalized_query]
    requested_subjects = [term for term in _SUBJECT_ALIASES if term in normalized_query]
    ranked: list[dict[str, Any]] = []

    general_condition_query = bool(requested_actions) and "điều kiện" in normalized_query
    for source_order, original in enumerate(results):
        item = dict(original)
        article_title, heading, body = _focus_text(item)
        searchable = f"{heading} {body}"
        intent_title_matches = sum(term in article_title for term in requested_intents)
        intent_matches = sum(term in searchable for term in requested_intents)
        action_matches = sum(term in searchable for term in requested_actions)
        subject_matches = sum(
            any(alias in searchable for alias in _SUBJECT_ALIASES[subject])
            for subject in requested_subjects
        )
        general_rights_condition_match = int(
            general_condition_query
            and (
                "người sử dụng đất được thực hiện" in body
                or "người sử dụng đất được chuyển nhượng" in body
            )
            and (
                "khi có các điều kiện" in body
                or "khi có đủ các điều kiện" in body
                or "các điều kiện sau đây" in body
            )
        )
        heading_coverage = _keyword_coverage(query, heading)
        text_coverage = _keyword_coverage(query, body)
        focus_score = (
            12.0 * general_rights_condition_match
            + 6.0 * intent_title_matches
            + 5.0 * action_matches
            + 2.0 * intent_matches
            + 1.5 * subject_matches
            + 3.0 * heading_coverage
            + text_coverage
        )
        item["legal_focus"] = {
            "intent_title_matches": intent_title_matches,
            "intent_matches": intent_matches,
            "action_matches": action_matches,
            "subject_matches": subject_matches,
            "general_rights_condition_match": general_rights_condition_match,
            "heading_coverage": round(heading_coverage, 6),
            "text_coverage": round(text_coverage, 6),
        }
        item["legal_focus_score"] = round(focus_score, 6)
        item["_comparison_source_order"] = source_order
        ranked.append(item)

    ranked.sort(
        key=lambda item: (
            item["legal_focus_score"],
            float(item.get("final_score", item.get("score", 0.0)) or 0.0),
            -item["_comparison_source_order"],
        ),
        reverse=True,
    )
    for rank, item in enumerate(ranked, start=1):
        item.pop("_comparison_source_order", None)
        item["comparison_rank"] = rank
    return ranked


@dataclass(frozen=True)
class ComparisonEvidence:
    """Hai tập evidence độc lập của cùng một chủ đề pháp lý."""

    topic: str
    legacy: tuple[dict[str, Any], ...]
    current: tuple[dict[str, Any], ...]
    legacy_query: str
    current_query: str

    @property
    def complete(self) -> bool:
        return bool(self.legacy and self.current)


def retrieve_comparison_evidence(
    retriever: Retriever,
    query: str,
    *,
    top_k_per_side: int = 6,
    candidate_multiplier: int = 4,
) -> ComparisonEvidence:
    """Gọi retriever hai lần rồi hard-filter, không tạo một pool evidence hỗn hợp."""

    if detect_legal_intent(query) != "comparison":
        raise ValueError("Query không có ý định legal comparison")
    if top_k_per_side <= 0 or candidate_multiplier <= 0:
        raise ValueError("Giới hạn retrieval phải lớn hơn 0")

    topic = extract_comparison_topic(query)
    legacy_query = f"{topic} Luật Đất đai 2013 45/2013/QH13"
    current_query = f"{topic} Luật Đất đai 2024 31/2024/QH15 hiện hành"
    candidate_k = top_k_per_side * candidate_multiplier

    legacy_candidates = retriever.search(legacy_query, top_k=candidate_k)
    current_candidates = retriever.search(current_query, top_k=candidate_k)
    legacy = rerank_legal_focus(
        topic, isolate_version(legacy_candidates, "2013")
    )[:top_k_per_side]
    current = rerank_legal_focus(
        topic, isolate_version(current_candidates, "current")
    )[:top_k_per_side]
    return ComparisonEvidence(
        topic=topic,
        legacy=tuple(legacy),
        current=tuple(current),
        legacy_query=legacy_query,
        current_query=current_query,
    )


def offset_source_labels(context: str, offset: int) -> str:
    """Đổi nhãn context thứ hai sang chỉ số global dùng bởi validator M7."""

    if offset < 0:
        raise ValueError("offset không được âm")
    return re.sub(
        r"\[Nguồn\s+(\d+)\]",
        lambda match: f"[Nguồn {int(match.group(1)) + offset}]",
        context,
        flags=re.IGNORECASE,
    )


def build_comparison_messages(
    query: str,
    legacy_context: str,
    current_context: str,
    sections: tuple[int, ...] = (1, 2, 3, 4),
) -> list[dict[str, str]]:
    """Dựng prompt M8; model chỉ chọn nhãn, M7 mới sinh citation pháp lý."""

    if detect_legal_intent(query) != "comparison":
        raise ValueError("Query không có ý định legal comparison")
    if not legacy_context.strip() or not current_context.strip():
        raise ValueError(MISSING_COUNTERPART_MESSAGE)
    if sections not in ((1, 2), (3, 4), (1, 2, 3, 4)):
        raise ValueError("sections phải là (1, 2), (3, 4) hoặc (1, 2, 3, 4)")

    legacy_labels = [int(value) for value in re.findall(r"\[Nguồn\s+(\d+)\]", legacy_context)]
    current_labels = [int(value) for value in re.findall(r"\[Nguồn\s+(\d+)\]", current_context)]
    legacy_range = ", ".join(f"[Nguồn {value}]" for value in legacy_labels)
    current_range = ", ".join(f"[Nguồn {value}]" for value in current_labels)

    requested_headings = " ".join(_REQUIRED_SECTIONS[number - 1] for number in sections)
    system_prompt = (
        "Bạn đối chiếu pháp luật đất đai Việt Nam chỉ từ hai nhóm EVIDENCE được cung cấp. "
        "Hai nhóm đã được retrieve và cô lập phiên bản độc lập. Không dùng kiến thức bên ngoài, "
        "không suy đoán thay đổi pháp luật và không ghép hai quy định chỉ vì chúng có cùng số Điều. "
        "Chỉ so sánh các nội dung cùng chủ đề pháp lý được evidence trực tiếp hỗ trợ. "
        "Không tự viết tên văn bản, Điều, Khoản, Điểm hoặc danh mục nguồn. "
        "Mỗi claim phải ở một dòng và kết thúc bằng nhãn [Nguồn n] có sẵn. "
        "Nhận định ở mục 1 chỉ dùng nguồn 2013; mục 2 chỉ dùng nguồn hiện hành; "
        "mục 3 và 4 phải dẫn ít nhất một nguồn từ mỗi phía. Tuyệt đối không được bỏ "
        "nhãn nguồn ở bất kỳ dòng nào. "
        "Hệ thống M7 sẽ kiểm tra nhãn và sinh citation deterministic từ metadata. "
        f"Xuất đúng {len(sections)} dòng nội dung, theo thứ tự các mục: "
        f"{requested_headings}"
    )
    if sections == (1, 2):
        output_contract = (
            "Dòng 1 bắt đầu chính xác bằng '1. Quy định năm 2013:' và chỉ dùng nhãn phía 2013. "
            "Dòng 2 bắt đầu chính xác bằng '2. Quy định hiện hành:' và chỉ dùng nhãn phía hiện hành."
        )
    elif sections == (3, 4):
        output_contract = (
            "Dòng 1 bắt đầu chính xác bằng '3. Điểm giống:'; dòng 2 bắt đầu chính xác bằng "
            "'4. Điểm khác/thay đổi:'. Mỗi dòng phải có một nhận định đầy đủ và ít nhất "
            "một nhãn phía 2013 cùng một nhãn phía hiện hành. Không được chỉ in nhãn nguồn."
        )
    else:
        output_contract = (
            "Mỗi dòng phải bắt đầu chính xác bằng tiêu đề mục tương ứng. Mục 1 chỉ dùng nhãn "
            "phía 2013; mục 2 chỉ dùng nhãn phía hiện hành; mục 3 và 4 mỗi mục phải dùng ít "
            "nhất một nhãn từ mỗi phía. Không được chỉ in nhãn nguồn."
        )

    user_prompt = (
        f"CÂU HỎI:\n{query.strip()}\n\n"
        f"EVIDENCE LUẬT ĐẤT ĐAI 2013:\n{legacy_context}\n\n"
        f"EVIDENCE PHÁP LUẬT HIỆN HÀNH:\n{current_context}\n\n"
        f"NHÃN ĐƯỢC PHÉP CHO PHÍA 2013: {legacy_range}\n"
        f"NHÃN ĐƯỢC PHÉP CHO PHÍA HIỆN HÀNH: {current_range}\n\n"
        f"Chỉ trả lời các mục {', '.join(map(str, sections))}; mỗi mục một dòng. "
        f"{output_contract} Không viết dòng nào mà thiếu [Nguồn n]."
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def build_validation_retry_messages(
    base_messages: list[dict[str, str]],
    invalid_output: str,
    sections: tuple[int, ...],
) -> list[dict[str, str]]:
    """Tạo lượt sửa format có kèm output sai và contract cụ thể."""

    if sections == (1, 2):
        template = (
            "1. Quy định năm 2013: <nhận định đầy đủ> [Nguồn n]\n"
            "2. Quy định hiện hành: <nhận định đầy đủ> [Nguồn n]"
        )
    elif sections == (3, 4):
        template = (
            "3. Điểm giống: <nhận định đầy đủ> [Nguồn phía 2013] [Nguồn phía hiện hành]\n"
            "4. Điểm khác/thay đổi: <nhận định đầy đủ> [Nguồn phía 2013] [Nguồn phía hiện hành]"
        )
    else:
        raise ValueError("Retry chỉ hỗ trợ hai lượt (1, 2) hoặc (3, 4)")

    return base_messages + [
        {"role": "assistant", "content": invalid_output},
        {
            "role": "user",
            "content": (
                "Output trên sai cấu trúc. Hãy viết lại từ evidence, không giải thích, không chỉ "
                "liệt kê nhãn nguồn và không sao chép phần trong dấu <>. Xuất đúng mẫu hai dòng:\n"
                f"{template}"
            ),
        },
    ]


def canonicalize_comparison_structure(answer: str) -> str:
    """Chuẩn hóa nhãn mục 1–4 mà không sửa nội dung claim hoặc nhãn nguồn."""

    answer = re.sub(
        r"\[\s*Nguồn\s+(\d+)\s*\]",
        lambda match: f"[Nguồn {match.group(1)}]",
        answer,
        flags=re.IGNORECASE,
    )
    normalized_lines: list[str] = []
    current_section: str | None = None

    def flush_section() -> None:
        nonlocal current_section
        if current_section is not None:
            normalized_lines.append(current_section.strip())
            current_section = None

    for raw_line in answer.strip().splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = re.match(r"^([1-4])\.\s*(.*)$", line, flags=re.DOTALL)
        if match is None:
            if current_section is None:
                normalized_lines.append(line)
            else:
                continuation = re.sub(r"^[-*•]\s*", "", line).strip()
                if continuation:
                    current_section = f"{current_section} {continuation}"
            continue
        flush_section()
        number = int(match.group(1))
        expected = _REQUIRED_SECTIONS[number - 1]
        remainder = match.group(2).strip()
        expected_without_number = expected.split(". ", 1)[1]
        if remainder.startswith(expected_without_number):
            current_section = f"{number}. {remainder}"
        else:
            current_section = f"{expected} {remainder}".rstrip()
    flush_section()
    return "\n".join(normalized_lines)


def validate_comparison_structure(answer: str) -> None:
    """Từ chối output thiếu hoặc đảo thứ tự bốn phần bắt buộc."""

    positions = [answer.find(section) for section in _REQUIRED_SECTIONS]
    if any(position < 0 for position in positions) or positions != sorted(positions):
        raise CitationValidationError("Câu trả lời thiếu hoặc sai thứ tự cấu trúc M8")


def _mapping_section(claim: str) -> int | None:
    for number, prefix in enumerate(_REQUIRED_SECTIONS, start=1):
        if claim.startswith(prefix):
            return number
    return None


def validate_comparison_mapping(
    mappings: Sequence[ClaimCitationMapping],
    legacy_evidence: Sequence[Mapping[str, Any]],
    current_evidence: Sequence[Mapping[str, Any]],
) -> None:
    """Bảo đảm claim từng phần chỉ trỏ tới đúng pool evidence đã cô lập."""

    legacy_ids = {
        str(item.get("chunk_id") or (item.get("metadata") or {}).get("chunk_id"))
        for item in legacy_evidence
    }
    current_ids = {
        str(item.get("chunk_id") or (item.get("metadata") or {}).get("chunk_id"))
        for item in current_evidence
    }
    if legacy_ids & current_ids:
        raise CitationValidationError("Hai phía comparison chứa chunk_id trùng nhau")

    for mapping in mappings:
        section = _mapping_section(mapping.claim)
        cited = set(mapping.chunk_ids)
        if section is None:
            raise CitationValidationError(f"Claim nằm ngoài cấu trúc M8: {mapping.claim!r}")
        if section == 1 and (not cited or not cited <= legacy_ids):
            raise CitationValidationError("Quy định 2013 trỏ sai phía evidence")
        if section == 2 and (not cited or not cited <= current_ids):
            raise CitationValidationError("Quy định hiện hành trỏ sai phía evidence")
        if section in (3, 4) and not (cited & legacy_ids and cited & current_ids):
            raise CitationValidationError(
                "Nhận định giống/khác phải có evidence từ cả hai phía"
            )
