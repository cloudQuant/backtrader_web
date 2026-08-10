# ADR-013: LLM Report Citation and Prompt Isolation

**Status:** Accepted
**Date:** 2026-08-07
**Deciders:** AI for Investor Technical Team

## Context

LLM-generated research reports can include plausible but unsupported numbers.
The existing report builder includes evidence IDs, but no deterministic check
prevents an LLM from emitting uncited content, and no budget guard protects
cost/rate-limit failures.

## Decision

Require every public report section to carry a known evidence ID before export
or publication.  LLM output is treated as untrusted until
`CitationVerifier` passes.  Prompt and report generation use `LlmBudgetGuardrails`
with per-task/daily/monthly token and cost limits; fallback reasons map to
controlled metric labels.

## Consequences

### Positive

- Reports without evidence cannot be exported or published.
- LLM cost and rate-limit failures become auditable and bounded.
- Candidate fields cannot leak through the public export path.

### Negative

- Legacy reports without evidence IDs must be repaired or remain export-blocked.
- More validation work is required before arbitrary LLM narrative is allowed.

### Neutral

- Deterministic report rendering remains the supported production path.

