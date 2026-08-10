# ADR-011: Asset Research Model Validation

**Status:** Accepted
**Date:** 2026-08-07
**Deciders:** AI for Investor Technical Team

## Context

Iteration 191 defined T2 promotion gates but did not implement the temporal
validation machinery required to prove them.  A model can only be promoted when
its evaluation has purge/embargo, walk-forward, calibration, utility bootstrap,
multiple-comparison control and drift evidence.  Hand-rolling those statistics
would be risky and difficult to audit.

## Decision

Use `purgedcv` as the dev dependency for purge/embargo, walk-forward/CPCV,
Deflated Sharpe and multiple-testing controls.  Wrap it behind
`app.services.asset_research.evaluation`, and require evaluation artifact,
model-card and drift-report hashes in `PromotionEvidenceMetrics` before a scope
can be promoted.

## Consequences

### Positive

- Promotion evidence is reproducible and based on a maintained, open implementation.
- Evaluation logic is separated from orchestration and promotion persistence.
- Missing evaluation artifacts now fail closed at the T2 gate.

### Negative

- Adds `purgedcv`, `pandas` and `scikit-learn` transitively to dev dependencies.
- Existing registry rows with incomplete T2 metrics cannot be promoted until their evidence is complete.

### Neutral

- The repository does not yet persist model-card files; model cards are content-addressed audit payloads.
- Real shadow data must still be accumulated before any asset can satisfy the gate.

