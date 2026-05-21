# ADR-007: Responsive Mobile Layout with Drawer Navigation

**Status:** Accepted
**Date:** 2026-05-20
**Deciders:** cloud

## Context

The platform's AppLayout used a fixed 220px sidebar that was not usable on mobile devices (< 768px screens). Mobile users couldn't access navigation or had to scroll horizontally. The platform needed to support tablet and phone access for monitoring trading positions on the go.

## Decision

Implement a responsive layout strategy:

1. **Desktop (> 768px):** Keep the existing fixed sidebar layout unchanged
2. **Mobile (< 768px):** Hide the desktop sidebar, show a hamburger button in the header, and use Element Plus `el-drawer` as an overlay navigation panel
3. **Breakpoint detection:** Use `window.innerWidth` with a resize listener (not CSS-only) to manage the `mobileMenuOpen` state and auto-close the drawer when resizing to desktop
4. **CSS approach:** Use SCSS mixins (`@include respond-to('sm')`) in `mobile.scss` for responsive style overrides
5. **Header simplification on mobile:** Hide non-essential elements (page-header-actions, username text, portfolio toggle) to save horizontal space

The drawer approach was chosen over:
- CSS-only sidebar collapse (doesn't work well with Element Plus menu)
- Bottom tab navigation (too many menu items for a tab bar)
- Responsive grid sidebar (would require major layout restructuring)

## Consequences

### Positive

- Mobile users can access all navigation items via the drawer
- Desktop layout is completely unchanged — zero regression risk
- Drawer overlays content instead of pushing it, preserving content width
- Auto-closes when resizing to desktop (no stale state)
- Uses existing Element Plus `el-drawer` component — no new dependencies

### Negative

- Duplicated menu items (desktop sidebar + mobile drawer) — must keep in sync
- Mobile users lose quick access to page-header-actions (hidden on small screens)
- No bottom tab bar for quick navigation between frequent pages

### Neutral

- The `isMobile` state is reactive but not exposed to other components (local to AppLayout)
- Future enhancement: could add a bottom tab bar for the 4-5 most used pages
