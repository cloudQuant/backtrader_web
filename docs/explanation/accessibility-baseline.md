# Accessibility (A11y) Baseline — WCAG 2.1 AA

> Iteration 175 §3 — single source of truth for the project's a11y baseline,
> the `Critical_Page_Set` scan results, and any "necessary exemptions" that
> are tolerated under the AA gate.

## Why this exists

A11y compliance is not a one-time fix; the baseline is enforced on every PR by
the `frontend-a11y` CI job. This document explains:

- which pages are scanned;
- the WCAG conformance level (2.1 AA);
- what `critical` and `serious` axe violations get blocked;
- the limited list of exemptions, each with the WCAG clause being deferred
  and the reason.

## Critical Page Set

The 7 pages enumerated in `requirements.md` Requirement 3.1:

| # | Route | View module | Auth required |
|---|---|---|---|
| 1 | `/login`              | `views/auth/Login*` | no |
| 2 | `/dashboard`          | `views/Dashboard*`  | yes |
| 3 | `/ai-chat`            | `views/AIChatPage`  | yes |
| 4 | `/backtests`          | `views/BacktestList*` (or equivalent) | yes |
| 5 | `/backtests/:id`      | `views/BacktestDetail*` | yes |
| 6 | `/knowledge-base`     | `views/KnowledgeBasePage` | yes |
| 7 | `/strategies`         | `views/Strategy*` | yes |

## Conformance level

- WCAG **2.1 Level AA**, scanned with axe-core via `@axe-core/playwright`
  using `.withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])`.
- Lighthouse Accessibility category threshold: `>= 0.9` (90/100). See
  `config/lighthouserc.js`.

## Blocking impact levels

`critical` and `serious` axe violations fail the `frontend-a11y` CI job and
block PR merge. `minor` and `moderate` are surfaced as warnings.

## Hard interaction constraints (Requirement 3.4)

These are baseline expectations every page in the Critical_Page_Set must
already satisfy. Any of the following on a covered page is treated as a
serious violation by axe and will block PR merge:

| # | Constraint | Example fix |
|---|---|---|
| a | Non-decorative `<img>` / icon must have `alt` or `aria-label` | Add `aria-label="刷新数据"` to icon-only refresh button |
| b | All form inputs have explicit `<label>` or `aria-labelledby` | Wrap `<el-input>` with an Element Plus form-item that has a label |
| c | Color contrast ≥ 4.5:1 normal / 3:1 large text & graphics | Use design system colour tokens, see DESIGN_SYSTEM.md |
| d | All interactive elements reachable via Tab / Shift+Tab; focus ring visible | Avoid `outline: none` without a replacement focus indicator |
| e | Modal opens trap focus; close returns focus to invoker | Use Element Plus `<el-dialog>` (handles trap automatically) |

"Non-decorative" is identified as: an image element that does **not** carry
any of `role="presentation"`, `aria-hidden="true"`, or empty `alt=""`.

## Exemptions (necessary)

> Hard cap: ≤ 5 entries (Requirement 3.8). Each entry must reference a WCAG
> clause and be reviewed annually.

| # | Page / Component | WCAG clause | Reason | Owner | Annual review |
|---|---|---|---|---|---|
| _none_ | — | — | At 175 entry, no exemption registered. New entries require an
> RFC and CODEOWNERS approval. | — | — |

## Re-running the baseline locally

```bash
cd src/frontend
npm ci
npm run build
# In one terminal: serve the built dist (or use vite preview)
npx vite preview --port 4173 &
# In another terminal: run a11y suite
BASE_URL=http://localhost:4173 npx playwright test e2e/a11y/
```

## CI integration

- `.github/workflows/ci.yml` `frontend-a11y` job — required, blocks PR.
- `config/lighthouserc.js` `lighthouse-ci` job — required, blocks PR.
- Failed scans upload Playwright trace + axe violation list as artifact
  (7-day retention).
