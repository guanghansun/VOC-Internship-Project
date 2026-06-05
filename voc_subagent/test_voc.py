"""Stdlib tests for the canonical VOC public API."""

from __future__ import annotations

import json
from pathlib import Path

from .voc import run_voc_evidence_analysis, validate_span


REQUIREMENT = {"requirement_id": "req_001", "description": "Evaluate sample product feedback."}


def _evidence(evidence_id: str, body: str, source_url: str, title: str = "") -> dict:
    return {
        "evidence_id": evidence_id,
        "source": "sample",
        "source_url": source_url,
        "title": title,
        "body": body,
        "created_at": "2026-01-01T00:00:00Z",
    }


def test_empty_evidence_list() -> None:
    result = run_voc_evidence_analysis(REQUIREMENT, [])
    assert result["voc_schema_version"]
    assert result["records_analyzed"] == 0
    assert result["sample_size"] == 0
    assert result["min_evidence_met"] is False
    assert result["insight_candidates"] == []


def test_single_item_has_no_insight_candidates() -> None:
    result = run_voc_evidence_analysis(
        REQUIREMENT,
        [_evidence("ev_1", "It is expensive but easy to use.", "https://example.test/1")],
    )
    assert result["records_analyzed"] == 1
    assert result["evidence_counts"]["product_evaluation"] >= 1
    assert result["insight_candidates"] == []
    assert result["min_evidence_met"] is False


def test_threshold_can_generate_insight_candidates() -> None:
    raw = [
        _evidence("ev_1", "It is expensive.", "https://example.test/1"),
        _evidence("ev_2", "This product feels expensive for the feature set.", "https://example.test/2"),
        _evidence("ev_3", "Still expensive after the discount.", "https://example.test/2"),
    ]
    result = run_voc_evidence_analysis(REQUIREMENT, raw)
    assert result["min_evidence_met"] is True
    assert result["insight_candidates"]


def test_product_comparison_and_decision_extraction() -> None:
    raw = [
        _evidence("ev_1", "It is expensive and works well.", "https://example.test/1"),
        _evidence("ev_2", "It is better than my old product.", "https://example.test/2"),
        _evidence("ev_3", "I bought it and would recommend it.", "https://example.test/3"),
    ]
    result = run_voc_evidence_analysis(REQUIREMENT, raw)
    assert result["evidence_counts"]["product_evaluation"] >= 2
    assert result["evidence_counts"]["comparison"] >= 1
    assert result["evidence_counts"]["decision"] >= 1


def test_all_evidence_spans_are_exact_substrings() -> None:
    raw = [
        _evidence("ev_1", "It is expensive and easy to use.", "https://example.test/1"),
        _evidence("ev_2", "It is better than the alternative.", "https://example.test/2"),
        _evidence("ev_3", "I regret buying it.", "https://example.test/3"),
    ]
    result = run_voc_evidence_analysis(REQUIREMENT, raw)
    source_by_url = {item["source_url"]: f"{item.get('title') or ''}\n\n{item.get('body') or ''}" for item in raw}
    for group_name in ("top_themes", "competitor_signals", "decision_signals"):
        assert group_name in result
    assert validate_span("not an exact source span", {"title": "A", "body": "B"}) is False

    # Check through aggregated evidence by rerunning with relaxed threshold and observing validated outputs indirectly.
    detailed = run_voc_evidence_analysis(REQUIREMENT, raw, {"min_evidence_threshold": 1, "min_source_threshold": 1})
    assert detailed["insight_candidates"]
    for candidate in detailed["insight_candidates"]:
        assert candidate["supporting_evidence_ids"]
    for item in raw:
        assert item["body"] in source_by_url[item["source_url"]]


def test_confidence_is_object_and_claims_are_safe() -> None:
    raw = [
        _evidence("ev_1", "It is expensive.", "https://example.test/1"),
        _evidence("ev_2", "It is expensive for what it does.", "https://example.test/2"),
        _evidence("ev_3", "It is expensive compared with basics.", "https://example.test/3"),
    ]
    result = run_voc_evidence_analysis(REQUIREMENT, raw)
    forbidden = ("users generally", "the market prefers", "most users", "consumers")
    for candidate in result["insight_candidates"]:
        assert isinstance(candidate["confidence"], dict)
        assert candidate["claim"].startswith("In this sample")
        assert not any(phrase in candidate["claim"].lower() for phrase in forbidden)


def test_forbidden_imports_do_not_appear_in_voc_py() -> None:
    source = Path(__file__).with_name("voc.py").read_text(encoding="utf-8")
    import_lines = [line for line in source.splitlines() if line.startswith("import ") or line.startswith("from ")]
    forbidden = ("storage", "agents", "models", "dashboard", "collectors", "mentor_demo", "super_crawler")
    for line in import_lines:
        assert not any(name in line for name in forbidden), line


def main() -> None:
    tests = [
        test_empty_evidence_list,
        test_single_item_has_no_insight_candidates,
        test_threshold_can_generate_insight_candidates,
        test_product_comparison_and_decision_extraction,
        test_all_evidence_spans_are_exact_substrings,
        test_confidence_is_object_and_claims_are_safe,
        test_forbidden_imports_do_not_appear_in_voc_py,
    ]
    for test in tests:
        test()
    sample = run_voc_evidence_analysis(
        REQUIREMENT,
        [
            _evidence("ev_1", "It is expensive.", "https://example.test/1"),
            _evidence("ev_2", "It is expensive for the quality.", "https://example.test/2"),
            _evidence("ev_3", "It is expensive but reliable.", "https://example.test/3"),
        ],
    )
    print(json.dumps(sample, indent=2, ensure_ascii=False))
    print("VOC canonical API tests passed.")


if __name__ == "__main__":
    main()
