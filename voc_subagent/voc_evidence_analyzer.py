"""Callable VOC evidence-analysis service for the MVP subagent."""

from __future__ import annotations

from typing import Any

from .aggregation import (
    aggregate_comparisons,
    aggregate_decisions,
    aggregate_product_evaluations,
    build_insight_candidates,
)
from .extraction_rules import extract_comparisons, extract_decisions, extract_product_evaluations
from .voc_record_mapper import build_voc_records


LIMITATIONS = [
    "This is a sample-level VOC analysis.",
    "No new crawling was performed.",
    "No LLM extraction was performed in this MVP version.",
    "This output should not be treated as a representative market conclusion.",
]


def run_voc_evidence_analysis(
    requirement: dict,
    raw_evidence_list: list[dict],
    config: dict | None = None,
) -> dict[str, Any]:
    """Run deterministic VOC evidence analysis over existing raw evidence."""
    _ = config
    records = build_voc_records(requirement, raw_evidence_list)
    product_evidence = extract_product_evaluations(records)
    comparison_evidence = extract_comparisons(records)
    decision_evidence = extract_decisions(records)

    top_themes = aggregate_product_evaluations(product_evidence)
    competitor_signals = aggregate_comparisons(comparison_evidence)
    decision_signals = aggregate_decisions(decision_evidence)
    insight_candidates = build_insight_candidates(product_evidence, comparison_evidence, decision_evidence)

    return {
        "requirement_id": requirement.get("requirement_id") or requirement.get("id"),
        "records_analyzed": len(records),
        "evidence_counts": {
            "product_evaluation": len(product_evidence),
            "comparison": len(comparison_evidence),
            "decision": len(decision_evidence),
        },
        "top_themes": top_themes,
        "competitor_signals": competitor_signals,
        "decision_signals": decision_signals,
        "insight_candidates": insight_candidates,
        "limitations": list(LIMITATIONS),
    }
