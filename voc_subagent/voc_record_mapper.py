"""Map raw evidence dictionaries into normalized VOC records."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def combine_title_and_body(raw_evidence: dict) -> str:
    """Merge title and body text without mutating the source evidence."""
    title = _clean_text(raw_evidence.get("title"))
    body = _clean_text(raw_evidence.get("body"))
    if title and body:
        if body.lower().startswith(title.lower()):
            return body
        return f"{title}\n\n{body}"
    return title or body


def build_voc_records(requirement: dict, raw_evidence_list: list[dict]) -> list[dict]:
    """Build normalized VOC records from RawEvidence-like dictionaries."""
    requirement_id = requirement.get("requirement_id") or requirement.get("id")
    records: list[dict] = []

    for index, raw in enumerate(raw_evidence_list):
        raw_copy = deepcopy(raw)
        text = combine_title_and_body(raw_copy)
        if not text.strip():
            continue

        content_id = raw_copy.get("evidence_id") or raw_copy.get("id") or f"raw_evidence_{index + 1}"
        metadata = {
            "subreddit": raw_copy.get("subreddit"),
            "post_id": raw_copy.get("post_id"),
            "comment_id": raw_copy.get("comment_id"),
            "fetched_at": raw_copy.get("fetched_at"),
            "matched_patterns": deepcopy(raw_copy.get("matched_patterns")),
            "raw_payload": deepcopy(raw_copy.get("raw_payload")),
            "task_group_id": raw_copy.get("task_group_id"),
            "task_group_run_id": raw_copy.get("task_group_run_id"),
        }

        records.append(
            {
                "content_id": str(content_id),
                "requirement_id": requirement_id,
                "platform": raw_copy.get("source"),
                "source_url": raw_copy.get("source_url"),
                "title": raw_copy.get("title"),
                "text": text,
                "created_at": raw_copy.get("created_at"),
                "metadata": metadata,
            }
        )

    return records
