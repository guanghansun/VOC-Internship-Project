"""Canonical public API for the VOC evidence-analysis subagent.

This module is intentionally standalone and stdlib-only. It accepts plain
requirement and raw evidence dictionaries, then returns a JSON-serializable VOC
findings dictionary suitable for integration into another system.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import re
from typing import Any


VOC_SCHEMA_VERSION = "0.1.0"
FORBIDDEN_CLAIM_PHRASES = (
    "users generally",
    "the market",
    "most users",
    "consumers",
    "people prefer",
)

DEFAULT_CONFIG = {
    "max_records": None,
    "language_filter": None,
    "min_evidence_threshold": 3,
    "min_source_threshold": 2,
    "evidence_span_strict": True,
    "target_product": "",
    "competitor_terms": [],
    "extraction_mode": "rule_based",
}

PRODUCT_RULES = [
    ("usability", "negative", ("hard to use", "difficult to use", "confusing", "annoying", "frustrating", "too many steps", "all manual", "too manual", "done manually", "manually track", "manual process", "inconvenient")),
    ("usability", "positive", ("easy to use", "simple", "convenient", "intuitive", "saves time")),
    ("performance", "negative", ("doesn't work", "does not work", "broken", "unreliable", "slow", "inaccurate", "fails", "buggy")),
    ("performance", "positive", ("works well", "reliable", "accurate", "fast", "effective")),
    ("price_value", "negative", ("expensive", "overpriced", "not worth it", "too costly", "subscription is too much")),
    ("price_value", "positive", ("worth it", "good value", "affordable", "cheap")),
    ("quality_design", "negative", ("flimsy", "poor quality", "uncomfortable", "ugly", "bad design")),
    ("quality_design", "positive", ("durable", "comfortable", "stylish", "good design", "well made")),
    ("support_service", "negative", ("bad support", "no support", "poor customer service", "warranty issue", "refund problem")),
    ("support_service", "positive", ("good support", "responsive support", "easy return", "helpful service")),
    ("availability", "negative", ("out of stock", "hard to find", "unavailable", "long shipping", "delayed delivery")),
    ("availability", "positive", ("easy to find", "available", "fast shipping", "quick delivery")),
]

COMPARISON_RULES = (
    "works better than",
    "works worse than",
    "not as good as",
    "better than",
    "worse than",
    "cheaper than",
    "more expensive than",
    "compared to",
    "compared with",
    "versus",
    "instead of",
    "alternative to",
    "switched from",
    "switched to",
    "prefer",
    "rather than",
    "vs",
    "over",
)

DECISION_RULES = [
    ("not_recommending", ("would not recommend", "wouldn't recommend", "do not recommend", "don't recommend", "avoid this", "not worth recommending")),
    ("purchase_consideration", ("considering buying", "thinking about buying", "looking to buy", "planning to buy", "would buy", "willing to pay", "would pay", "I need something that")),
    ("purchase_barrier", ("too expensive", "not worth it", "can't justify the price", "price is too high", "subscription is too much", "monthly fee is too much", "deal breaker", "stopped me from buying")),
    ("bought", ("I bought", "I purchased", "I ordered", "I paid for", "I subscribed", "I upgraded to")),
    ("returned", ("I returned", "sent it back", "got a refund", "asked for a refund", "returned it", "refund process")),
    ("recommending", ("would recommend", "highly recommend", "recommend it", "worth recommending", "tell people to buy")),
    ("switching_intent", ("switched from", "switched to", "moving from", "moving to", "replacing", "looking for an alternative", "alternative to")),
    ("renewal_or_subscription", ("subscription cost", "subscription is too much", "paying for subscription", "pay for subscription", "cancel subscription", "cancelled subscription", "monthly subscription", "annual subscription", "subscription fee", "monthly fee", "annual plan", "renewal", "renew")),
]

COMPLAINT_HINTS = {"complaint", "problem", "negative", "pain", "issue"}
PRAISE_HINTS = {"praise", "recommendation", "recommended", "positive", "love"}
STRONG_TERMS = {
    "very",
    "extremely",
    "terrible",
    "awful",
    "amazing",
    "excellent",
    "love",
    "hate",
    "always",
    "never",
    "too",
    "really",
}
MILD_TERMS = {"slightly", "somewhat", "a bit", "kind of", "okay"}


@dataclass
class _ProductEvaluationEvidence:
    extraction_id: str
    evidence_id: str
    evidence_span: str
    span_validated: bool
    extraction_method: str
    content_id: str
    source_url: str | None
    category: str
    dimension: str
    direction: str
    intensity: str


@dataclass
class _ComparisonEvidence:
    extraction_id: str
    evidence_id: str
    compared_product: str
    comparison_basis: str
    preferred_option: str
    direction: str
    switching_intent: bool
    evidence_span: str
    span_validated: bool
    extraction_method: str
    content_id: str
    source_url: str | None
    category: str
    signal: str


@dataclass
class _DecisionEvidence:
    extraction_id: str
    evidence_id: str
    evidence_span: str
    span_validated: bool
    extraction_method: str
    content_id: str
    source_url: str | None
    category: str
    signal_type: str
    price_point_mentioned: bool


def run_voc_evidence_analysis(
    requirement: dict,
    raw_evidence_list: list[dict],
    config: dict | None = None,
) -> dict:
    """Run VOC evidence analysis and never raise implementation errors to caller."""
    requirement_id = _requirement_id(requirement)
    try:
        return VOCService(config).analyze(requirement, raw_evidence_list)
    except Exception as exc:  # pragma: no cover - defensive public API boundary.
        return {
            "voc_schema_version": VOC_SCHEMA_VERSION,
            "requirement_id": requirement_id,
            "error": str(exc),
            "limitations": _limitations(),
            "validation_issues": ["analysis_failed"],
        }


class VOCService:
    """Small deterministic VOC evidence-analysis service."""

    def __init__(self, config: dict | None = None) -> None:
        self.config = _normalize_config(config)

    def analyze(self, requirement: dict, raw_evidence_list: list[dict]) -> dict[str, Any]:
        normalized_evidence = _normalize_raw_evidence_list(raw_evidence_list, self.config)
        records = _build_records(requirement, normalized_evidence, self.config)
        product_evidence = self._extract_product_evaluations(records)
        comparison_evidence = self._extract_comparisons(records)
        decision_evidence = self._extract_decisions(records)

        top_themes = _aggregate_product_evaluations(product_evidence)
        competitor_signals = _aggregate_comparisons(comparison_evidence)
        decision_signals = _aggregate_decisions(decision_evidence)
        insight_candidates = self._build_insight_candidates(
            product_evidence,
            comparison_evidence,
            decision_evidence,
            len(records),
        )

        result = {
            "voc_schema_version": VOC_SCHEMA_VERSION,
            "analyzed_at": _now_iso(),
            "requirement_id": _requirement_id(requirement),
            "records_analyzed": len(records),
            "sample_size": len(records),
            "min_evidence_met": len(records) >= int(self.config["min_evidence_threshold"]),
            "evidence_counts": {
                "product_evaluation": len(product_evidence),
                "comparison": len(comparison_evidence),
                "decision": len(decision_evidence),
            },
            "top_themes": top_themes,
            "competitor_signals": competitor_signals,
            "decision_signals": decision_signals,
            "insight_candidates": insight_candidates,
            "limitations": _limitations(self.config.get("_normalization_limitations")),
        }
        result["validation_issues"] = _validate_voc_result(result, records)
        return result

    def _extract_product_evaluations(self, records: list[dict]) -> list[dict]:
        evidence: list[dict] = []
        for record in records:
            local_index = 1
            seen: set[tuple[str, str, str, str]] = set()
            for dimension, direction, keywords in _prioritized_product_rules(record):
                for keyword in keywords:
                    span = _find_span(record["source_text"], keyword)
                    if not span or not validate_span(span, record):
                        continue
                    if _is_negated(span, keyword):
                        continue
                    final_direction = _direction_for_span(span, dimension, direction)
                    dedupe_key = (record["content_id"], dimension, final_direction, span)
                    if dedupe_key in seen:
                        continue
                    seen.add(dedupe_key)
                    item = _ProductEvaluationEvidence(
                        extraction_id=f"product_{record['content_id']}_{local_index}",
                        evidence_id=record["content_id"],
                        evidence_span=span,
                        span_validated=True,
                        extraction_method="rule_based",
                        content_id=record["content_id"],
                        source_url=record.get("source_url"),
                        category="product_evaluation",
                        dimension=dimension,
                        direction=final_direction,
                        intensity=_intensity_for_span(span),
                    )
                    evidence.append(asdict(item))
                    local_index += 1
        return evidence

    def _extract_comparisons(self, records: list[dict]) -> list[dict]:
        evidence: list[dict] = []
        target_product = str(self.config.get("target_product") or "").strip()
        competitor_terms = [str(term).strip() for term in self.config.get("competitor_terms", []) if str(term).strip()]
        for record in records:
            local_index = 1
            seen: set[tuple[str, str, str, str, str, str]] = set()
            for keyword in COMPARISON_RULES:
                span = _find_span(record["source_text"], keyword)
                if not span or not validate_span(span, record):
                    continue
                if keyword == "over" and not _span_has_target_and_competitor(span, target_product, competitor_terms):
                    continue
                compared_product = _detect_compared_product(span, competitor_terms)
                basis = _comparison_basis(span)
                preferred_option, direction = _infer_comparison_preference(span, keyword, target_product, compared_product)
                switching_intent = _contains_pattern(span, "switched from") or _contains_pattern(span, "switched to") or _contains_pattern(span, "moving from") or _contains_pattern(span, "moving to")
                dedupe_key = (record["content_id"], compared_product, basis, preferred_option, direction, span)
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                item = _ComparisonEvidence(
                    extraction_id=f"comparison_{record['content_id']}_{local_index}",
                    evidence_id=record["content_id"],
                    compared_product=compared_product,
                    comparison_basis=basis,
                    preferred_option=preferred_option,
                    direction=direction,
                    switching_intent=switching_intent,
                    evidence_span=span,
                    span_validated=True,
                    extraction_method="rule_based",
                    content_id=record["content_id"],
                    source_url=record.get("source_url"),
                    category="comparison",
                    signal=keyword.replace(" ", "_"),
                )
                evidence.append(asdict(item))
                local_index += 1
        return evidence

    def _extract_decisions(self, records: list[dict]) -> list[dict]:
        evidence: list[dict] = []
        for record in records:
            local_index = 1
            seen: set[tuple[str, str, str]] = set()
            for signal_type, keywords in DECISION_RULES:
                for keyword in keywords:
                    span = _find_span(record["source_text"], keyword)
                    if not span or not validate_span(span, record):
                        continue
                    if _decision_span_is_blocked(signal_type, span):
                        continue
                    dedupe_key = (record["content_id"], signal_type, span)
                    if dedupe_key in seen:
                        continue
                    seen.add(dedupe_key)
                    item = _DecisionEvidence(
                        extraction_id=f"decision_{record['content_id']}_{local_index}",
                        evidence_id=record["content_id"],
                        evidence_span=span,
                        span_validated=True,
                        extraction_method="rule_based",
                        content_id=record["content_id"],
                        source_url=record.get("source_url"),
                        category="decision",
                        signal_type=signal_type,
                        price_point_mentioned=_price_point_mentioned(span),
                    )
                    evidence.append(asdict(item))
                    local_index += 1
        return evidence

    def _build_insight_candidates(
        self,
        product_evidence: list[dict],
        comparison_evidence: list[dict],
        decision_evidence: list[dict],
        sample_size: int,
    ) -> list[dict]:
        min_evidence = int(self.config["min_evidence_threshold"])
        min_sources = int(self.config["min_source_threshold"])

        candidates = self._collect_insight_candidates(
            product_evidence,
            comparison_evidence,
            decision_evidence,
            sample_size,
            min_evidence,
            min_sources,
        )
        if candidates or sample_size < min_evidence:
            return candidates

        # The overall sample meets min_evidence_threshold, but every
        # fine-grained group (by dimension/competitor/signal type) is too
        # small or too narrowly sourced to clear the configured thresholds.
        # Surface the strongest groups as preliminary, low-confidence
        # signals instead of returning nothing.
        fallback = self._collect_insight_candidates(
            product_evidence,
            comparison_evidence,
            decision_evidence,
            sample_size,
            1,
            1,
            preliminary=True,
        )
        fallback.sort(key=lambda candidate: (candidate["evidence_count"], candidate["source_count"]), reverse=True)
        return fallback[:5]

    def _collect_insight_candidates(
        self,
        product_evidence: list[dict],
        comparison_evidence: list[dict],
        decision_evidence: list[dict],
        sample_size: int,
        min_evidence: int,
        min_sources: int,
        preliminary: bool = False,
    ) -> list[dict]:
        candidates: list[dict] = []

        for group in _group_items(product_evidence, ("dimension", "direction")):
            if not _meets_threshold(group["items"], min_evidence, min_sources):
                continue
            dimension, direction = group["key"]
            claim = (
                f"In this sample, {group['count']} of {sample_size} evidence items describe "
                f"{direction} signals related to {dimension}."
            )
            candidates.append(_make_candidate(claim, "product_evaluation", group["items"], preliminary))

        for group in _group_items(comparison_evidence, ("compared_product", "comparison_basis", "preferred_option", "direction")):
            if not _meets_threshold(group["items"], min_evidence, min_sources):
                continue
            compared_product, comparison_basis, _preferred_option, _direction = group["key"]
            claim = f"In this sample, {group['count']} of {sample_size} evidence items compare against {compared_product} on {comparison_basis}."
            candidates.append(_make_candidate(claim, "comparison", group["items"], preliminary))

        for group in _group_items(decision_evidence, ("signal_type",)):
            if not _meets_threshold(group["items"], min_evidence, min_sources):
                continue
            signal_type = group["key"][0]
            claim = f"In this sample, {group['count']} of {sample_size} evidence items show {signal_type} decision signals."
            candidates.append(_make_candidate(claim, "decision", group["items"], preliminary))

        return [candidate for candidate in candidates if _claim_is_safe(candidate["claim"])]


def validate_span(span: str, item: dict) -> bool:
    """Return True only when span is an exact substring of title + body."""
    if not span:
        return False
    source_text = item.get("source_text")
    if source_text is None:
        source_text = _source_text(item)
    return span in source_text


def build_confidence(
    items_or_count: list[dict] | int,
    source_count: int | None = None,
    group_direction: str | None = None,
) -> dict[str, Any]:
    """Build a small confidence object for a group of evidence.

    group_direction — pass the aggregation group's direction key so that a
    "mixed" direction group is reported correctly even though all pre-grouped
    items share the same direction value.
    """
    if isinstance(items_or_count, list):
        items = items_or_count
        evidence_count = len(items)
        actual_source_count = _source_count(items)
        item_directions = {item.get("direction") for item in items if item.get("direction")}
    else:
        evidence_count = items_or_count
        actual_source_count = int(source_count or 0)
        item_directions = set()

    effective_direction = group_direction if group_direction is not None else (
        next(iter(item_directions)) if len(item_directions) == 1 else None
    )

    if effective_direction == "mixed":
        signal_consistency = "mixed"
    elif "positive" in item_directions and "negative" in item_directions:
        signal_consistency = "mixed"
    elif len(item_directions) > 1:
        signal_consistency = "contradicted"
    else:
        signal_consistency = "consistent"

    if evidence_count > 5 and actual_source_count > 1:
        confidence_label = "high"
    elif 3 <= evidence_count <= 5 and actual_source_count >= 2:
        confidence_label = "medium"
    else:
        confidence_label = "low"

    return {
        "evidence_count": evidence_count,
        "source_count": actual_source_count,
        "signal_consistency": signal_consistency,
        "confidence_label": confidence_label,
    }


def _normalize_config(config: dict | None) -> dict:
    merged = dict(DEFAULT_CONFIG)
    if isinstance(config, dict):
        merged.update(config)
    merged["min_evidence_threshold"] = _positive_int_or_default(
        merged.get("min_evidence_threshold"), DEFAULT_CONFIG["min_evidence_threshold"]
    )
    merged["min_source_threshold"] = _positive_int_or_default(
        merged.get("min_source_threshold"), DEFAULT_CONFIG["min_source_threshold"]
    )
    merged["max_records"] = _optional_positive_int(merged.get("max_records"))
    merged["language_filter"] = _optional_clean_str(merged.get("language_filter"))
    merged["target_product"] = _clean_str(merged.get("target_product"))
    merged["competitor_terms"] = _str_list(merged.get("competitor_terms"))
    merged["extraction_mode"] = _clean_str(merged.get("extraction_mode")) or "rule_based"
    merged["evidence_span_strict"] = bool(merged.get("evidence_span_strict", True))
    merged["_normalization_limitations"] = []
    return merged


def _normalize_raw_evidence_list(raw_evidence_list: object, config: dict) -> list[dict]:
    limitations: list[str] = []
    normalized: list[dict] = []
    generated_count = 0
    dropped_count = 0
    generated_ids = False

    if raw_evidence_list is None:
        config["_normalization_limitations"] = limitations
        return []
    if not isinstance(raw_evidence_list, list):
        config["_normalization_limitations"] = ["Some raw evidence items were ignored because they were empty or invalid."]
        return []

    language_filter = config.get("language_filter")
    max_records = config.get("max_records")

    for raw in raw_evidence_list:
        if max_records is not None and len(normalized) >= max_records:
            break
        if not isinstance(raw, dict):
            dropped_count += 1
            continue

        item = dict(raw)
        title = _clean_str(item.get("title"))
        body = _clean_str(item.get("body"))
        original_text = _clean_str(item.get("text"))
        if not body and original_text:
            body = original_text
        if not title and not body:
            dropped_count += 1
            continue

        language = _clean_str(item.get("language")) or "en"
        if language_filter and language != language_filter:
            continue

        evidence_id = _clean_str(item.get("evidence_id")) or _clean_str(item.get("id"))
        if not evidence_id:
            evidence_id = f"generated_{generated_count}"
            generated_count += 1
            generated_ids = True

        normalized.append(
            {
                **item,
                "evidence_id": evidence_id,
                "title": title,
                "body": body,
                "text": original_text,
                "source": _clean_str(item.get("source")),
                "source_url": _clean_str(item.get("source_url") or item.get("url")),
                "subreddit": _clean_str(item.get("subreddit")),
                "language": language,
                "matched_patterns": _str_list(item.get("matched_patterns")),
                "score": _int_or_zero(item.get("score")),
                "comment_count": _int_or_zero(item.get("comment_count")),
            }
        )

    if dropped_count:
        limitations.append("Some raw evidence items were ignored because they were empty or invalid.")
    if generated_ids:
        limitations.append("Some evidence items were missing evidence_id values; deterministic local IDs were generated.")
    if language_filter:
        limitations.append("A language filter was applied before analysis.")
    if max_records is not None:
        limitations.append("A max_records limit was applied before analysis.")
    config["_normalization_limitations"] = limitations
    return normalized


def _positive_int_or_default(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _optional_positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _int_or_zero(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _clean_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _optional_clean_str(value: Any) -> str | None:
    cleaned = _clean_str(value)
    return cleaned or None


def _str_list(value: Any) -> list[str]:
    if isinstance(value, str):
        cleaned = value.strip()
        return [cleaned] if cleaned else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []



def _build_records(requirement: dict, raw_evidence_list: list[dict], config: dict) -> list[dict]:
    requirement_id = _requirement_id(requirement)
    records: list[dict] = []
    for index, raw in enumerate(raw_evidence_list):
        source_text = _source_text(raw)
        if not source_text.strip():
            continue
        content_id = raw.get("evidence_id") or raw.get("id") or f"raw_evidence_{index + 1}"
        records.append(
            {
                "content_id": str(content_id),
                "requirement_id": requirement_id,
                "platform": raw.get("source") or raw.get("platform"),
                "source_url": raw.get("source_url") or raw.get("url"),
                "title": raw.get("title"),
                "body": raw.get("body"),
                "text": source_text,
                "source_text": source_text,
                "created_at": raw.get("created_at"),
                "matched_patterns": raw.get("matched_patterns") or [],
                "metadata": {
                    "subreddit": raw.get("subreddit"),
                    "post_id": raw.get("post_id"),
                    "comment_id": raw.get("comment_id"),
                    "fetched_at": raw.get("fetched_at"),
                    "matched_patterns": raw.get("matched_patterns"),
                    "raw_payload": raw.get("raw_payload"),
                    "task_group_id": raw.get("task_group_id"),
                    "task_group_run_id": raw.get("task_group_run_id"),
                },
            }
        )
    return records


def _source_text(item: dict) -> str:
    title = str(item.get("title") or "").strip()
    body = str(item.get("body") or "").strip()
    if title and body:
        return f"{title}\n\n{body}"
    return title or body


def _find_span(text: str, keyword: str) -> str | None:
    keyword_lower = keyword.lower()
    for sentence in _split_sentences(text):
        if not _contains_pattern(sentence, keyword):
            continue
        best_span = sentence
        for clause in _split_clauses(sentence):
            if not _contains_pattern(clause, keyword) or len(clause) >= len(best_span):
                continue
            if len(clause.split()) < 2:
                # Skip single-word fragments like "confusing." - they are
                # technically exact substrings but lack enough context to be
                # useful as a quoted evidence span. Keep the larger span
                # (a longer clause, or the full sentence) instead.
                continue
            best_span = clause
        return best_span
    return None


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [part.strip() for part in parts if part.strip()]


def _split_clauses(sentence: str) -> list[str]:
    parts = re.split(r"(?:,|;|\s+but\s+|\s+and\s+)", sentence, flags=re.IGNORECASE)
    return [part.strip() for part in parts if part.strip()]


def _contains_pattern(sentence: str, pattern: str) -> bool:
    """Match product rule patterns with safer boundaries for single words."""
    normalized_sentence = " ".join(sentence.lower().split())
    normalized_pattern = " ".join(pattern.lower().split())
    if not normalized_pattern:
        return False
    if " " in normalized_pattern:
        return normalized_pattern in normalized_sentence
    return re.search(rf"\b{re.escape(normalized_pattern)}\b", normalized_sentence, flags=re.IGNORECASE) is not None

def _prioritized_product_rules(record: dict) -> list[tuple[str, str, tuple[str, ...]]]:
    hints = {str(value).lower() for value in record.get("matched_patterns", [])}
    if hints & COMPLAINT_HINTS:
        return sorted(PRODUCT_RULES, key=lambda rule: 0 if rule[1] == "negative" else 1)
    if hints & PRAISE_HINTS:
        return sorted(PRODUCT_RULES, key=lambda rule: 0 if rule[1] == "positive" else 1)
    return PRODUCT_RULES


def _direction_for_span(span: str, dimension: str, default_direction: str) -> str:
    directions = {
        direction
        for rule_dimension, direction, keywords in PRODUCT_RULES
        if rule_dimension == dimension
        for keyword in keywords
        if _contains_pattern(span, keyword) and not _is_negated(span, keyword)
    }
    if "positive" in directions and "negative" in directions:
        return "mixed"
    if len(directions) == 1:
        return next(iter(directions))
    return default_direction or "unclear"


def _intensity_for_span(span: str) -> str:
    if any(_contains_pattern(span, term) for term in STRONG_TERMS):
        return "strong"
    if any(_contains_pattern(span, term) for term in MILD_TERMS):
        return "mild"
    return "unclear"


def _span_has_target_and_competitor(span: str, target_product: str, competitor_terms: list[str]) -> bool:
    return bool(target_product and _contains_pattern(span, target_product) and any(_contains_pattern(span, term) for term in competitor_terms))


def _detect_compared_product(span: str, competitor_terms: list[str]) -> str:
    for term in competitor_terms:
        if _contains_pattern(span, term):
            return _singularize_competitor_term(term)
    return "unknown"


def _singularize_competitor_term(term: str) -> str:
    """Collapse simple plural aliases (e.g. "spreadsheets") to their singular form

    so that plural/singular variants of the same competitor term (as produced by
    voc_integration's alias expansion) aggregate into a single competitor_signals
    group instead of two.
    """
    stripped = term.strip()
    lowered = stripped.casefold()
    if len(lowered) > 2 and lowered.endswith("s") and not lowered.endswith("ss"):
        return stripped[:-1]
    return stripped


def _comparison_basis(span: str) -> str:
    basis_terms = [
        ("price_value", ("price", "expensive", "cheaper", "cost", "value", "worth", "subscription", "fee")),
        ("performance", ("works", "performance", "reliable", "accurate", "fast", "slow", "broken", "effective", "results")),
        ("usability", ("easy", "hard", "confusing", "convenient", "manual", "setup", "steps", "use")),
        ("quality_design", ("quality", "durable", "flimsy", "design", "comfortable", "ugly", "stylish", "well made")),
        ("support_service", ("support", "service", "warranty", "refund", "return")),
        ("availability", ("available", "stock", "shipping", "delivery", "out of stock")),
    ]
    for basis, terms in basis_terms:
        if any(_contains_pattern(span, term) for term in terms):
            return basis
    return "general"


def _infer_comparison_preference(span: str, pattern: str, target_product: str, compared_product: str) -> tuple[str, str]:
    lowered_pattern = pattern.lower()
    neutral_patterns = {"compared to", "compared with", "vs", "versus", "instead of", "alternative to"}
    if compared_product != "unknown" and lowered_pattern in neutral_patterns:
        return "unclear", "neutral_or_mixed"
    if not target_product or compared_product == "unknown":
        return "unclear", "unclear"
    target_pos = _term_position(span, target_product)
    competitor_pos = _term_position(span, compared_product)
    if target_pos < 0 or competitor_pos < 0:
        return "unclear", "unclear"
    if _contains_pattern(span, "switched from") or _contains_pattern(span, "moving from"):
        if competitor_pos < target_pos:
            return "target", "target_preferred"
        if target_pos < competitor_pos:
            return "competitor", "competitor_preferred"
    if _contains_pattern(span, "switched to") or _contains_pattern(span, "moving to"):
        if target_pos > competitor_pos:
            return "target", "target_preferred"
        if competitor_pos > target_pos:
            return "competitor", "competitor_preferred"

    target_before = target_pos < competitor_pos
    competitor_before = competitor_pos < target_pos
    positive_subject_patterns = {"better than", "works better than", "cheaper than", "prefer", "over", "rather than"}
    reverse_subject_patterns = {"worse than", "works worse than", "more expensive than", "not as good as"}
    if lowered_pattern in positive_subject_patterns:
        if target_before:
            return "target", "target_preferred"
        if competitor_before:
            return "competitor", "competitor_preferred"
    if lowered_pattern in reverse_subject_patterns:
        if target_before:
            return "competitor", "competitor_preferred"
        if competitor_before:
            return "target", "target_preferred"
    return "unclear", "unclear"


def _term_position(span: str, term: str) -> int:
    if not term or not _contains_pattern(span, term):
        return -1
    return span.lower().find(term.lower())


def _decision_span_is_blocked(signal_type: str, span: str) -> bool:
    if signal_type != "recommending":
        return False
    negative_recommendation_patterns = (
        "would not recommend",
        "wouldn't recommend",
        "do not recommend",
        "don't recommend",
        "not recommend",
        "avoid this",
        "not worth recommending",
    )
    return any(_contains_pattern(span, pattern) for pattern in negative_recommendation_patterns)


def _price_point_mentioned(span: str) -> bool:
    if re.search(r"\$\s?\d+(?:\.\d{1,2})?(?:\s*/\s?(?:month|mo|year|yr))?", span, flags=re.IGNORECASE):
        return True
    price_terms = ("price", "expensive", "cost", "fee", "subscription", "monthly", "annually", "paid", "pay")
    return any(_contains_pattern(span, term) for term in price_terms)



_NEGATION_WORDS = frozenset({"not", "never", "no"})


def _is_negated(sentence: str, keyword: str) -> bool:
    """Return True when a keyword is preceded by a negation word within 3 words.

    Applied to both single-word and multi-word patterns so that positive
    sub-phrases like "worth it" are correctly suppressed inside longer
    negated phrases like "not worth it".
    """
    m = re.search(rf"\b{re.escape(keyword)}\b", sentence, re.IGNORECASE)
    if not m:
        return False
    before_words = sentence[: m.start()].split()
    window = before_words[-3:] if len(before_words) >= 3 else before_words
    return any(
        w.lower() in _NEGATION_WORDS or w.lower().endswith("n't")
        for w in window
    )


def _aggregate_product_evaluations(product_evidence: list[dict]) -> list[dict]:
    results: list[dict] = []
    for group in _group_items(product_evidence, ("dimension", "direction")):
        dimension, direction = group["key"]
        items = group["items"]
        results.append({
            "theme": f"{direction} {dimension}",
            "dimension": dimension,
            "direction": direction,
            "evidence_count": group["count"],
            "source_count": _source_count(items),
            "sample_evidence_ids": _evidence_ids(items)[:3],
            "sample_extraction_ids": _extraction_ids(items)[:3],
            "sample_spans": [item["evidence_span"] for item in items[:3]],
            "confidence": build_confidence(items, group_direction=direction),
        })
    return results


def _aggregate_comparisons(comparison_evidence: list[dict]) -> list[dict]:
    results: list[dict] = []
    for group in _group_items(
        comparison_evidence,
        ("compared_product", "comparison_basis", "preferred_option", "direction"),
    ):
        compared_product, comparison_basis, preferred_option, direction = group["key"]
        items = group["items"]
        results.append({
            "compared_product": compared_product,
            "comparison_basis": comparison_basis,
            "preferred_option": preferred_option,
            "direction": direction,
            "evidence_count": group["count"],
            "source_count": _source_count(items),
            "sample_evidence_ids": _evidence_ids(items)[:3],
            "sample_extraction_ids": _extraction_ids(items)[:3],
            "sample_spans": [item["evidence_span"] for item in items[:3]],
            "confidence": build_confidence(items),
        })
    return results


def _aggregate_decisions(decision_evidence: list[dict]) -> list[dict]:
    results: list[dict] = []
    for group in _group_items(decision_evidence, ("signal_type",)):
        items = group["items"]
        results.append({
            "signal_type": group["key"][0],
            "evidence_count": group["count"],
            "source_count": _source_count(items),
            "sample_evidence_ids": _evidence_ids(items)[:3],
            "sample_extraction_ids": _extraction_ids(items)[:3],
            "sample_spans": [item["evidence_span"] for item in items[:3]],
            "price_point_mentions": sum(1 for item in items if item.get("price_point_mentioned")),
            "confidence": build_confidence(items),
        })
    return results


def _group_items(items: list[dict], fields: tuple[str, ...]) -> list[dict]:
    grouped: dict[tuple[Any, ...], list[dict]] = {}
    for item in items:
        key = tuple(item.get(field) for field in fields)
        grouped.setdefault(key, []).append(item)
    return [
        {"key": key, "items": grouped[key], "count": len(grouped[key])}
        for key in sorted(grouped, key=lambda value: tuple(str(part) for part in value))
    ]


def _validate_voc_result(result: dict, records: list[dict]) -> list[str]:
    """Return traceability and output-contract issues for a VOC result."""
    issues: list[str] = []
    required_keys = (
        "voc_schema_version",
        "analyzed_at",
        "requirement_id",
        "records_analyzed",
        "sample_size",
        "min_evidence_met",
        "evidence_counts",
        "top_themes",
        "competitor_signals",
        "decision_signals",
        "insight_candidates",
        "limitations",
    )
    for key in required_keys:
        if key not in result:
            issues.append(f"missing_required_key: {key}")

    counts = result.get("evidence_counts")
    if not isinstance(counts, dict):
        issues.append("invalid_evidence_counts")
    else:
        for key in ("product_evaluation", "comparison", "decision"):
            value = counts.get(key)
            if not isinstance(value, int) or value < 0:
                issues.append(f"invalid_evidence_count: {key}")

    for item in _iter_dicts(result.get("top_themes")):
        _validate_required_shape(item, ("evidence_count", "source_count", "sample_evidence_ids", "sample_spans"), "top_themes", issues)
        _validate_ids(item.get("sample_evidence_ids"), records, issues)
        _validate_spans(item.get("sample_spans"), records, issues)

    for item in _iter_dicts(result.get("competitor_signals")):
        _validate_required_shape(
            item,
            ("compared_product", "comparison_basis", "preferred_option", "direction", "evidence_count", "source_count", "sample_evidence_ids", "sample_spans"),
            "competitor_signals",
            issues,
        )
        _validate_ids(item.get("sample_evidence_ids"), records, issues)
        _validate_spans(item.get("sample_spans"), records, issues)

    for item in _iter_dicts(result.get("decision_signals")):
        _validate_required_shape(item, ("signal_type", "evidence_count", "source_count", "sample_evidence_ids", "sample_spans", "price_point_mentions"), "decision_signals", issues)
        _validate_ids(item.get("sample_evidence_ids"), records, issues)
        _validate_spans(item.get("sample_spans"), records, issues)

    for candidate in _iter_dicts(result.get("insight_candidates")):
        _validate_required_shape(candidate, ("claim", "finding_type", "supporting_evidence_ids", "evidence_count", "source_count", "confidence", "limitations"), "insight_candidates", issues)
        claim = candidate.get("claim")
        if not isinstance(claim, str) or not _claim_is_safe(claim):
            issues.append("unsafe_insight_claim")
        _validate_ids(candidate.get("supporting_evidence_ids"), records, issues)
        _validate_non_negative_int(candidate.get("evidence_count"), "invalid_candidate_evidence_count", issues)
        _validate_non_negative_int(candidate.get("source_count"), "invalid_candidate_source_count", issues)
        confidence = candidate.get("confidence")
        if not isinstance(confidence, dict):
            issues.append("invalid_confidence")
        else:
            for key in ("evidence_count", "source_count", "signal_consistency", "confidence_label"):
                if key not in confidence:
                    issues.append(f"missing_confidence_key: {key}")
        if not candidate.get("supporting_evidence_ids"):
            issues.append("missing_supporting_evidence_ids")

    return issues


def _iter_dicts(value: Any) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _validate_required_shape(item: dict, keys: tuple[str, ...], label: str, issues: list[str]) -> None:
    for key in keys:
        if key not in item:
            issues.append(f"missing_{label}_key: {key}")


def _validate_ids(values: Any, records: list[dict], issues: list[str]) -> None:
    if not isinstance(values, list):
        issues.append("invalid_evidence_id_list")
        return
    for value in values:
        if not _known_evidence_id(str(value), records):
            issues.append(f"unknown_evidence_id: {value}")


def _known_evidence_id(value: str, records: list[dict]) -> bool:
    content_ids = {str(record.get("content_id")) for record in records if record.get("content_id") is not None}
    return value in content_ids


def _validate_spans(values: Any, records: list[dict], issues: list[str]) -> None:
    if not isinstance(values, list):
        issues.append("invalid_sample_span_list")
        return
    source_texts = [_record_source_text(record) for record in records]
    for value in values:
        span = str(value)
        if span and not any(span in source_text for source_text in source_texts):
            issues.append(f"invalid_sample_span: {_shorten(span)}")


def _record_source_text(record: dict) -> str:
    if record.get("source_text") is not None:
        return str(record.get("source_text"))
    if record.get("text") is not None:
        title = str(record.get("title") or "")
        text = str(record.get("text") or "")
        return f"{title}\n\n{text}" if title else text
    return _source_text(record)


def _shorten(value: str, limit: int = 48) -> str:
    collapsed = " ".join(value.split())
    if len(collapsed) <= limit:
        return collapsed
    return f"{collapsed[: limit - 3]}..."


def _validate_non_negative_int(value: Any, issue: str, issues: list[str]) -> None:
    if not isinstance(value, int) or value < 0:
        issues.append(issue)


def _make_candidate(claim: str, category: str, items: list[dict], preliminary: bool = False) -> dict:
    extra_limitations = None
    if preliminary:
        claim = (
            f"{claim} This is a preliminary signal based on a small sample below the "
            f"configured min_evidence_threshold/min_source_threshold."
        )
        extra_limitations = [
            "This insight candidate is below the configured min_evidence_threshold/min_source_threshold "
            "and should be treated as preliminary.",
        ]
    return {
        "claim": claim,
        "finding_type": category,
        "evidence_count": len(items),
        "source_count": _source_count(items),
        "supporting_evidence_ids": _evidence_ids(items),
        "confidence": build_confidence(items),
        "limitations": _limitations(extra_limitations),
        "preliminary": preliminary,
    }


def _meets_threshold(items: list[dict], min_evidence: int, min_sources: int) -> bool:
    return len(items) >= min_evidence and _source_count(items) >= min_sources


def _source_count(items: list[dict]) -> int:
    return len({item.get("source_url") for item in items if item.get("source_url")})


def _evidence_ids(items: list[dict]) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for item in items:
        evidence_id = item.get("evidence_id")
        if not evidence_id:
            continue
        value = str(evidence_id)
        if value in seen:
            continue
        ids.append(value)
        seen.add(value)
    return ids


def _extraction_ids(items: list[dict]) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for item in items:
        extraction_id = item.get("extraction_id")
        if not extraction_id:
            continue
        value = str(extraction_id)
        if value in seen:
            continue
        ids.append(value)
        seen.add(value)
    return ids


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _requirement_id(requirement: dict) -> str:
    if not isinstance(requirement, dict):
        return "unknown"
    return str(requirement.get("requirement_id") or "unknown")


def _claim_is_safe(claim: str) -> bool:
    lowered = claim.lower()
    allowed_prefixes = ("In this sample", "Among the analyzed evidence")
    return claim.startswith(allowed_prefixes) and not any(phrase in lowered for phrase in FORBIDDEN_CLAIM_PHRASES)


def _limitations(extra: list[str] | None = None) -> list[str]:
    limitations = [
        "Rule-based extraction may miss nuanced signals.",
        "Evidence spans reflect exact source text; context may vary.",
        "Sample size may not represent all users.",
        "Confidence is based on evidence count and source diversity, not semantic analysis.",
    ]
    if extra:
        for item in extra:
            if item not in limitations:
                limitations.append(item)
    return limitations
