"""Stdlib tests for the canonical VOC public API."""

from __future__ import annotations

import json
from pathlib import Path

from .voc import (
    VOCService,
    _build_records,
    _claim_is_safe,
    _validate_voc_result,
    run_voc_evidence_analysis,
    validate_span,
)


REQUIREMENT = {"requirement_id": "req_001", "description": "Evaluate sample product feedback."}


def _evidence(
    evidence_id: str,
    body: str,
    source_url: str,
    title: str = "",
    matched_patterns: list[str] | None = None,
) -> dict:
    return {
        "evidence_id": evidence_id,
        "source": "sample",
        "source_url": source_url,
        "title": title,
        "body": body,
        "matched_patterns": matched_patterns or [],
        "language": "en",
        "created_at": "2026-01-01T00:00:00Z",
    }


def _theme_map(result: dict) -> dict[tuple[str, str], dict]:
    return {(item["dimension"], item["direction"]): item for item in result["top_themes"]}

def _decision_map(result: dict) -> dict[str, dict]:
    return {item["signal_type"]: item for item in result["decision_signals"]}


def _comparison_result_for(body: str, config: dict | None = None) -> dict:
    merged_config = {
        "target_product": "Dyson",
        "competitor_terms": ["Shark", "Revlon"],
        "min_evidence_threshold": 1,
        "min_source_threshold": 1,
    }
    if config:
        merged_config.update(config)
    return run_voc_evidence_analysis(
        REQUIREMENT,
        [_evidence("ev_1", body, "https://example.test/1")],
        merged_config,
    )


def _comparison_map(result: dict) -> dict[tuple[str, str, str, str], dict]:
    return {
        (item["compared_product"], item["comparison_basis"], item["preferred_option"], item["direction"]): item
        for item in result["competitor_signals"]
    }

def _result_for(body: str, matched_patterns: list[str] | None = None) -> dict:
    return run_voc_evidence_analysis(
        REQUIREMENT,
        [_evidence("ev_1", body, "https://example.test/1", matched_patterns=matched_patterns)],
        {"min_evidence_threshold": 1, "min_source_threshold": 1},
    )


def test_empty_evidence_list() -> None:
    result = run_voc_evidence_analysis(REQUIREMENT, [])
    assert result["voc_schema_version"]
    assert result["records_analyzed"] == 0
    assert result["sample_size"] == 0
    assert result["min_evidence_met"] is False
    assert result["insight_candidates"] == []


def test_single_item_has_no_insight_candidates_with_default_thresholds() -> None:
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
    assert result["insight_candidates"][0]["claim"] == (
        "In this sample, 3 of 3 evidence items describe negative signals related to price_value."
    )


def test_min_evidence_met_can_be_true_without_insights() -> None:
    raw = [
        _evidence("ev_1", "Breakfast was included.", "https://example.test/1"),
        _evidence("ev_2", "The packaging arrived yesterday.", "https://example.test/2"),
        _evidence("ev_3", "A receipt was attached.", "https://example.test/3"),
    ]
    result = run_voc_evidence_analysis(REQUIREMENT, raw)
    assert result["sample_size"] == 3
    assert result["min_evidence_met"] is True
    assert result["evidence_counts"]["product_evaluation"] == 0
    assert result["insight_candidates"] == []


def test_min_evidence_met_false_for_one_or_two_records() -> None:
    one = run_voc_evidence_analysis(REQUIREMENT, [_evidence("ev_1", "It is expensive.", "https://example.test/1")])
    two = run_voc_evidence_analysis(
        REQUIREMENT,
        [
            _evidence("ev_1", "It is expensive.", "https://example.test/1"),
            _evidence("ev_2", "It is expensive.", "https://example.test/2"),
        ],
    )
    assert one["min_evidence_met"] is False
    assert two["min_evidence_met"] is False

def test_usability_negative_extraction() -> None:
    themes = _theme_map(_result_for("The setup is frustrating and has too many steps."))
    assert ("usability", "negative") in themes


def test_usability_positive_extraction() -> None:
    themes = _theme_map(_result_for("The product is intuitive and saves time."))
    assert ("usability", "positive") in themes


def test_performance_negative_extraction() -> None:
    themes = _theme_map(_result_for("The app is buggy and slow."))
    assert ("performance", "negative") in themes


def test_performance_positive_extraction() -> None:
    themes = _theme_map(_result_for("It is fast, accurate, and effective."))
    assert ("performance", "positive") in themes


def test_price_value_negative_extraction() -> None:
    themes = _theme_map(_result_for("The subscription is too much and not worth it."))
    assert ("price_value", "negative") in themes


def test_price_value_positive_extraction() -> None:
    themes = _theme_map(_result_for("It is affordable and a good value."))
    assert ("price_value", "positive") in themes


def test_quality_design_extraction() -> None:
    themes = _theme_map(_result_for("The case is flimsy, but the handle is comfortable."))
    assert ("quality_design", "negative") in themes
    assert ("quality_design", "positive") in themes


def test_support_service_extraction() -> None:
    positive = _theme_map(_result_for("Customer service gave responsive support."))
    negative = _theme_map(_result_for("There was a warranty issue and poor customer service."))
    assert ("support_service", "positive") in positive
    assert ("support_service", "negative") in negative


def test_availability_extraction() -> None:
    negative = _theme_map(_result_for("It was out of stock."))
    positive = _theme_map(_result_for("It had fast shipping and quick delivery."))
    assert ("availability", "negative") in negative
    assert ("availability", "positive") in positive


def test_multiple_dimensions_from_one_evidence_item() -> None:
    result = _result_for("It is expensive but easy to use, and it works well.")
    themes = _theme_map(result)
    assert ("price_value", "negative") in themes
    assert ("usability", "positive") in themes
    assert ("performance", "positive") in themes


def test_no_duplicate_evidence_objects_for_same_key() -> None:
    result = _result_for("It is expensive and expensive.")
    theme = _theme_map(result)[("price_value", "negative")]
    assert theme["evidence_count"] == 1
    assert len(theme["sample_evidence_ids"]) == 1


def test_single_word_patterns_avoid_substring_false_positives() -> None:
    result = run_voc_evidence_analysis(
        REQUIREMENT,
        [
            _evidence("ev_1", "Breakfast was included.", "https://example.test/1"),
            _evidence("ev_2", "The manualization process was documented.", "https://example.test/2"),
            _evidence("ev_3", "The cheapened materials were discussed elsewhere.", "https://example.test/3"),
            _evidence("ev_4", "The simplex method was mentioned.", "https://example.test/4"),
        ],
        {"min_evidence_threshold": 1, "min_source_threshold": 1},
    )
    assert result["evidence_counts"]["product_evaluation"] == 0
    assert result["top_themes"] == []


def test_single_word_patterns_still_match_standalone_words() -> None:
    result = run_voc_evidence_analysis(
        REQUIREMENT,
        [
            _evidence("ev_1", "It is fast.", "https://example.test/1"),
            _evidence("ev_2", "This is cheap.", "https://example.test/2"),
            _evidence("ev_3", "The process is too manual.", "https://example.test/3"),
            _evidence("ev_4", "The app is simple.", "https://example.test/4"),
            _evidence("ev_5", "It is available.", "https://example.test/5"),
        ],
        {"min_evidence_threshold": 1, "min_source_threshold": 1},
    )
    themes = _theme_map(result)
    assert ("performance", "positive") in themes
    assert ("price_value", "positive") in themes
    assert ("usability", "negative") in themes
    assert ("usability", "positive") in themes
    assert ("availability", "positive") in themes

def test_manual_rule_avoids_neutral_manual_context() -> None:
    neutral = _theme_map(_result_for("I read the manual."))
    negative = _theme_map(_result_for("The process is too manual."))
    assert ("usability", "negative") not in neutral
    assert ("usability", "negative") in negative

def test_matched_patterns_are_hints_not_filters() -> None:
    complaint = _theme_map(_result_for("It is expensive but easy to use.", ["complaint"]))
    praise = _theme_map(_result_for("It is expensive but easy to use.", ["praise"]))
    missing = _theme_map(_result_for("It is expensive but easy to use."))
    assert ("price_value", "negative") in complaint
    assert ("usability", "positive") in complaint
    assert ("price_value", "negative") in praise
    assert ("usability", "positive") in praise
    assert ("price_value", "negative") in missing
    assert ("usability", "positive") in missing


def test_product_spans_are_exact_substrings_and_limited_to_three_samples() -> None:
    raw = [
        _evidence("ev_1", "It is expensive.", "https://example.test/1"),
        _evidence("ev_2", "It is expensive for the features.", "https://example.test/2"),
        _evidence("ev_3", "It is expensive after discounts.", "https://example.test/3"),
        _evidence("ev_4", "It is expensive in my region.", "https://example.test/4"),
    ]
    result = run_voc_evidence_analysis(REQUIREMENT, raw)
    theme = _theme_map(result)[("price_value", "negative")]
    assert len(theme["sample_spans"]) == 3
    source_text = "\n\n".join(item["body"] for item in raw)
    for span in theme["sample_spans"]:
        assert span in source_text
        assert validate_span(span, {"title": "", "body": source_text}) is True
    assert validate_span("not an exact source span", {"title": "A", "body": "B"}) is False


def test_top_themes_group_by_dimension_and_direction() -> None:
    raw = [
        _evidence("ev_1", "It is expensive.", "https://example.test/1"),
        _evidence("ev_2", "It is cheap.", "https://example.test/2"),
        _evidence("ev_3", "It is expensive again.", "https://example.test/3"),
    ]
    result = run_voc_evidence_analysis(REQUIREMENT, raw, {"min_evidence_threshold": 1, "min_source_threshold": 1})
    themes = _theme_map(result)
    assert themes[("price_value", "negative")]["evidence_count"] == 2
    assert themes[("price_value", "positive")]["evidence_count"] == 1
    for theme in result["top_themes"]:
        assert "theme" in theme
        assert "sample_evidence_ids" in theme
        assert "sample_spans" in theme


def test_comparison_pattern_extraction_and_preference_direction() -> None:
    cases = [
        ("Dyson works better than Shark.", ("Shark", "performance", "target", "target_preferred")),
        ("Dyson works worse than Shark.", ("Shark", "performance", "competitor", "competitor_preferred")),
        ("Dyson is cheaper than Shark.", ("Shark", "price_value", "target", "target_preferred")),
        ("Dyson is more expensive than Shark.", ("Shark", "price_value", "competitor", "competitor_preferred")),
        ("Compared to Shark, Dyson is different.", ("Shark", "general", "unclear", "neutral_or_mixed")),
        ("Dyson vs Shark is a common comparison.", ("Shark", "general", "unclear", "neutral_or_mixed")),
        ("I bought Dyson instead of Shark.", ("Shark", "general", "unclear", "neutral_or_mixed")),
        ("Dyson is an alternative to Shark.", ("Shark", "general", "unclear", "neutral_or_mixed")),
        ("I switched from Shark to Dyson.", ("Shark", "general", "target", "target_preferred")),
        ("I switched from Dyson to Shark.", ("Shark", "general", "competitor", "competitor_preferred")),
        ("I prefer Dyson over Shark.", ("Shark", "general", "target", "target_preferred")),
    ]
    for body, expected in cases:
        result = _comparison_result_for(body)
        assert expected in _comparison_map(result), body


def test_comparison_basis_detection() -> None:
    cases = [
        ("Dyson is cheaper than Shark.", "price_value"),
        ("Dyson works better than Shark.", "performance"),
        ("Dyson is better than Shark for setup and use.", "usability"),
        ("Dyson is better than Shark in quality.", "quality_design"),
        ("Dyson is better than Shark for support service.", "support_service"),
        ("Dyson is better than Shark for shipping delivery.", "availability"),
    ]
    for body, basis in cases:
        result = _comparison_result_for(body)
        assert any(item["comparison_basis"] == basis for item in result["competitor_signals"]), body


def test_competitor_terms_and_unknown_competitor_are_conservative() -> None:
    configured = _comparison_result_for("Dyson is better than Revlon.")
    unknown = _comparison_result_for("Dyson is better than the old one.")
    unclear = _comparison_result_for("Compared to Shark, the setup is different.")
    assert any(item["compared_product"] == "Revlon" for item in configured["competitor_signals"])
    assert any(item["compared_product"] == "unknown" for item in unknown["competitor_signals"])
    assert any(item["preferred_option"] == "unclear" and item["direction"] == "neutral_or_mixed" for item in unclear["competitor_signals"])


def test_comparison_spans_are_exact_substrings_and_deduped() -> None:
    body = "Dyson is better than Shark and Dyson is better than Shark."
    result = _comparison_result_for(body)
    signal = result["competitor_signals"][0]
    assert signal["evidence_count"] == 1
    assert len(signal["sample_spans"]) == 1
    assert signal["sample_spans"][0] in body
    assert validate_span(signal["sample_spans"][0], {"title": "", "body": body}) is True


def test_comparison_aggregation_fields_and_safe_insight_claims() -> None:
    raw = [
        _evidence("ev_1", "Dyson works better than Shark.", "https://example.test/1"),
        _evidence("ev_2", "Dyson works better than Shark for results.", "https://example.test/2"),
        _evidence("ev_3", "Dyson works better than Shark again.", "https://example.test/3"),
    ]
    result = run_voc_evidence_analysis(
        REQUIREMENT,
        raw,
        {"target_product": "Dyson", "competitor_terms": ["Shark"], "min_evidence_threshold": 3, "min_source_threshold": 2},
    )
    signal = result["competitor_signals"][0]
    assert {"compared_product", "comparison_basis", "preferred_option", "direction", "evidence_count", "source_count", "sample_evidence_ids", "sample_spans"}.issubset(signal)
    assert len(signal["sample_spans"]) <= 3
    comparison_candidates = [item for item in result["insight_candidates"] if item["finding_type"] == "comparison"]
    assert comparison_candidates
    assert comparison_candidates[0]["claim"] == "In this sample, 3 of 3 evidence items compare against Shark on performance."
    forbidden = ("users generally", "the market", "consumers", "most users", "people prefer")
    assert not any(term in comparison_candidates[0]["claim"].lower() for term in forbidden)

def test_comparison_and_decision_extraction_still_work() -> None:
    raw = [
        _evidence("ev_1", "It is better than my old product.", "https://example.test/1"),
        _evidence("ev_2", "I bought it and would recommend it.", "https://example.test/2"),
    ]
    result = run_voc_evidence_analysis(REQUIREMENT, raw, {"min_evidence_threshold": 1, "min_source_threshold": 1})
    assert result["evidence_counts"]["comparison"] >= 1
    assert result["evidence_counts"]["decision"] >= 1


def test_intensity_uses_safe_pattern_matching() -> None:
    service = VOCService({"min_evidence_threshold": 1, "min_source_threshold": 1})
    false_positive_records = [
        {"content_id": "ev_1", "source_text": "Tools are included.", "source_url": "https://example.test/1", "matched_patterns": []},
        {"content_id": "ev_2", "source_text": "It has a lovely design and good design.", "source_url": "https://example.test/2", "matched_patterns": []},
        {"content_id": "ev_3", "source_text": "Whenever possible it is effective.", "source_url": "https://example.test/3", "matched_patterns": []},
    ]
    false_positive_evidence = service._extract_product_evaluations(false_positive_records)
    assert false_positive_evidence
    assert all(item["intensity"] != "strong" for item in false_positive_evidence)

    strong_records = [
        {"content_id": "ev_4", "source_text": "It is too expensive.", "source_url": "https://example.test/4", "matched_patterns": []},
        {"content_id": "ev_5", "source_text": "The setup is really frustrating.", "source_url": "https://example.test/5", "matched_patterns": []},
        {"content_id": "ev_6", "source_text": "I love this because it is easy to use.", "source_url": "https://example.test/6", "matched_patterns": []},
    ]
    strong_evidence = service._extract_product_evaluations(strong_records)
    assert strong_evidence
    assert all(item["intensity"] == "strong" for item in strong_evidence)

def test_decision_signal_type_extraction() -> None:
    cases = [
        ("purchase_consideration", "I am considering buying this."),
        ("purchase_barrier", "The price is too high."),
        ("bought", "I bought this last week."),
        ("returned", "I returned it after two days."),
        ("recommending", "I would recommend it."),
        ("not_recommending", "I would not recommend it."),
        ("switching_intent", "I am looking for an alternative."),
        ("renewal_or_subscription", "The subscription fee is too much."),
    ]
    for signal_type, text in cases:
        result = run_voc_evidence_analysis(
            REQUIREMENT,
            [_evidence("ev_1", text, "https://example.test/1")],
            {"min_evidence_threshold": 1, "min_source_threshold": 1},
        )
        assert signal_type in _decision_map(result), signal_type


def test_subscription_service_alone_does_not_create_renewal_signal() -> None:
    result = _result_for("This is a subscription service.")
    assert "renewal_or_subscription" not in _decision_map(result)


def test_subscription_intent_bearing_phrases_create_renewal_signal() -> None:
    fee = _decision_map(_result_for("The subscription fee is too much."))
    cancelled = _decision_map(_result_for("I cancelled subscription because of the monthly fee."))
    assert "renewal_or_subscription" in fee
    assert "renewal_or_subscription" in cancelled

def test_decision_price_point_detection() -> None:
    dollar = _decision_map(_result_for("At $30/month, I can't justify the price."))["purchase_barrier"]
    fee = _decision_map(_result_for("The monthly fee is too much."))["purchase_barrier"]
    no_price = _decision_map(_result_for("I would recommend it."))["recommending"]
    assert dollar["price_point_mentions"] == 1
    assert fee["price_point_mentions"] == 1
    assert no_price["price_point_mentions"] == 0


def test_multiple_decision_signals_from_one_item() -> None:
    result = _result_for("I bought it, but the monthly fee is too much and I might return it.")
    signals = _decision_map(result)
    assert "bought" in signals
    assert "purchase_barrier" in signals
    assert "renewal_or_subscription" in signals


def test_not_recommending_does_not_create_recommending_overlap() -> None:
    result = _result_for("I would not recommend it.")
    signals = _decision_map(result)
    assert "not_recommending" in signals
    assert "recommending" not in signals


def test_negative_recommendation_variants_do_not_create_recommending_overlap() -> None:
    cases = [
        "I don't recommend this.",
        "I do not recommend this.",
    ]
    for body in cases:
        result = _result_for(body)
        signals = _decision_map(result)
        assert "not_recommending" in signals
        assert "recommending" not in signals

def test_decision_spans_are_exact_substrings_and_deduped() -> None:
    result = _result_for("I bought it and I bought it.")
    bought = _decision_map(result)["bought"]
    assert bought["evidence_count"] == 1
    assert len(bought["sample_spans"]) == 1
    assert bought["sample_spans"][0] in "I bought it and I bought it."
    assert validate_span(bought["sample_spans"][0], {"title": "", "body": "I bought it and I bought it."}) is True


def test_decision_aggregation_fields_and_insight_claims() -> None:
    raw = [
        _evidence("ev_1", "I would recommend it.", "https://example.test/1"),
        _evidence("ev_2", "I would recommend it to a friend.", "https://example.test/2"),
        _evidence("ev_3", "I would recommend it again.", "https://example.test/3"),
    ]
    result = run_voc_evidence_analysis(REQUIREMENT, raw)
    recommending = _decision_map(result)["recommending"]
    assert recommending["evidence_count"] == 3
    assert recommending["source_count"] == 3
    assert recommending["sample_evidence_ids"]
    assert len(recommending["sample_spans"]) <= 3
    assert recommending["price_point_mentions"] == 0
    decision_candidates = [item for item in result["insight_candidates"] if item["finding_type"] == "decision"]
    assert decision_candidates
    assert decision_candidates[0]["claim"] == "In this sample, 3 of 3 evidence items show recommending decision signals."
    assert decision_candidates[0]["claim"].startswith(("In this sample", "Among the analyzed evidence"))

def test_confidence_is_object_and_claims_are_safe() -> None:
    raw = [
        _evidence("ev_1", "It is expensive.", "https://example.test/1"),
        _evidence("ev_2", "It is expensive for what it does.", "https://example.test/2"),
        _evidence("ev_3", "It is expensive compared with basics.", "https://example.test/3"),
    ]
    result = run_voc_evidence_analysis(REQUIREMENT, raw)
    forbidden = ("users generally", "the market", "most users", "consumers", "people prefer")
    for phrase in forbidden:
        for candidate in result["insight_candidates"]:
            assert phrase not in candidate["claim"].lower(), candidate["claim"]
    theme = _theme_map(result)[("price_value", "negative")]
    assert "evidence_count" in theme
    assert "confidence" in theme
    assert isinstance(theme["confidence"], dict)
    assert {"evidence_count", "source_count", "signal_consistency", "confidence_label"}.issubset(theme["confidence"])
    assert result["limitations"]


def test_output_contains_all_required_keys() -> None:
    result = run_voc_evidence_analysis(REQUIREMENT, [])
    required_keys = {
        "voc_schema_version", "analyzed_at", "requirement_id",
        "records_analyzed", "sample_size", "min_evidence_met",
        "evidence_counts", "top_themes", "competitor_signals",
        "decision_signals", "insight_candidates", "limitations",
        "validation_issues",
    }
    assert required_keys.issubset(result)
    assert result["voc_schema_version"] == "0.1.0"


def test_claim_safety_accepts_allowed_prefixes_and_rejects_forbidden_phrases() -> None:
    assert _claim_is_safe("In this sample, 3 of 5 items show negative signals related to usability.")
    assert _claim_is_safe("Among the analyzed evidence, 2 of 4 items show positive signals related to performance.")
    assert not _claim_is_safe("Users generally find this product easy to use.")
    assert not _claim_is_safe("In this sample, most users prefer the cheaper option.")
    assert not _claim_is_safe("The market prefers Dyson over Shark.")
    assert not _claim_is_safe("Consumers love this product.")
    assert not _claim_is_safe("People prefer the subscription tier.")


def test_voc_module_has_no_forbidden_imports() -> None:
    source = (Path(__file__).parent / "voc.py").read_text(encoding="utf-8-sig")
    forbidden = ("super_crawler", "storage", "agents", "models", "dashboard", "collectors")
    for module in forbidden:
        assert f"import {module}" not in source and f"from {module}" not in source, (
            f"voc.py must not import {module}"
        )


def test_normal_output_has_no_validation_issues() -> None:
    result = run_voc_evidence_analysis(
        REQUIREMENT,
        [_evidence("ev_1", "It is expensive.", "https://example.test/1")],
        {"min_evidence_threshold": 1, "min_source_threshold": 1},
    )
    assert result["validation_issues"] == []


def test_validate_voc_result_detects_missing_required_keys() -> None:
    records = _build_records(REQUIREMENT, [_evidence("ev_1", "It is expensive.", "https://example.test/1")], {})
    result = run_voc_evidence_analysis(REQUIREMENT, [])
    del result["top_themes"]
    assert "missing_required_key: top_themes" in _validate_voc_result(result, records)


def test_validate_voc_result_detects_unknown_supporting_evidence_ids() -> None:
    records = _build_records(REQUIREMENT, [_evidence("ev_1", "It is expensive.", "https://example.test/1")], {})
    result = run_voc_evidence_analysis(
        REQUIREMENT,
        [_evidence("ev_1", "It is expensive.", "https://example.test/1")],
        {"min_evidence_threshold": 1, "min_source_threshold": 1},
    )
    result["insight_candidates"][0]["supporting_evidence_ids"] = ["ev_missing"]
    assert "unknown_evidence_id: ev_missing" in _validate_voc_result(result, records)


def test_validate_voc_result_detects_invalid_sample_spans() -> None:
    records = _build_records(REQUIREMENT, [_evidence("ev_1", "It is expensive.", "https://example.test/1")], {})
    result = run_voc_evidence_analysis(
        REQUIREMENT,
        [_evidence("ev_1", "It is expensive.", "https://example.test/1")],
        {"min_evidence_threshold": 1, "min_source_threshold": 1},
    )
    result["top_themes"][0]["sample_spans"] = ["not copied from source"]
    assert "invalid_sample_span: not copied from source" in _validate_voc_result(result, records)


def test_validate_voc_result_detects_unsafe_insight_claims() -> None:
    records = _build_records(REQUIREMENT, [_evidence("ev_1", "It is expensive.", "https://example.test/1")], {})
    result = run_voc_evidence_analysis(
        REQUIREMENT,
        [_evidence("ev_1", "It is expensive.", "https://example.test/1")],
        {"min_evidence_threshold": 1, "min_source_threshold": 1},
    )
    result["insight_candidates"][0]["claim"] = "Users generally dislike the price."
    assert "unsafe_insight_claim" in _validate_voc_result(result, records)


def test_validate_voc_result_requires_confidence_object_shape() -> None:
    records = _build_records(REQUIREMENT, [_evidence("ev_1", "It is expensive.", "https://example.test/1")], {})
    result = run_voc_evidence_analysis(
        REQUIREMENT,
        [_evidence("ev_1", "It is expensive.", "https://example.test/1")],
        {"min_evidence_threshold": 1, "min_source_threshold": 1},
    )
    result["insight_candidates"][0]["confidence"] = "high"
    assert "invalid_confidence" in _validate_voc_result(result, records)


def test_error_output_includes_validation_issues() -> None:
    class BadThreshold:
        def __int__(self) -> int:
            raise RuntimeError("bad threshold")

    result = run_voc_evidence_analysis(REQUIREMENT, [], {"min_evidence_threshold": BadThreshold()})
    assert result["validation_issues"] == ["analysis_failed"]


def test_none_raw_evidence_returns_empty_valid_output() -> None:
    result = run_voc_evidence_analysis(REQUIREMENT, None)
    assert result["sample_size"] == 0
    assert result["records_analyzed"] == 0
    assert result["validation_issues"] == []


def test_non_list_raw_evidence_returns_empty_valid_output() -> None:
    result = run_voc_evidence_analysis(REQUIREMENT, {"evidence_id": "ev_1", "body": "It is expensive."})
    assert result["sample_size"] == 0
    assert result["validation_issues"] == []
    assert "Some raw evidence items were ignored because they were empty or invalid." in result["limitations"]


def test_non_dict_raw_evidence_items_are_ignored() -> None:
    result = run_voc_evidence_analysis(REQUIREMENT, ["bad", _evidence("ev_1", "It is expensive.", "https://example.test/1")])
    assert result["sample_size"] == 1
    assert "Some raw evidence items were ignored because they were empty or invalid." in result["limitations"]


def test_missing_evidence_id_uses_id() -> None:
    result = run_voc_evidence_analysis(
        REQUIREMENT,
        [{"id": "source_1", "body": "It is expensive.", "source_url": "https://example.test/1"}],
        {"min_evidence_threshold": 1, "min_source_threshold": 1},
    )
    assert result["top_themes"][0]["sample_evidence_ids"] == ["source_1"]


def test_missing_evidence_id_generates_deterministic_id() -> None:
    result = run_voc_evidence_analysis(
        REQUIREMENT,
        [{"body": "It is expensive.", "source_url": "https://example.test/1"}],
        {"min_evidence_threshold": 1, "min_source_threshold": 1},
    )
    assert result["top_themes"][0]["sample_evidence_ids"] == ["generated_0"]
    assert "Some evidence items were missing evidence_id values; deterministic local IDs were generated." in result["limitations"]


def test_missing_body_uses_text_field() -> None:
    result = run_voc_evidence_analysis(
        REQUIREMENT,
        [{"evidence_id": "ev_1", "text": "It is expensive.", "source_url": "https://example.test/1"}],
        {"min_evidence_threshold": 1, "min_source_threshold": 1},
    )
    assert result["evidence_counts"]["product_evaluation"] == 1
    assert result["validation_issues"] == []


def test_empty_title_body_text_item_is_dropped() -> None:
    result = run_voc_evidence_analysis(REQUIREMENT, [{"evidence_id": "ev_1", "title": " ", "body": " ", "text": " "}])
    assert result["sample_size"] == 0
    assert "Some raw evidence items were ignored because they were empty or invalid." in result["limitations"]


def test_matched_patterns_string_and_invalid_values_are_normalized() -> None:
    string_result = run_voc_evidence_analysis(
        REQUIREMENT,
        [{"evidence_id": "ev_1", "body": "It is expensive but easy to use.", "matched_patterns": "complaint", "source_url": "https://example.test/1"}],
        {"min_evidence_threshold": 1, "min_source_threshold": 1},
    )
    invalid_result = run_voc_evidence_analysis(
        REQUIREMENT,
        [{"evidence_id": "ev_2", "body": "It is expensive.", "matched_patterns": {"bad": True}, "source_url": "https://example.test/2"}],
        {"min_evidence_threshold": 1, "min_source_threshold": 1},
    )
    assert string_result["evidence_counts"]["product_evaluation"] >= 1
    assert invalid_result["evidence_counts"]["product_evaluation"] == 1
    assert invalid_result["validation_issues"] == []


def test_score_and_comment_count_invalid_values_do_not_crash() -> None:
    result = run_voc_evidence_analysis(
        REQUIREMENT,
        [{"evidence_id": "ev_1", "body": "It is expensive.", "score": "bad", "comment_count": object(), "source_url": "https://example.test/1"}],
        {"min_evidence_threshold": 1, "min_source_threshold": 1},
    )
    assert result["sample_size"] == 1
    assert result["validation_issues"] == []


def test_language_filter_filters_records() -> None:
    result = run_voc_evidence_analysis(
        REQUIREMENT,
        [
            {"evidence_id": "ev_1", "body": "It is expensive.", "language": "en", "source_url": "https://example.test/1"},
            {"evidence_id": "ev_2", "body": "It is expensive.", "language": "es", "source_url": "https://example.test/2"},
        ],
        {"language_filter": "en"},
    )
    assert result["sample_size"] == 1
    assert "A language filter was applied before analysis." in result["limitations"]


def test_max_records_limits_analyzed_records() -> None:
    result = run_voc_evidence_analysis(
        REQUIREMENT,
        [
            _evidence("ev_1", "It is expensive.", "https://example.test/1"),
            _evidence("ev_2", "It is expensive.", "https://example.test/2"),
        ],
        {"max_records": 1},
    )
    assert result["sample_size"] == 1
    assert "A max_records limit was applied before analysis." in result["limitations"]


def test_invalid_max_records_is_ignored_safely() -> None:
    result = run_voc_evidence_analysis(
        REQUIREMENT,
        [_evidence("ev_1", "It is expensive.", "https://example.test/1")],
        {"max_records": "bad"},
    )
    assert result["sample_size"] == 1
    assert "A max_records limit was applied before analysis." not in result["limitations"]


def test_invalid_thresholds_fall_back_safely() -> None:
    result = run_voc_evidence_analysis(
        REQUIREMENT,
        [_evidence("ev_1", "It is expensive.", "https://example.test/1")],
        {"min_evidence_threshold": "bad", "min_source_threshold": "bad"},
    )
    assert "error" not in result
    assert result["min_evidence_met"] is False
    assert result["validation_issues"] == []


def test_input_dictionaries_are_not_mutated_by_normalization() -> None:
    raw = {"id": "source_1", "text": "It is expensive.", "matched_patterns": "complaint", "score": "bad"}
    original = dict(raw)
    run_voc_evidence_analysis(REQUIREMENT, [raw], {"min_evidence_threshold": 1, "min_source_threshold": 1})
    assert raw == original


def test_demo_import_does_not_execute_and_exposes_main() -> None:
    from . import demo

    assert callable(demo.main)
    assert demo.DEMO_REQUIREMENT["requirement_id"] == "REQ-DEMO-001"


def test_negated_single_word_keywords_are_not_extracted() -> None:
    # "not expensive" should not produce price_value negative
    themes = _theme_map(_result_for("It is not expensive."))
    assert ("price_value", "negative") not in themes
    # "not cheap" should not produce price_value positive
    themes2 = _theme_map(_result_for("It is not cheap."))
    assert ("price_value", "positive") not in themes2
    # "not simple" should not produce usability positive
    themes3 = _theme_map(_result_for("The process is not simple."))
    assert ("usability", "positive") not in themes3


def test_multi_word_negation_patterns_are_still_matched() -> None:
    # "not worth it" is a first-class keyword — must still match
    themes = _theme_map(_result_for("This is not worth it."))
    assert ("price_value", "negative") in themes
    # "would not recommend" is a first-class DECISION keyword
    result = _result_for("I would not recommend it.")
    assert "not_recommending" in _decision_map(result)


def test_signal_consistency_is_mixed_for_mixed_direction_group() -> None:
    # A span that triggers both positive and negative keywords for the same
    # dimension gets direction="mixed"; confidence should reflect that.
    from voc_subagent.voc import build_confidence
    mixed_items = [
        {"evidence_id": "ev_1", "direction": "mixed", "source_url": "https://a.com"},
        {"evidence_id": "ev_2", "direction": "mixed", "source_url": "https://b.com"},
        {"evidence_id": "ev_3", "direction": "mixed", "source_url": "https://c.com"},
    ]
    conf = build_confidence(mixed_items, group_direction="mixed")
    assert conf["signal_consistency"] == "mixed"

    consistent_items = [
        {"evidence_id": "ev_1", "direction": "negative", "source_url": "https://a.com"},
        {"evidence_id": "ev_2", "direction": "negative", "source_url": "https://b.com"},
    ]
    conf2 = build_confidence(consistent_items, group_direction="negative")
    assert conf2["signal_consistency"] == "consistent"


def _all_ids_are_raw(ids: list[str]) -> bool:
    return not any(value.startswith(("product_", "decision_", "comparison_")) for value in ids)


def test_product_aggregation_uses_original_evidence_ids() -> None:
    result = _result_for("It is expensive and confusing.")
    theme = _theme_map(result)[("price_value", "negative")]
    assert theme["sample_evidence_ids"] == ["ev_1"]
    assert _all_ids_are_raw(theme["sample_evidence_ids"])
    assert theme["sample_extraction_ids"][0].startswith("product_ev_1_")


def test_decision_aggregation_uses_original_evidence_ids() -> None:
    result = _result_for("I bought it.")
    signal = _decision_map(result)["bought"]
    assert signal["sample_evidence_ids"] == ["ev_1"]
    assert _all_ids_are_raw(signal["sample_evidence_ids"])
    assert signal["sample_extraction_ids"][0].startswith("decision_ev_1_")


def test_comparison_aggregation_uses_original_evidence_ids() -> None:
    result = _comparison_result_for("Dyson is better than Shark.")
    signal = next(iter(result["competitor_signals"]))
    assert signal["sample_evidence_ids"] == ["ev_1"]
    assert _all_ids_are_raw(signal["sample_evidence_ids"])
    assert signal["sample_extraction_ids"][0].startswith("comparison_ev_1_")


def test_insight_candidates_use_original_supporting_evidence_ids() -> None:
    result = run_voc_evidence_analysis(
        REQUIREMENT,
        [
            _evidence("ev_1", "It is expensive.", "https://example.test/1"),
            _evidence("ev_2", "This is overpriced.", "https://example.test/2"),
            _evidence("ev_3", "It is too costly.", "https://example.test/3"),
        ],
        {"min_evidence_threshold": 3, "min_source_threshold": 2},
    )
    candidates = [item for item in result["insight_candidates"] if item["finding_type"] == "product_evaluation"]
    assert candidates
    assert candidates[0]["supporting_evidence_ids"] == ["ev_1", "ev_2", "ev_3"]
    assert _all_ids_are_raw(candidates[0]["supporting_evidence_ids"])


def test_validator_rejects_internal_extraction_ids_as_evidence_ids() -> None:
    raw = [_evidence("ev_1", "It is expensive.", "https://example.test/1")]
    result = run_voc_evidence_analysis(REQUIREMENT, raw, {"min_evidence_threshold": 1, "min_source_threshold": 1})
    records = _build_records(REQUIREMENT, raw, {})
    result["top_themes"][0]["sample_evidence_ids"] = ["product_ev_1_1"]
    assert "unknown_evidence_id: product_ev_1_1" in _validate_voc_result(result, records)
    result["top_themes"][0]["sample_evidence_ids"] = ["ev_1"]
    assert "unknown_evidence_id: ev_1" not in _validate_voc_result(result, records)


def test_duplicate_extractions_dedupe_sample_evidence_ids() -> None:
    result = run_voc_evidence_analysis(
        REQUIREMENT,
        [_evidence("ev_1", "It is expensive and overpriced.", "https://example.test/1")],
        {"min_evidence_threshold": 1, "min_source_threshold": 1},
    )
    theme = _theme_map(result)[("price_value", "negative")]
    assert theme["evidence_count"] >= 2
    assert theme["sample_evidence_ids"] == ["ev_1"]
    assert len(theme["sample_extraction_ids"]) >= 2


def test_traceability_keeps_existing_exact_span_validation() -> None:
    result = _result_for("The app is simple and saves time.")
    spans = [span for theme in result["top_themes"] for span in theme["sample_spans"]]
    assert spans
    for span in spans:
        assert span in "The app is simple and saves time."

def main() -> None:
    tests = [
        (name, value)
        for name, value in sorted(globals().items())
        if name.startswith("test_") and callable(value)
    ]
    if not tests:
        print("0/0 tests discovered")
        raise SystemExit(1)

    passed = 0
    failures = []
    for name, test_func in tests:
        try:
            test_func()
        except Exception as exc:  # pragma: no cover - manual runner reporting
            failures.append((name, exc))
        else:
            passed += 1

    total = len(tests)
    if failures:
        print(f"{passed}/{total} tests passed")
        for name, exc in failures:
            print(f"FAILED {name}: {exc!r}")
        raise SystemExit(1)

    print(f"{passed}/{total} tests passed")


if __name__ == "__main__":
    main()
