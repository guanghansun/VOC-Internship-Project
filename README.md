# VOC Subagent

This project implements a VOC (Voice of Customer) evidence-analysis subagent.

The subagent is designed to convert raw user evidence into structured VOC records, extract product evaluation, comparison, and decision signals, and preserve traceability from every extracted signal back to its supporting source text.

## Purpose

The project focuses on sample-level VOC evidence analysis. It helps organize what users say in a collected evidence sample without claiming that the sample represents the broader market.

## Core Capabilities

- Convert raw user evidence into normalized VOC records.
- Extract product evaluation evidence such as usability, performance, quality, fit, and price/value signals.
- Extract comparison evidence when users explicitly compare products or alternatives.
- Extract decision evidence such as purchase barriers, return intent, recommendation signals, or switching signals.
- Preserve evidence spans so each structured signal remains auditable.
- Produce sample-level findings with explicit limitations.

## Scope Boundaries

This project does not make market-level claims such as what consumers generally prefer or what the whole market believes. Findings should be framed as evidence observed within the analyzed sample only.

The project also does not include new crawling, large-scale collection, production analytics, or final product insight report generation in its current form.

## Safety Rules

Do not commit environment files, databases, logs, raw responses, prompt examples, local outputs, backups, or other internal working files.
