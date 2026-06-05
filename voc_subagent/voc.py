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
    "the market prefers",
    "most users",
    "consumers",
)

DEFAULT_CONFIG = {
    "min_evidence_threshold": 3,
    "min_source_threshold": 2,
    "evidence_span_strict": True,
    "extraction_mode": "rule_based",
}

PRODUCT_RULES = [
    ("price_and_value", "negative", ("expensive", "overpriced")),
    ("price_and_value", "positive", ("cheap", "worth it", "good value")),
    ("usability", "positive", ("easy to use", "convenient")),
    ("usability", "negative", ("hard to use", "confusing")),
    ("performance", "positive", ("works well", "reliable")),
    ("performance", "negative", ("doesn't work", "does not work", "broke", "slow")),
    ("quality_and_design", "positive", ("durable", "comfortable", "stylish")),
    ("quality_and_design", "negative", ("flimsy", "uncomfortable", "ugly")),
]

COMPARISON_RULES = (
    "better than",
    "worse than",
    "compared with",
    "instead of",
    "alternative to",
)

DECISION_RULES = [
    ("would not recommend", "recommend_against"),
    ("would recommend", "recommend"),
    ("considering buying", "considering_purchase"),
    ("regret buying", "regret_purchase"),
    ("returned", "returned"),
    ("bought", "bought"),
]


@dataclass
class _ProductEvaluationEvidence:
    evidence_id: str
    evidence_span: str
    span_validated: bool
    extraction_method: str
    content_id: str
    source_url: str | None
    category: str
    dimension: str
    direction: str


@dataclass
class _ComparisonEvidence:
    evidence_id: str
    evidence_span: str
    span_validated: bool
    extraction_method: str
    content_id: str
    source_url: str | None
    category: str
    signal: str
    preferred_option: str | None


@dataclass
class _DecisionEvidence:
    evidence_id: str
    evidence_span: str
    span_validated: bool
    extraction_method: str
    content_id: str
    source_url: str | None
    category: str
    signal: str


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
        }


class VOCService:
    """Small deterministic VOC evidence-analysis service."""

    def __init__(self, config: dict | None = None) -> None:
        merged = dict(DEFAULT_CONFIG)
        if config:
            merged.update(config)
        self.config = merged

    def analyze(self, requirement: dict, raw_evidence_list: list[dict]) -> dict[str, Any]:
        records = _build_records(requirement, raw_evidence_list)
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
        )

        return {
            "voc_schema_version": VOC_SCHEMA_VERSION,
            "analyzed_at": _now_iso(),
            "requirement_id": _requirement_id(requirement),
            "records_analyzed": len(records),
            "sample_size": len(records),
            "min_evidence_met": bool(insight_candidates),
            "evidence_counts": {
                "product_evaluation": len(product_evidence),
                "comparison": len(comparison_evidence),
                "decision": len(decision_evidence),
            },
            "top_themes": top_themes,
            "competitor_signals": competitor_signals,
            "decision_signals": decision_signals,
            "insight_candidates": insight_candidates,
            "limitations": _limitations(),
        }

    def _extract_product_evaluations(self, records: list[dict]) -> list[dict]:
        evidence: list[dict] = []
        for record in records:
            local_index = 1
            seen: set[tuple[str, str, str]] = set()
            for dimension, direction, keywords in PRODUCT_RULES:
                for keyword in keywords:
                    span = _find_span(record["source_text"], keyword)
                    if not span or not validate_span(span, record):
                        continue
                    dedupe_key = (dimension, direction, span.lower())
                    if dedupe_key in seen:
                        continue
                    seen.add(dedupe_key)
                    item = _ProductEvaluationEvidence(
                        evidence_id=f"product_{record['content_id']}_{local_index}",
                        evidence_span=span,
                        span_validated=True,
                        extraction_method="rule_based",
                        content_id=record["content_id"],
                        source_url=record.get("source_url"),
                        category="product_evaluation",
                        dimension=dimension,
                        direction=direction,
                    )
                    evidence.append(asdict(item))
                    local_index += 1
        return evidence

    def _extract_comparisons(self, records: list[dict]) -> list[dict]:
        evidence: list[dict] = []
        for record in records:
            local_index = 1
            for keyword in COMPARISON_RULES:
                span = _find_span(record["source_text"], keyword)
                if not span or not validate_span(span, record):
                    continue
                item = _ComparisonEvidence(
                    evidence_id=f"comparison_{record['content_id']}_{local_index}",
                    evidence_span=span,
                    span_validated=True,
                    extraction_method="rule_based",
                    content_id=record["content_id"],
                    source_url=record.get("source_url"),
                    category="comparison",
                    signal=keyword.replace(" ", "_"),
                    preferred_option=None,
                )
                evidence.append(asdict(item))
                local_index += 1
        return evidence

    def _extract_decisions(self, records: list[dict]) -> list[dict]:
        evidence: list[dict] = []
        for record in records:
            local_index = 1
            for keyword, signal in DECISION_RULES:
                span = _find_span(record["source_text"], keyword)
                if not span or not validate_span(span, record):
                    continue
                item = _DecisionEvidence(
                    evidence_id=f"decision_{record['content_id']}_{local_index}",
                    evidence_span=span,
                    span_validated=True,
                    extraction_method="rule_based",
                    content_id=record["content_id"],
                    source_url=record.get("source_url"),
                    category="decision",
                    signal=signal,
                )
                evidence.append(asdict(item))
                local_index += 1
        return evidence

    def _build_insight_candidates(
        self,
        product_evidence: list[dict],
        comparison_evidence: list[dict],
        decision_evidence: list[dict],
    ) -> list[dict]:
        candidates: list[dict] = []
        min_evidence = int(self.config["min_evidence_threshold"])
        min_sources = int(self.config["min_source_threshold"])

        for group in _group_items(product_evidence, ("dimension", "direction")):
            if not _meets_threshold(group["items"], min_evidence, min_sources):
                continue
            dimension, direction = group["key"]
            claim = f"In this sample, {group['count']} evidence item(s) mention {direction} {dimension} feedback."
            candidates.append(_make_candidate(claim, "product_evaluation", group["items"]))

        for group in _group_items(comparison_evidence, ("signal",)):
            if not _meets_threshold(group["items"], min_evidence, min_sources):
                continue
            signal = group["key"][0]
            claim = f"In this sample, {group['count']} evidence item(s) include {signal.replace('_', ' ')} comparison language."
            candidates.append(_make_candidate(claim, "comparison", group["items"]))

        for group in _group_items(decision_evidence, ("signal",)):
            if not _meets_threshold(group["items"], min_evidence, min_sources):
                continue
            signal = group["key"][0]
            claim = f"In this sample, {group['count']} evidence item(s) include {signal.replace('_', ' ')} decision language."
            candidates.append(_make_candidate(claim, "decision", group["items"]))

        return [candidate for candidate in candidates if _claim_is_safe(candidate["claim"])]


def validate_span(span: str, item: dict) -> bool:
    """Return True only when span is an exact substring of title + body."""
    if not span:
        return False
    source_text = item.get("source_text")
    if source_text is None:
        source_text = _source_text(item)
    return span in source_text


def build_confidence(items_or_count: list[dict] | int, source_count: int | None = None) -> dict[str, Any]:
    """Build a small confidence object for a group of evidence."""
    if isinstance(items_or_count, list):
        items = items_or_count
        evidence_count = len(items)
        actual_source_count = _source_count(items)
        directions = {item.get("direction") for item in items if item.get("direction")}
    else:
        evidence_count = items_or_count
        actual_source_count = int(source_count or 0)
        directions = set()

    if len(directions) <= 1:
        signal_consistency = "consistent"
    elif "positive" in directions and "negative" in directions:
        signal_consistency = "mixed"
    else:
        signal_consistency = "contradicted"

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


def _build_records(requirement: dict, raw_evidence_list: list[dict]) -> list[dict]:
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
        if keyword_lower in sentence.lower():
            return sentence
    return None


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [part.strip() for part in parts if part.strip()]


def _aggregate_product_evaluations(product_evidence: list[dict]) -> list[dict]:
    results: list[dict] = []
    for group in _group_items(product_evidence, ("dimension", "direction")):
        dimension, direction = group["key"]
        results.append(
            {
                "dimension": dimension,
                "direction": direction,
                "evidence_count": group["count"],
                "source_count": _source_count(group["items"]),
                "supporting_evidence_ids": _evidence_ids(group["items"]),
            }
        )
    return results


def _aggregate_comparisons(comparison_evidence: list[dict]) -> list[dict]:
    results: list[dict] = []
    for group in _group_items(comparison_evidence, ("signal", "preferred_option")):
        signal, preferred_option = group["key"]
        results.append(
            {
                "signal": signal,
                "preferred_option": preferred_option,
                "evidence_count": group["count"],
                "source_count": _source_count(group["items"]),
                "supporting_evidence_ids": _evidence_ids(group["items"]),
            }
        )
    return results


def _aggregate_decisions(decision_evidence: list[dict]) -> list[dict]:
    results: list[dict] = []
    for group in _group_items(decision_evidence, ("signal",)):
        results.append(
            {
                "signal": group["key"][0],
                "evidence_count": group["count"],
                "source_count": _source_count(group["items"]),
                "supporting_evidence_ids": _evidence_ids(group["items"]),
            }
        )
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


def _make_candidate(claim: str, finding_type: str, items: list[dict]) -> dict[str, Any]:
    return {
        "claim": claim,
        "finding_type": finding_type,
        "supporting_evidence_ids": _evidence_ids(items),
        "evidence_count": len(items),
        "source_count": _source_count(items),
        "confidence": build_confidence(items),
        "limitations": _limitations(),
    }


def _meets_threshold(items: list[dict], min_evidence: int, min_sources: int) -> bool:
    return len(items) >= min_evidence and _source_count(items) >= min_sources


def _source_count(items: list[dict]) -> int:
    return len({item.get("source_url") or item.get("content_id") for item in items})


def _evidence_ids(items: list[dict]) -> list[str]:
    return [item["evidence_id"] for item in items]


def _claim_is_safe(claim: str) -> bool:
    lowered = claim.lower()
    return claim.startswith("In this sample") and not any(phrase in lowered for phrase in FORBIDDEN_CLAIM_PHRASES)


def _requirement_id(requirement: dict | None) -> str | None:
    if not requirement:
        return None
    value = requirement.get("requirement_id") or requirement.get("id")
    return str(value) if value is not None else None


def _limitations() -> list[str]:
    return [
        "This is a sample-level VOC analysis.",
        "No new crawling was performed.",
        "No LLM extraction was performed in this MVP version.",
        "This output should not be treated as a representative market conclusion.",
    ]


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
