# VOC Evidence Subagent

## Purpose

This project provides a callable VOC (Voice of Customer) evidence-analysis subagent. It analyzes already-collected user evidence and returns structured, sample-level VOC findings.

## Public API

```python
from voc_subagent import run_voc_evidence_analysis

result = run_voc_evidence_analysis(
    requirement={...},
    raw_evidence_list=[...],
    config={...},
)
```

## Scope

The subagent does:

- map raw evidence into VOC records;
- extract product evaluation, comparison, and decision signals;
- preserve evidence spans;
- preserve supporting evidence IDs;
- aggregate evidence deterministically;
- generate sample-level insight candidates.

The subagent does not:

- crawl or collect new evidence;
- call external APIs or LLMs;
- read or write databases;
- modify queues or research runs;
- render dashboards;
- make market-level conclusions.

## Input Contract

`requirement` is a dictionary that may include:

- `requirement_id`
- `title`
- `description`

`raw_evidence_list` is a list of dictionaries. Each item may include:

- `evidence_id`
- `title`
- `body`
- `source`
- `source_url`
- `subreddit`
- `score`
- `comment_count`
- `matched_patterns`
- `language`

`config` is an optional dictionary. Supported fields include:

- `target_product`
- `competitor_terms`
- `extraction_mode`
- `max_records`
- `min_evidence_threshold`
- `min_source_threshold`
- `language_filter`
- `evidence_span_strict`

## Output Contract

The returned dictionary includes:

- `voc_schema_version`
- `analyzed_at`
- `requirement_id`
- `records_analyzed`
- `sample_size`
- `min_evidence_met`
- `evidence_counts`
- `top_themes`
- `competitor_signals`
- `decision_signals`
- `insight_candidates`
- `limitations`

## Claim Safety

Findings are sample-level only. Insight claims must start with `In this sample`.

The subagent does not produce market-level claims or representative consumer conclusions. Every insight candidate must include supporting evidence IDs so the output remains traceable to the source evidence.

## Testing

Run the stdlib-only smoke tests with:

```bash
python -m voc_subagent.test_voc
```

## Integration Note

This module is designed to be called by a larger Deep Research workflow after evidence has been collected. Integration, persistence, dashboard display, and queue behavior are owned by the parent workflow.
