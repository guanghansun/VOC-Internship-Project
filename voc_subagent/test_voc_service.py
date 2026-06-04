"""Stdlib smoke test for the VOC evidence-analysis service."""

from __future__ import annotations

import json

from .sample_data import SAMPLE_RAW_EVIDENCE, SAMPLE_REQUIREMENT
from .voc_evidence_analyzer import run_voc_evidence_analysis


def main() -> None:
    result = run_voc_evidence_analysis(SAMPLE_REQUIREMENT, SAMPLE_RAW_EVIDENCE)
    print(json.dumps(result, indent=2, ensure_ascii=False))

    assert result["records_analyzed"] > 0
    assert result["requirement_id"] == SAMPLE_REQUIREMENT["requirement_id"]
    assert "evidence_counts" in result
    assert result["limitations"]
    for candidate in result.get("insight_candidates", []):
        assert candidate["supporting_evidence_ids"]
        assert candidate["claim"].startswith("In this sample")

    print("VOC service smoke test passed.")


if __name__ == "__main__":
    main()
