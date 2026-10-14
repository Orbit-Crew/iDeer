import type { NextRequest } from "next/server";

import {
  MOCK_API_UNAVAILABLE,
  mockApiDisabled,
} from "@/app/mock/api/mock-api-gate";
import { DEMO_THREAD_IDS } from "@/core/threads/static-demo";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ thread_id: string }> },
) {
  if (mockApiDisabled()) return MOCK_API_UNAVAILABLE;
  const threadId = (await params).thread_id;
  if (!DEMO_THREAD_IDS.some((candidate) => candidate === threadId)) {
    return new Response("Thread not found", { status: 404 });
  }
  const response = await fetch(
    new URL(
      `/demo/threads/${encodeURIComponent(threadId)}/thread.json`,
      request.nextUrl.origin,
    ),
    { signal: request.signal },
  );
  if (!response.ok) return new Response("Thread not found", { status: 404 });
  const json = (await response.json()) as { history?: unknown[] };
  if (Array.isArray(json.history)) {
    return Response.json(json);
  }
  return Response.json([json]);
}
