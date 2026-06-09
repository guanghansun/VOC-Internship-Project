"""Runnable fake-data demo for the VOC Evidence Subagent."""

from __future__ import annotations

import json

from voc_subagent import run_voc_evidence_analysis


DEMO_REQUIREMENT = {
    "requirement_id": "REQ-DEMO-001",
    "title": "Pet medication tracking app",
    "description": "Users need an easier way to track recurring pet medication schedules.",
}

DEMO_RAW_EVIDENCE = [
    {
        "evidence_id": "demo_ev_001",
        "source": "forum",
        "source_url": "https://example.test/forum/1",
        "title": "Tracking pet medication",
        "body": "The spreadsheet method is too manual and confusing. This app is easier than a spreadsheet.",
        "language": "en",
    },
    {
        "evidence_id": "demo_ev_002",
        "source": "review",
        "source_url": "https://example.test/review/2",
        "title": "Daily routine",
        "body": "The app is simple and saves time. I bought the app last month.",
        "language": "en",
    },
    {
        "evidence_id": "demo_ev_003",
        "source": "forum",
        "source_url": "https://example.test/forum/3",
        "title": "Subscription concern",
        "body": "The monthly fee is too much. I would pay for this, but not $30/month.",
        "language": "en",
    },
    {
        "evidence_id": "demo_ev_004",
        "source": "review",
        "source_url": "https://example.test/review/4",
        "title": "Recommendation",
        "body": "I do not recommend it because the subscription fee is too much.",
        "language": "en",
    },
    {
        "evidence_id": "demo_ev_005",
        "source": "forum",
        "source_url": "https://example.test/forum/5",
        "title": "Switching tools",
        "body": "I switched from a spreadsheet to this app. Spreadsheets are cheaper than the app but too manual.",
        "language": "en",
    },
    {
        "evidence_id": "demo_ev_006",
        "source": "comment",
        "source_url": "https://example.test/comment/6",
        "title": "Setup comparison",
        "body": "Compared to Notion, this is faster to set up.",
        "language": "en",
    },
]

DEMO_CONFIG = {
    "target_product": "Pet medication tracking app",
    "competitor_terms": ["spreadsheet", "Notion"],
    "min_evidence_threshold": 3,
    "min_source_threshold": 2,
}


def main() -> None:
    result = run_voc_evidence_analysis(DEMO_REQUIREMENT, DEMO_RAW_EVIDENCE, DEMO_CONFIG)

    print("VOC Evidence Subagent Demo")
    print("===========================")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print()
    print("Summary")
    print("-------")
    print(f"records_analyzed: {result['records_analyzed']}")
    print(f"evidence_counts: {result['evidence_counts']}")
    print(f"top_themes: {len(result['top_themes'])}")
    print(f"decision_signals: {len(result['decision_signals'])}")
    print(f"competitor_signals: {len(result['competitor_signals'])}")
    print(f"insight_candidates: {len(result['insight_candidates'])}")
    print(f"validation_issues: {result['validation_issues']}")


if __name__ == "__main__":
    main()
