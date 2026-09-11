# Iteration 197 B2 Family Evidence Implementation Plan

> 执行状态：本计划已在隔离工作树中完成实施和本地候选验证；勾选项仅记录已完成步骤，不要求或调用任何外部工作流技能。

**Goal:** Add an internal, durable B2 completeness-evidence layer that validates the four multi-record family dimension contracts and lets strict local replay prove an expected manifest or a selector/event-bound zero result.

**Architecture:** A versioned family-contract module owns dimension validation and derives semantic record keys from server-controlled dimensions. Immutable completeness receipts and normalized expected-key entries are staged with a linked `MdPublication`, so the reader can require both the source snapshot and the receipt to be visible under its frozen anchor. The four B2 families remain `unconfigured`; this package adds no route, provider, OpenBB/AkShare call, scheduler, capability permit, or frontend path.

**Tech Stack:** Python 3.11, SQLAlchemy 2.0, Alembic, pytest, and SQLite-focused regression with MySQL/PostgreSQL reflection contracts.

**Spec:** `docs/iterations/迭代197-本地优先市场数据中台/REQUIREMENTS.md`, `docs/iterations/迭代197-本地优先市场数据中台/DESIGN.md`, and `docs/iterations/迭代197-本地优先市场数据中台/PRODUCT_EXPANSION_PLAN.md`.

## Global Constraints

- Keep `futures.inventory`, `option.derivative`, `option.risk_surface`, and `crypto.cme_position` at registry status `unconfigured`.
- Do not add an HTTP route, provider adapter, scheduler, page change, capability permit, public grant integration, or network invocation.
- Callers supply dimensions and evidence references; the service derives semantic-key, selector, manifest, and receipt hashes.
- Use append-only ORM models and a separate `MdPublication` receipt for visibility; never use `created_at` as PIT visibility.
- Require `local_only + strict`, one exact event, a frozen visibility anchor, and a nonempty internal verified-source allowlist in the reader.
- Preserve type-sensitive canonical JSON behavior; do not round strikes, coerce case, infer aliases, or convert `true`, `1`, and `1.0` into one dimension value.
- Run Python with `/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python ...`.

---

### Task 1: Versioned B2 Family Dimension Contracts

**Files:**
- Create: `src/backend/app/services/market_data/multi_record_contracts.py`
- Modify: `src/backend/app/services/market_data/store.py`
- Modify: `src/backend/app/services/market_data/dataset_contracts.py`
- Create: `src/backend/tests/market_data_platform/test_multi_record_contracts.py`

**Interfaces:**
- Consumes: `normalize_semantic_record_key()` and `normalize_record_dimensions()` from `multi_record.py`.
- Produces: `get_b2_family_contract(family_id, family_contract_version) -> B2FamilyContract`, `normalize_b2_record_dimensions(...)`, `normalize_b2_selector_dimensions(...)`, and `issue_b2_selector(...)`.
- Produces: a Store pre-write guard that rejects missing, extra, mistyped, or selector-incompatible B2 dimensions before a source receipt or observation is written.

- [x] **Step 1: Write the failing contract tests**

```python
def test_option_contract_requires_exact_record_dimensions() -> None:
    contract = get_b2_family_contract("option.derivative", "market-data-family-v1")
    with pytest.raises(B2FamilyContractError, match="B2_RECORD_DIMENSIONS_INVALID"):
        contract.normalize_record_dimensions(
            {"underlying_canonical_id": "IF", "expiry": "2026-10-30"}
        )


def test_contract_preserves_scalar_types_without_strike_rounding() -> None:
    contract = get_b2_family_contract("option.derivative", "market-data-family-v1")
    assert contract.normalize_record_dimensions(_option_dimensions(strike="100")) != (
        contract.normalize_record_dimensions(_option_dimensions(strike="100.0"))
    )
```

- [x] **Step 2: Run the test and confirm the missing interface fails**

```bash
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python -m pytest -q tests/market_data_platform/test_multi_record_contracts.py -p no:cacheprovider
```

Expected: import or attribute failure for `multi_record_contracts`.

- [x] **Step 3: Implement the registry and Store guard**

```python
@dataclass(frozen=True, slots=True)
class B2FamilyContract:
    family_id: str
    family_contract_version: str
    selector_kind: Literal["slice", "report"]
    record_dimension_fields: tuple[str, ...]
    selector_dimension_fields: frozenset[str]

    def normalize_record_dimensions(self, value: Mapping[str, object]) -> Mapping[str, object]: ...
    def normalize_selector_dimensions(self, value: Mapping[str, object]) -> Mapping[str, object]: ...


def issue_b2_selector(
    *, family_id: str, family_contract_version: str,
    selector_dimensions: Mapping[str, object],
    expected_record_dimensions: Iterable[Mapping[str, object]],
) -> B2SliceSelector | B2ReportSelector: ...
```

Define exact fields: inventory `(report_date, location, warehouse, commodity)`; option derivative `(underlying_canonical_id, contract_canonical_id, expiry, strike, right)`; risk surface `(underlying_canonical_id, expiry, moneyness, model_version)`; CME position `(report_date, reporting_entity, rank, report_type)`. Keep all dataset-contract status values `unconfigured` and align their `dimension_fields`.

- [x] **Step 4: Run focused regression and formatting checks**

```bash
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python -m pytest -q tests/market_data_platform/test_multi_record_contracts.py tests/market_data_platform/test_multi_record_identity.py tests/market_data_platform/test_multi_record_store.py -p no:cacheprovider
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python -m ruff check app/services/market_data/multi_record_contracts.py app/services/market_data/store.py app/services/market_data/dataset_contracts.py tests/market_data_platform/test_multi_record_contracts.py
```

- [x] **Step 5: Commit**

```bash
git add src/backend/app/services/market_data/multi_record_contracts.py src/backend/app/services/market_data/store.py src/backend/app/services/market_data/dataset_contracts.py src/backend/tests/market_data_platform/test_multi_record_contracts.py
git commit -m "feat(market-data): define B2 family dimension contracts"
```

### Task 2: Immutable Completeness Receipt Schema and Publication Type

**Files:**
- Modify: `src/backend/app/models/market_data_platform.py`
- Modify: `src/backend/app/models/__init__.py`
- Modify: `src/backend/app/services/market_data/publication.py`
- Create: `src/backend/alembic/versions/20260911_market_data_b2_completeness_evidence.py`
- Create: `src/backend/tests/market_data_platform/test_multi_record_evidence_migration.py`
- Modify: `src/backend/tests/market_data_platform/test_storage_models.py`

**Interfaces:**
- Consumes: `MdDataSeries`, `MdSourceSnapshot`, `MdPublication`, and `MarketDataPublicationManager`.
- Produces: immutable `MdB2CompletenessReceipt`, `MdB2CompletenessManifestEntry`, and publication type `b2_completeness_receipt`.

- [x] **Step 1: Write failing migration/model tests**

```python
async def test_b2_completeness_receipt_has_normalized_expected_key_entries(session) -> None:
    receipt = MdB2CompletenessReceipt(..., expected_record_count=2)
    session.add_all([receipt, MdB2CompletenessManifestEntry(...), MdB2CompletenessManifestEntry(...)])
    await session.flush()
    with pytest.raises(IntegrityError):
        session.add(MdB2CompletenessManifestEntry(
            receipt_id=receipt.id, semantic_record_key_sha256=key_a,
        ))
        await session.flush()
```

- [x] **Step 2: Run the migration test and confirm it fails**

```bash
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python -m pytest -q tests/market_data_platform/test_multi_record_evidence_migration.py -p no:cacheprovider
```

Expected: missing models, revision, or tables.

- [x] **Step 3: Add immutable normalized evidence tables and safe migration**

```python
class MdB2CompletenessReceipt(Base):
    __tablename__ = "md_b2_completeness_receipts"
    id = Column(String(36), primary_key=True, default=_uuid)
    series_id = Column(String(36), ForeignKey("md_data_series.id", ondelete="RESTRICT"), nullable=False)
    source_snapshot_id = Column(String(36), ForeignKey("md_source_snapshots.id", ondelete="RESTRICT"), nullable=False)
    family_id = Column(String(128), nullable=False)
    family_contract_version = Column(String(64), nullable=False)
    selector_kind = Column(String(16), nullable=False)
    event_at = Column(PITDateTime, nullable=False)
    selector_digest = Column(String(64), nullable=False)
    manifest_sha256 = Column(String(64), nullable=False)
    expected_record_count = Column(Integer, nullable=False)
    zero_record_evidence_sha256 = Column(String(64), nullable=True)
    receipt_sha256 = Column(String(64), nullable=False)

class MdB2CompletenessManifestEntry(Base):
    __tablename__ = "md_b2_completeness_manifest_entries"
    receipt_id = Column(String(36), ForeignKey("md_b2_completeness_receipts.id", ondelete="RESTRICT"), primary_key=True)
    semantic_record_key_sha256 = Column(String(64), primary_key=True)
```

Use named checks for SHA lengths, selector kind, nonnegative count, and exact empty-manifest/zero-evidence state. The migration accepts only an exact startup-created pair, uses an explicit MySQL writer drain, blocks downgrade when either table is populated, and preserves the parent fact tables. Put both models in the immutable ORM listener list. Extend publication recovery to verify a B2 receipt and `receipt_sha256` before sealing it.

- [x] **Step 4: Run focused schema and publication tests**

```bash
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python -m pytest -q tests/market_data_platform/test_multi_record_evidence_migration.py tests/market_data_platform/test_storage_models.py tests/market_data_platform/test_publication.py -p no:cacheprovider
```

- [x] **Step 5: Commit**

```bash
git add src/backend/app/models/market_data_platform.py src/backend/app/models/__init__.py src/backend/app/services/market_data/publication.py src/backend/alembic/versions/20260911_market_data_b2_completeness_evidence.py src/backend/tests/market_data_platform/test_multi_record_evidence_migration.py src/backend/tests/market_data_platform/test_storage_models.py
git commit -m "feat(market-data): persist B2 completeness evidence"
```

### Task 3: Server-Owned Evidence Issuance and PIT Lookup

**Files:**
- Create: `src/backend/app/services/market_data/multi_record_evidence.py`
- Modify: `src/backend/app/services/market_data/store.py`
- Create: `src/backend/tests/market_data_platform/test_multi_record_evidence.py`

**Interfaces:**
- Produces: `B2CompletenessEvidenceIssuer.stage(...) -> StagedB2CompletenessEvidence`.
- Produces: `MarketDataStore.read_b2_completeness_evidence(...) -> DurableB2CompletenessEvidence | None`.
- Produces: a durable selector manifest where every expected digest is derived from validated dimensions instead of trusted caller input.

- [x] **Step 1: Write failing issuer and lookup tests**

```python
async def test_issuer_derives_manifest_hashes_and_stages_a_publication(session) -> None:
    staged = await issuer.stage(_nonempty_option_manifest_request())
    assert staged.selector.expected_record_key_sha256s == frozenset({_derived_key_a, _derived_key_b})
    assert staged.publication.entity_type == "b2_completeness_receipt"

async def test_lookup_requires_both_source_and_receipt_visibility_at_anchor(session) -> None:
    assert await store.read_b2_completeness_evidence(...) is None
```

- [x] **Step 2: Run the test and confirm the API is absent**

```bash
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python -m pytest -q tests/market_data_platform/test_multi_record_evidence.py -p no:cacheprovider
```

Expected: missing issuer or Store read method.

- [x] **Step 3: Implement issuance and read contracts**

```python
@dataclass(frozen=True, slots=True)
class B2CompletenessEvidenceRequest:
    series_id: str
    source_snapshot_id: str
    family_id: str
    family_contract_version: str
    selector_dimensions: Mapping[str, object]
    expected_record_dimensions: tuple[Mapping[str, object], ...]
    event_at: datetime
    zero_record_evidence_sha256: str | None

@dataclass(frozen=True, slots=True)
class DurableB2CompletenessEvidence:
    selector: B2SliceSelector | B2ReportSelector
    source_snapshot_id: str
    zero_record_certificate: ZeroRecordCertificate | None
    receipt_sha256: str
```

Reject duplicate derived keys, zero evidence with expected rows, an empty expected manifest without zero evidence, a nonempty manifest with zero evidence, a mismatched series semantic identity, and a source snapshot that cannot provide immutable evidence. Construct canonical manifest/receipt hashes inside the issuer. Store lookup joins the B2 receipt publication and source snapshot publication, requires matching hashes/entity types, requires both under the frozen `MarketDataVisibilityAnchor`, and returns `None` for pending, unavailable, ambiguous, or structurally invalid evidence.

- [x] **Step 4: Run issuer/Store regression**

```bash
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python -m pytest -q tests/market_data_platform/test_multi_record_evidence.py tests/market_data_platform/test_multi_record_store.py tests/market_data_platform/test_store.py -p no:cacheprovider
```

- [x] **Step 5: Commit**

```bash
git add src/backend/app/services/market_data/multi_record_evidence.py src/backend/app/services/market_data/store.py src/backend/tests/market_data_platform/test_multi_record_evidence.py
git commit -m "feat(market-data): issue B2 manifest evidence internally"
```

### Task 4: Require Durable Evidence in the Strict Local Reader

**Files:**
- Modify: `src/backend/app/services/market_data/multi_record_query_service.py`
- Modify: `src/backend/tests/market_data_platform/test_multi_record_query_service.py`
- Modify: `src/backend/tests/market_data_platform/test_multi_record_completeness.py`

**Interfaces:**
- Consumes: `MarketDataStore.read_b2_completeness_evidence`, `DurableB2CompletenessEvidence`, and existing cursor binding.
- Produces: strict local pages only when a durable receipt matches the caller selector and the receipt’s expected keys exactly match local selected facts.

- [x] **Step 1: Write failing reader tests**

```python
@pytest.mark.asyncio
async def test_reader_returns_no_rows_when_selector_has_no_visible_durable_receipt() -> None:
    execution = await service.execute(request_with_declared_selector)
    assert execution.completeness.reason_codes == ("DURABLE_SELECTOR_EVIDENCE_MISSING",)
    assert execution.observations == ()

@pytest.mark.asyncio
async def test_visible_durable_zero_receipt_allows_only_its_exact_empty_event() -> None:
    execution = await service.execute(empty_selector_request)
    assert execution.completeness.is_complete
    assert execution.observations == ()
```

- [x] **Step 2: Run the reader test and confirm it fails before integration**

```bash
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python -m pytest -q tests/market_data_platform/test_multi_record_query_service.py -p no:cacheprovider
```

Expected: existing reader treats caller-owned selector data as sufficient or Store lacks durable lookup.

- [x] **Step 3: Integrate durable evidence without external capability**

```python
evidence = await self._store.read_b2_completeness_evidence(
    request.context, selector=request.selector, event_at=request.event_at,
    knowledge_cutoff=request.knowledge_cutoff, visibility_anchor=visibility_anchor,
    allowed_source_registry_ids=request.access_binding.allowed_source_registry_ids,
)
if evidence is None:
    return _incomplete_execution(request, visibility_anchor, "DURABLE_SELECTOR_EVIDENCE_MISSING")
if evidence.selector.selector_digest != request.selector.selector_digest:
    return _incomplete_execution(request, visibility_anchor, "DURABLE_SELECTOR_EVIDENCE_MISMATCH")
```

Use the durable selector expected-key set and durable zero certificate in the planner. Filter candidate facts to the receipt’s source snapshot before planning, so independent source receipts cannot be combined to prove a complete slice. Retain exact-event SQL, HMAC cursor binding, source allowlist, local-only mode checks, no-provider boundary, and partial-result suppression.

- [x] **Step 4: Run reader and public-boundary regression**

```bash
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python -m pytest -q tests/market_data_platform/test_multi_record_query_service.py tests/market_data_platform/test_multi_record_completeness.py tests/market_data_platform/test_query_api.py tests/market_data_platform/test_query_resolution.py -p no:cacheprovider
```

- [x] **Step 5: Commit**

```bash
git add src/backend/app/services/market_data/multi_record_query_service.py src/backend/tests/market_data_platform/test_multi_record_query_service.py src/backend/tests/market_data_platform/test_multi_record_completeness.py
git commit -m "feat(market-data): require durable B2 completeness evidence"
```

### Task 5: Candidate Documentation and Verification

**Files:**
- Modify: `docs/iterations/迭代197-本地优先市场数据中台/DESIGN.md`
- Modify: `docs/iterations/迭代197-本地优先市场数据中台/ACCEPTANCE.md`
- Create: `docs/iterations/迭代197-本地优先市场数据中台/evidence/2026-09-11-l197-b2-family-evidence.txt`
- Modify: `docs/superpowers/plans/2026-09-11-iteration-197-b2-family-evidence.md`

**Interfaces:**
- Consumes: verified test, format, Alembic, and diff outcomes from Tasks 1–4.
- Produces: a candidate record that distinguishes local development PASS from real provider, public authorization, MySQL/PostgreSQL, browser/API/database, and production readiness `NOT_RUN / NO-GO`.

- [x] **Step 1: Add an acceptance guard**

```python
def test_b2_families_remain_unconfigured_after_internal_evidence_support() -> None:
    for family_id in B2_FAMILY_IDS:
        assert get_dataset_contract(family_id).status == "unconfigured"
```

- [x] **Step 2: Run the complete backend candidate matrix**

```bash
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python -m pytest -q tests/market_data_platform tests/test_config.py -p no:cacheprovider --tb=short
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python -m ruff check app/models/market_data_platform.py app/models/__init__.py app/services/market_data/multi_record_contracts.py app/services/market_data/multi_record_evidence.py app/services/market_data/multi_record_query_service.py app/services/market_data/publication.py app/services/market_data/store.py app/services/market_data/dataset_contracts.py tests/market_data_platform
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python -m alembic -c alembic.ini heads
git diff --check
```

- [x] **Step 3: Record exact outcomes and remaining boundaries**

The evidence file names the candidate commit, test counts, migration head, and local PASS scope. It retains `NOT_RUN / NO-GO` for real AkShare/OpenBB/provider operation, source-policy/public-grant activation, HTTP/frontend/scheduler work, MySQL/PostgreSQL writer drain/concurrency/scale, and browser/API/database acceptance.

- [x] **Step 4: Self-review plan and document edits**

```bash
bad_patterns='T''BD|TO''DO|implement'' later|fill'' in details|appropriate'' error handling|Write'' tests for the above'
rg -n "$bad_patterns" docs/superpowers/plans/2026-09-11-iteration-197-b2-family-evidence.md
git diff --check
```

Expected: no matches and no whitespace errors.

- [x] **Step 5: Commit**

```bash
git add docs/iterations/迭代197-本地优先市场数据中台/DESIGN.md docs/iterations/迭代197-本地优先市场数据中台/ACCEPTANCE.md docs/iterations/迭代197-本地优先市场数据中台/evidence/2026-09-11-l197-b2-family-evidence.txt docs/superpowers/plans/2026-09-11-iteration-197-b2-family-evidence.md
git commit -m "docs(market-data): record B2 family evidence acceptance"
```

## Self-Review

1. **Spec coverage:** Task 1 covers REQ-197-B2-01; Tasks 2–3 cover durable selector/manifest and zero receipt requirements from REQ-197-B2-03; Task 4 preserves REQ-197-B2-04 strict-local replay while requiring durable evidence; every task preserves REQ-197-B2-05’s no-public-authorization boundary.
2. **Placeholder scan:** The plan has concrete paths, types, failure cases, commands, and commit allowlists. It contains no incomplete task marker.
3. **Type consistency:** `B2FamilyContract` produces selectors used by `B2CompletenessEvidenceIssuer`; `DurableB2CompletenessEvidence` is returned by `MarketDataStore` and consumed by `MultiRecordLocalQueryService`; `MdB2CompletenessReceipt.receipt_sha256` is the `MdPublication.entity_sha256` used by recovery validation.

## Execution Record

用户已授权继续迭代 197 实施；本计划在隔离工作树中执行，并以提交、测试、迁移升级和验收收据作为完成证据。
