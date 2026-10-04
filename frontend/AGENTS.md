# Frontend guidance

Next.js App Router + React + TypeScript. Routes in `src/app/`, UI in `src/components/`, domain logic in `src/core/`, tests mirror `src/` under `tests/unit/` (Vitest) and `tests/e2e/` (Playwright). Follow the root test selection policy; read `src/AGENTS.md` before changing data-flow, messaging, or thread state.

## Ownership

`src/core/threads/use-thread-page.ts` owns the shared chat-route wiring (stream wiring, welcome state, empty-thread redirect, stop/branch/regenerate, view turn-submit controller); the showcase chat, workspace chat, and agent chat routes are views over it. `src/app/workspace/chats/[thread_id]/page.tsx` owns composer busy state. `src/core/threads/turn-submit.ts` owns the message submit chain (duplicate fence, draft policy, attachment pre-uploads, turn lifecycle); the composer and chat pages are views over its controller, and `src/core/threads/hooks.ts` owns streaming while joining the shared fence through `turnSubmitGate`. Keep new shared chat-route wiring in the thread-page hook, and new submit-chain state and effects in the turn-submit module — not in the composer, pages, or stream hooks. `src/hooks/usePoseStream.ts` only selects from the store; `App.tsx` owns the global WebSocket lifecycle.

`ui/` and `ai-elements/` contain generated components. Change their source registry or generation input instead of editing generated output by hand. Keep server components as the default and add `"use client"` only where browser interaction or client state requires it.

## Environment & dependencies

`pnpm-workspace.yaml` overrides vulnerable `@xmldom/xmldom` 0.9.x releases to 0.9.12 for GHSA-965w-775f-mr7g. Nextra pulls it in through MathJax and `speech-rule-engine@4.1.2`, which pins 0.9.8. Keep the override until the upstream dependency chain resolves a patched version without it; regenerate `pnpm-lock.yaml` and verify the docs build when changing this constraint.

Backend API URLs are optional; the nginx proxy is used by default. Leave `NEXT_PUBLIC_LANGGRAPH_BASE_URL` and `NEXT_PUBLIC_BACKEND_BASE_URL` unset for the standard `make dev` / Docker flow, where nginx serves the public `/api/langgraph/*` prefix and rewrites it to Gateway's native `/api/*` routes.

## Tests & conventions

Preserve the repository's Rstest/Vitest allocation and run the focused test plus the narrowest relevant check for each local slice. Use the frontend standard lane at implementation completion; use `pr-standard` for cross-stack and high-risk changes. Running a single test file: `pnpm vitest run <file>` for the default Vitest include, `pnpm rstest run <file>` for `*.dom.test.tsx` and the other Rstest-only suites — matching the runner to the file avoids the "No test files found" dead end.

Use `@/*` for `src/*` imports and inline type imports. Keep import groups ordered by the existing ESLint rules, prefix intentionally unused variables with `_`, and use `cn()` from `@/lib/utils` for conditional Tailwind classes. Obtain the LangGraph singleton through `getAPIClient()`; thread hooks own streaming. TanStack Query owns server state, including `core/knowledge-admin/hooks.ts`; localStorage owns user settings. Validate environment variables through `src/env.js`. Auth server code in `src/server/` is active.
