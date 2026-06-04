"""Deterministic aggregation for VOC evidence objects."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def _confidence(evidence_count: int, source_count: int) -> str:
    if evidence_count > 5 and source_count > 1:
        return "high"
    if 3 <= evidence_count <= 5:
        return "medium"
    return "low"


def _source_count(items: list[dict]) -> int:
    return len({item.get("source_url") or item.get("record_id") for item in items})


def aggregate_product_evaluations(product_evidence: list[dict]) -> list[dict]:
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for item in product_evidence:
        groups[(item.get("dimension", "unknown"), item.get("direction", "unknown"))].append(item)
    return [
        {
            "dimension": dimension,
            "direction": direction,
            "evidence_count": len(items),
            "source_count": _source_count(items),
            "supporting_evidence_ids": [item["evidence_id"] for item in items],
        }
        for (dimension, direction), items in sorted(groups.items())
    ]


def aggregate_comparisons(comparison_evidence: list[dict]) -> list[dict]:
    groups: dict[tuple[str, str | None], list[dict]] = defaultdict(list)
    for item in comparison_evidence:
        groups[(item.get("signal", "unknown"), item.get("preferred_option"))].append(item)
    return [
        {
            "signal": signal,
            "preferred_option": preferred_option,
            "evidence_count": len(items),
            "source_count": _source_count(items),
            "supporting_evidence_ids": [item["evidence_id"] for item in items],
        }
        for (signal, preferred_option), items in sorted(groups.items(), key=lambda pair: str(pair[0]))
    ]


def aggregate_decisions(decision_evidence: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for item in decision_evidence:
        groups[item.get("signal", "unknown")].append(item)
    return [
        {
            "signal": signal,
            "evidence_count": len(items),
            "source_count": _source_count(items),
            "supporting_evidence_ids": [item["evidence_id"] for item in items],
        }
        for signal, items in sorted(groups.items())
    ]


def _candidate(claim: str, finding_type: str, items: list[dict]) -> dict[str, Any]:
    evidence_count = len(items)
    source_count = _source_count(items)
    return {
        "claim": claim,
        "finding_type": finding_type,
        "supporting_evidence_ids": [item["evidence_id"] for item in items],
        "evidence_count": evidence_count,
        "source_count": source_count,
        "confidence": _confidence(evidence_count, source_count),
        "limitations": [
            "This is based only on the analyzed sample.",
            "This should not be treated as a representative market conclusion.",
        ],
    }


def build_insight_candidates(
    product_evidence: list[dict], comparison_evidence: list[dict], decision_evidence: list[dict]
) -> list[dict]:
    candidates: list[dict[str, Any]] = []

    product_groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for item in product_evidence:
        product_groups[(item.get("dimension", "unknown"), item.get("direction", "unknown"))].append(item)
    for (dimension, direction), items in sorted(product_groups.items()):
        candidates.append(
            _candidate(
                f"In this sample, {len(items)} evidence item(s) mention {direction} {dimension} feedback.",
                "product_evaluation",
                items,
            )
        )

    comparison_groups: dict[str, list[dict]] = defaultdict(list)
    for item in comparison_evidence:
        comparison_groups[item.get("signal", "unknown")].append(item)
    for signal, items in sorted(comparison_groups.items()):
        candidates.append(
            _candidate(
                f"In this sample, {len(items)} evidence item(s) include {signal.replace('_', ' ')} comparison language.",
                "comparison",
                items,
            )
        )

    decision_groups: dict[str, list[dict]] = defaultdict(list)
    for item in decision_evidence:
        decision_groups[item.get("signal", "unknown")].append(item)
    for signal, items in sorted(decision_groups.items()):
        candidates.append(
            _candidate(
                f"In this sample, {len(items)} evidence item(s) include {signal.replace('_', ' ')} decision language.",
                "decision",
                items,
            )
        )

    return candidates
