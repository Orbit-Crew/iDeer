import { isStaticWebsiteOnly } from "@/core/static-mode";

/**
 * Mock/demo endpoints exist only for the offline static demo (report 07-M2).
 * In any other deployment they would be a confusing public surface answering
 * fixed demo payloads, so every handler bails with 404 unless the deployment
 * explicitly runs in static-website-only mode.
 */
export function mockApiDisabled(): boolean {
  return !isStaticWebsiteOnly();
}

export const MOCK_API_UNAVAILABLE = new Response(null, { status: 404 });
