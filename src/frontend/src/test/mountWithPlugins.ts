/**
 * Compatibility re-export shim.
 *
 * The canonical mountWithPlugins helper lives at
 * `src/__tests__/mountWithPlugins.ts` (post-C26 refactor in commit 281f41b5).
 * 3 test files still import from `@/test/mountWithPlugins`. This thin
 * re-export preserves the old import path.
 */
export { mountWithPlugins } from '@/__tests__/mountWithPlugins'
