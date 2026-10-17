// Type-side counterpart of tests/setup-rstest-dom.ts: expose the jest-dom
// matchers on rstest's Assertion, giving `.dom.test.*` files the same
// typechecked matcher contract the vitest suite gets from
// `@testing-library/jest-dom/vitest` (see tests/setup.ts).
import type { TestingLibraryMatchers } from "@testing-library/jest-dom/matchers";

declare module "@rstest/core" {
  interface Assertion<T = any> extends TestingLibraryMatchers<any, T> {}
}
