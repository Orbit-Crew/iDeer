// Shared setup for the rstest `dom` project (mirrors tests/setup.ts, which
// only reaches vitest). Registers jest-dom matchers on rstest's expect and
// guarantees DOM cleanup between tests, so `.dom.test.*` files get the same
// `toBeInTheDocument()` contract whether rstest or vitest runs them.
import { afterEach, expect } from "@rstest/core";
import * as jestDomMatchers from "@testing-library/jest-dom/matchers";
import { cleanup } from "@testing-library/react";

expect.extend(jestDomMatchers);

afterEach(cleanup);
