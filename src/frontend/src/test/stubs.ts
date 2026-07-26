/**
 * Compatibility re-export shim.
 *
 * The canonical stubs live at `src/__tests__/stubs.ts` (post-C26 refactor in
 * commit 281f41b5). 21 test files still import from `@/test/stubs`. Rather
 * than touch every test file in this directory move, this thin re-export
 * preserves the old import path so vue-tsc and runtime resolution both work.
 */
export { elStubs } from '@/__tests__/stubs'
