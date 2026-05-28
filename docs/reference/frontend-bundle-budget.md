# Frontend Bundle Budget

> Iteration 175 §7.6 — single source of truth for the frontend bundle size
> ratchet. Numbers are refreshed on each release; CI uses `scripts/ci/check_bundle_size.sh`
> and `scripts/ci/compare_bundle_size.sh` as the enforcement points.

## Active 175 hard budget

| Indicator | Budget | Enforcement |
|---|---|---|
| `dist/assets/index-*.js` gzip size | **≤ 300 KB (307200 bytes)** | `check_bundle_size.sh` exit 1 |
| `/login` route non-vendor JS request count | **≤ 4 files** | `check_bundle_size.sh` exit 1 |
| Per-PR entry chunk gzip growth vs base | **≤ 10%** | `compare_bundle_size.sh` exit 1 |

## Vendor chunk split (175 §7.1)

`vite.config.ts > rollupOptions.output.manualChunks` partitions the following
sets into dedicated chunks. Each set is mutually exclusive — every dependency
lands in at most one chunk.

| Chunk key | Match prefixes |
|---|---|
| `element-plus`  | `node_modules/element-plus/`, `node_modules/@element-plus/` |
| `vue-router`    | `node_modules/vue-router/` |
| `pinia`         | `node_modules/pinia/` |
| `echarts`       | `node_modules/echarts/`, `node_modules/echarts-gl/`, `node_modules/vue-echarts/`, `node_modules/zrender/` |
| `monaco-editor` | `node_modules/monaco-editor/`, `node_modules/@monaco-editor/` |

## Baseline (175 entry-commit)

> Snapshot date: 2026-05-28
> Git commit (175 entry baseline): `51efc51e`
> Build command: `npm --prefix src/frontend run build`
>
> Numbers below are **placeholders pending a clean build on this machine**.
> When 175 implementation reaches the first green CI run, refresh this table
> with the actual values and re-commit.

| Asset | gzip bytes | gzip KB | Notes |
|---|---:|---:|---|
| `dist/assets/index-*.js` (entry chunk) | _tbd_ | _tbd_ | hard budget = 307200 bytes |
| `dist/assets/element-plus-*.js`        | _tbd_ | _tbd_ | |
| `dist/assets/vue-router-*.js`          | _tbd_ | _tbd_ | |
| `dist/assets/pinia-*.js`               | _tbd_ | _tbd_ | |
| `dist/assets/echarts-*.js`             | _tbd_ | _tbd_ | echarts + zrender + echarts-gl + vue-echarts |
| `dist/assets/monaco-editor-*.js`       | _tbd_ | _tbd_ | + monaco workers (lazy-loaded) |
| `/login` non-vendor JS files           | _tbd_ |  | hard budget = 4 |

## How to refresh the baseline

```bash
npm --prefix src/frontend ci
npm --prefix src/frontend run build
ls -l src/frontend/dist/assets | sort -k5 -nr | head -20

# Per-asset gzip:
for f in src/frontend/dist/assets/*.js; do
  printf '%-60s %d\n' "$(basename "$f")" "$(gzip -c -9 "$f" | wc -c)"
done | column -t

# Login route non-vendor JS count:
node scripts/ci/list_route_assets.mjs /login src/frontend/dist --kind=non-vendor-js | wc -l
```

After the run, replace the `_tbd_` cells, update the snapshot date and commit
SHA, and open a PR titled `docs(175): refresh bundle budget baseline`.

## Adjustment policy (Coverage_Ratchet semantics)

Per Property 5 in `.kiro/specs/iteration-175/design.md`:

- The numeric thresholds in this file may be **lowered** at any time (a
  ratchet — getting smaller is always allowed).
- The thresholds may be **raised only via** explicit owner-approved PR with a
  `<!-- bundle-size-override: <reason> -->` line in the PR body. The CI gate
  (`compare_bundle_size.sh`) will surface the override use in the job summary.
- For 176 and beyond we expect to ratchet `index-*.js` gzip from 300 → 250 KB
  (see `iteration-175 / 175 与 176 的接续`).
