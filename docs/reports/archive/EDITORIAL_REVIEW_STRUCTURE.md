# Editorial Review - Structure

> **✅ 已完成** — 8 条建议中的关键项已执行（CONTRIBUTING 去重、安全增强归类、迭代归档等）。本文档保留作为历史参考。

> Review Type: Structural | Date: 2026-02-24
> Reviewed Documents: INDEX.md, TECHNICAL_DOCS.md, ARCHITECTURE.md, and 8 newly created docs

## Document Summary

- **Purpose:** Provide comprehensive documentation for a quantitative trading platform
- **Audience:** Intermediate developers building/operating the platform
- **Reader type:** Humans (developers)
- **Structure model:** Reference/Database (INDEX.md), Explanation/Conceptual (TECHNICAL_DOCS.md)
- **Current length:** ~4,500 words across 28+ documents (core docs only)

---

## Recommendations

### 1. CONDENSE - TECHNICAL_DOCS.md (709 lines)

**Rationale:** This file duplicates significant content from ARCHITECTURE.md (architecture diagram), DATABASE.md (data models), and API.md (API endpoints). It tries to be a single monolithic document covering everything, which creates maintenance burden and redundancy.

**Impact:** ~200 words could be replaced with cross-references

**Suggested action:**
- Keep §1 (功能概览) and §3 (技术栈) as they're unique
- §2 (目录结构) → Replace with link to `source-tree-analysis.md`
- §4 (数据模型) → Replace with link to `DATABASE.md`
- §5 (API 模块) → Replace with link to `API.md`
- §6 (部署运维) → Replace with link to `DEPLOYMENT.md` + `OPERATIONS.md`

### 2. MERGE - ARCHITECTURE.md + source-tree-analysis.md

**Rationale:** Both documents describe system structure. ARCHITECTURE.md has the architecture diagrams; source-tree-analysis.md has the annotated tree. Together they form a complete picture.

**Impact:** ~50 words (cross-reference savings)

**Suggested action:** Add a "Source Tree" section link in ARCHITECTURE.md pointing to source-tree-analysis.md, or merge source tree into ARCHITECTURE.md as an appendix.

### 3. MOVE - SECURITY_ENHANCEMENTS.md content

**Rationale:** Security enhancement history is changelog-style content buried in the architecture section of INDEX.md. It should be under "项目管理" or merged into CHANGELOG.md.

**Impact:** ~0 words (reorganization only)

**Suggested action:** Move link from "架构文档" section to "项目管理" section in INDEX.md.

### 4. CONDENSE - Iteration notes (15 files, 迭代100-114)

**Rationale:** 15 iteration note files in the docs root create clutter. They're historical records, not active reference docs.

**Impact:** Cleaner docs directory, no content loss

**Suggested action:**
- Create `docs/iterations/` subdirectory
- Move all `迭代*.md` files there
- Create `docs/iterations/README.md` index

### 5. QUESTION - Duplicate E2E test documentation

**Rationale:** E2E testing is documented in 3 places: `TESTING.md` (§3), `E2E_TEST_COVERAGE_ANALYSIS.md`, and `src/frontend/e2e/README.md`. They serve different purposes but overlap on test file listing.

**Suggested action:** Keep all three but ensure TESTING.md references the other two rather than duplicating content. E2E_TEST_COVERAGE_ANALYSIS.md is point-in-time analysis; TESTING.md is evergreen reference; e2e/README.md is developer quick-start.

### 6. PRESERVE - USER_GUIDE.md as separate doc

**Rationale:** USER_GUIDE.md targets end-users, not developers. It should remain separate even though its content overlaps with BACKTEST_GUIDE.md and LIVE_TRADING.md (which are developer-oriented).

**Impact:** ~0 words

**Comprehension note:** End-users need a single entry point without developer-specific details.

### 7. CONDENSE - INDEX.md section headers

**Rationale:** INDEX.md now has 8 sections which is slightly heavy for a navigation page. "质量与测试" and "项目管理" could be merged into "开发指南" and "变更日志" respectively.

**Impact:** ~20 words, simpler navigation

**Suggested action:** Optional — current structure is acceptable. Only merge if user prefers fewer sections.

### 8. MOVE - CONTRIBUTING.md from project root

**Rationale:** CONTRIBUTING.md exists in both project root (`/CONTRIBUTING.md`) and is referenced in docs INDEX. The root-level copy follows GitHub convention (auto-displayed on repo page). The docs link should point to the root copy, not create a duplicate.

**Impact:** Avoids content drift between two copies

---

## Summary

- **Total recommendations:** 8
- **Estimated reduction:** ~270 words (~6% of core docs)
- **Meets length target:** No target specified
- **Comprehension trade-offs:** Recommendation #1 (condensing TECHNICAL_DOCS.md) may reduce its value as a standalone reference. Mitigate by adding clear cross-reference links.

## Priority Actions

| Priority | Action | Effort |
|----------|--------|--------|
| 🔴 High | Move iteration notes to subdirectory | 5 min |
| 🟡 Medium | Condense TECHNICAL_DOCS.md redundancy | 15 min |
| 🟡 Medium | Fix CONTRIBUTING.md reference | 2 min |
| 🟢 Low | Merge INDEX.md sections | 5 min |
