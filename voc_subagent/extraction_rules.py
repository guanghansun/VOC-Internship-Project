"""Deterministic MVP extraction rules for VOC evidence."""

from __future__ import annotations

import re
from typing import Any


PRODUCT_PATTERNS = [
    ("price_and_value", "negative", ["expensive", "overpriced"]),
    ("price_and_value", "positive", ["cheap", "worth it", "good value"]),
    ("usability", "positive", ["easy to use", "convenient"]),
    ("usability", "negative", ["hard to use", "confusing"]),
    ("performance", "positive", ["works well", "reliable"]),
    ("performance", "negative", ["doesn't work", "does not work", "broke", "slow"]),
    ("quality_and_design", "positive", ["durable", "comfortable", "stylish"]),
    ("quality_and_design", "negative", ["flimsy", "uncomfortable", "ugly"]),
]

COMPARISON_PATTERNS = [
    "better than",
    "worse than",
    "compared with",
    "instead of",
    "alternative to",
]

DECISION_PATTERNS = [
    ("bought", "bought"),
    ("returned", "returned"),
    ("considering buying", "considering_purchase"),
    ("would recommend", "recommend"),
    ("would not recommend", "recommend_against"),
    ("regret buying", "regret_purchase"),
]


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [part.strip() for part in parts if part.strip()]


def _find_span(text: str, keyword: str) -> str | None:
    lower_keyword = keyword.lower()
    for sentence in _sentences(text):
        if lower_keyword in sentence.lower():
            return sentence
    if lower_keyword in text.lower():
        match = re.search(re.escape(keyword), text, flags=re.IGNORECASE)
        if match:
            start = max(0, match.start() - 40)
            end = min(len(text), match.end() + 40)
            return text[start:end].strip()
    return None


def _evidence_id(prefix: str, record_id: str, index: int) -> str:
    return f"{prefix}_{record_id}_{index}"


def extract_product_evaluations(records: list[dict]) -> list[dict]:
    evidence: list[dict[str, Any]] = []
    for record in records:
        record_id = record["content_id"]
        text = record.get("text", "")
        local_index = 1
        seen_spans: set[tuple[str, str]] = set()
        for dimension, direction, keywords in PRODUCT_PATTERNS:
            for keyword in keywords:
                span = _find_span(text, keyword)
                if not span:
                    continue
                key = (dimension, span.lower())
                if key in seen_spans:
                    continue
                seen_spans.add(key)
                evidence.append(
                    {
                        "evidence_id": _evidence_id("product", record_id, local_index),
                        "evidence_span": span,
                        "source_url": record.get("source_url"),
                        "record_id": record_id,
                        "category": "product_evaluation",
                        "direction": direction,
                        "dimension": dimension,
                    }
                )
                local_index += 1
    return evidence


def extract_comparisons(records: list[dict]) -> list[dict]:
    evidence: list[dict[str, Any]] = []
    for record in records:
        record_id = record["content_id"]
        text = record.get("text", "")
        local_index = 1
        for keyword in COMPARISON_PATTERNS:
            span = _find_span(text, keyword)
            if not span:
                continue
            evidence.append(
                {
                    "evidence_id": _evidence_id("comparison", record_id, local_index),
                    "evidence_span": span,
                    "source_url": record.get("source_url"),
                    "record_id": record_id,
                    "category": "comparison",
                    "signal": keyword.replace(" ", "_"),
                    "preferred_option": None,
                }
            )
            local_index += 1
    return evidence


def extract_decisions(records: list[dict]) -> list[dict]:
    evidence: list[dict[str, Any]] = []
    for record in records:
        record_id = record["content_id"]
        text = record.get("text", "")
        local_index = 1
        for keyword, signal in DECISION_PATTERNS:
            span = _find_span(text, keyword)
            if not span:
                continue
            evidence.append(
                {
                    "evidence_id": _evidence_id("decision", record_id, local_index),
                    "evidence_span": span,
                    "source_url": record.get("source_url"),
                    "record_id": record_id,
                    "category": "decision",
                    "signal": signal,
                }
            )
            local_index += 1
    return evidence
