# ADR-012: Market Data License Registry

**Status:** Accepted
**Date:** 2026-08-07
**Deciders:** AI for Investor Technical Team

## Context

The multi-asset research framework must not treat a source capability as a
license to cache, export, redistribute or derive from market data.  The existing
`asset_data_source_registry` has license fields but no import or provider
contract to enforce them consistently across collection, report generation,
export and retention.

## Decision

Adopt an ODRL-inspired registry model.  Every provider declares source ID,
allowed hosts, network policy and capability.  Approved manifests are imported
only through `ApprovedManifestImporter` with evidence URI/hash.  License checks
run before collection, before public report generation, before export and before
retention tombstone actions.

## Consequences

### Positive

- Real provider onboarding becomes an auditable import instead of ad hoc DB writes.
- Network controls and license fields are validated in one place.
- Dry-run imports prevent operators from bypassing evidence requirements.

### Negative

- Importing real provider data still requires approved source manifests and evidence.
- Provider-specific adapters are not yet implemented for all six asset classes.

### Neutral

- The registry schema remains unchanged; the enforcement boundary is in services.

