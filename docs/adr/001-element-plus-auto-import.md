# ADR-001: Element Plus Auto-Import

**Status:** Accepted
**Date:** 2026-05-20
**Deciders:** AI for Trader Team

## Context

The frontend was importing Element Plus globally via `app.use(ElementPlus)`, which pulled
the entire component library into the production bundle. This added approximately 330KB
(gzipped) to the initial load, significantly impacting page load times — especially on
mobile and slower connections.

Most pages only use a handful of Element Plus components, making the full bundle import
wasteful for the majority of routes.

## Decision

Switch to on-demand auto-import using:

- `unplugin-vue-components` with `ElementPlusResolver` for component auto-registration
- `unplugin-auto-import` with `ElementPlusResolver` for API auto-imports (ElMessage, ElNotification, etc.)

Vite config additions:

```ts
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

export default defineConfig({
  plugins: [
    AutoImport({ resolvers: [ElementPlusResolver()] }),
    Components({ resolvers: [ElementPlusResolver()] }),
  ],
})
```

Generated declaration files (`auto-imports.d.ts`, `components.d.ts`) are committed to the
repository to support IDE type checking without requiring a build step.

## Consequences

### Positive

- ~73KB reduction in gzipped bundle size (330KB → 257KB)
- Faster initial page loads and improved Lighthouse scores
- Tree-shaking works correctly — only used components are bundled
- No manual import statements needed for Element Plus components

### Negative

- Generated type declaration files (`auto-imports.d.ts`, `components.d.ts`) must be
  committed and can cause merge conflicts
- Dynamic components using `resolveComponent()` or `<component :is="...">` with string
  names may not be auto-resolved — these require explicit imports
- Developers must run the dev server at least once to regenerate declarations after
  adding new components

### Neutral

- Element Plus styles are still imported per-component via the resolver's side-effect
  style imports
- No change to the runtime behavior of components — only the bundling strategy changes
