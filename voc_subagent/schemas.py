"""JSON-serializable schema helpers for the VOC subagent MVP."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class VOCRecord:
    content_id: str
    requirement_id: str | None
    platform: str | None
    source_url: str | None
    title: str | None
    text: str
    created_at: str | None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProductEvaluationEvidence:
    evidence_id: str
    evidence_span: str
    source_url: str | None
    record_id: str
    category: str
    direction: str
    dimension: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ComparisonEvidence:
    evidence_id: str
    evidence_span: str
    source_url: str | None
    record_id: str
    category: str
    signal: str
    preferred_option: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DecisionEvidence:
    evidence_id: str
    evidence_span: str
    source_url: str | None
    record_id: str
    category: str
    signal: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class InsightCandidate:
    claim: str
    finding_type: str
    supporting_evidence_ids: list[str]
    evidence_count: int
    source_count: int
    confidence: str
    limitations: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VOCFindings:
    requirement_id: str | None
    records_analyzed: int
    evidence_counts: dict[str, int]
    top_themes: list[dict[str, Any]]
    competitor_signals: list[dict[str, Any]]
    decision_signals: list[dict[str, Any]]
    insight_candidates: list[dict[str, Any]]
    limitations: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
