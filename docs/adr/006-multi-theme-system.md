# ADR-006: Multi-Theme System with CSS Custom Properties

**Status:** Accepted
**Date:** 2026-05-20
**Deciders:** cloud

## Context

The platform initially supported only a simple light/dark toggle. Users requested more theme options to suit different working environments — professional financial analysis, trading monitoring, and personal preference. The existing theme store already used CSS variables for dark mode, but was limited to two states.

## Decision

Implement a multi-theme system supporting 5 themes (Light, Dark, Blue Professional, Green Trading, Auto/System) using:

1. **CSS Custom Properties** — All theme colors defined as CSS variables on `document.documentElement`
2. **Pinia store with persistence** — Theme preference stored in localStorage via `pinia-plugin-persistedstate`
3. **Element Plus compatibility** — Dark theme adds `.dark` class for Element Plus dark mode; Blue/Green themes use light-mode Element Plus components with custom color overrides
4. **`data-theme` attribute** — Set on `<html>` for CSS selector targeting (`html[data-theme="blue"]`)
5. **ThemeSwitcher dropdown component** — Replaces the simple toggle button in the header

Theme variables are applied at runtime via `document.documentElement.style.setProperty()`, avoiding the need for multiple CSS file imports or build-time theme generation.

## Consequences

### Positive

- Users can choose a theme that suits their workflow (dark for night trading, blue for professional reports, green for market monitoring)
- Zero build-time overhead — themes are pure runtime CSS variable swaps
- Easy to add new themes — just add a new entry to `THEME_VARIABLES` and `THEME_OPTIONS`
- Persisted across sessions via localStorage
- Compatible with Element Plus dark mode system

### Negative

- CSS variable overrides may not cover all third-party component styles (e.g., Monaco Editor, ECharts have their own theming)
- Blue/Green themes don't get full Element Plus component color adaptation (only background/text/border)
- Slightly more complex than a simple dark/light toggle

### Neutral

- Theme store API remains backward-compatible (`toggleTheme()` still works for simple dark/light switching)
- No additional npm dependencies required
