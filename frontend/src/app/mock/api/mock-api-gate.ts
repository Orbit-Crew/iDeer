import { isStaticWebsiteOnly } from "@/core/static-mode";

/**
 * Mock/demo endpoints exist only for the offline static demo (report 07-M2).
 * In any other deployment they would be a confusing public surface answering
 * fixed demo payloads, so every handler bails with 404 unless the deployment
 * explicitly runs in static-website-only mode.
 *
 * Exception: the mock browser test lanes (frontend-smoke / frontend-mock-e2e)
 * set DEER_FLOW_MOCK_API_ENABLED=1. They keep client-side static mode OFF so
 * the Playwright interceptors own the traffic, yet demo-thread requests fall
 * through those interceptors to these real routes — closing the gate there
 * broke the showcase corpus (issue #93). The flag is server-side only and
 * must never be set on a user-facing deployment.
 */
export function mockApiDisabled(): boolean {
  if (process.env.DEER_FLOW_MOCK_API_ENABLED === "1") {
    return false;
  }
  return !isStaticWebsiteOnly();
}

export const MOCK_API_UNAVAILABLE = new Response(null, { status: 404 });
