import type { NextRequest } from "next/server";

const BACKEND_BASE_URL =
  process.env.IDEER_INTERNAL_GATEWAY_BASE_URL ??
  process.env.NEXT_PUBLIC_BACKEND_BASE_URL ??
  "http://127.0.0.1:8001";

const MEMORY_PROXY_PREFIX = "/api/memory/";

/**
 * Only plain path segments may reach the gateway. Next.js decodes dynamic
 * segments before routing, so a raw join would let "." / ".." (or percent
 * forms that normalize to them) escape the memory prefix inside `new URL`.
 */
function isSafeMemoryPathSegment(segment: string): boolean {
  return (
    segment.length > 0 &&
    segment !== "." &&
    segment !== ".." &&
    !/[/\\%?#]/.test(segment)
  );
}

function buildBackendUrl(pathSegments: string[]): URL | null {
  if (!pathSegments.every(isSafeMemoryPathSegment)) {
    return null;
  }

  const url = new URL(
    `${MEMORY_PROXY_PREFIX}${pathSegments.map(encodeURIComponent).join("/")}`,
    BACKEND_BASE_URL,
  );

  // Defense in depth: URL normalization must never escape the memory prefix.
  if (!url.pathname.startsWith(MEMORY_PROXY_PREFIX)) {
    return null;
  }

  return url;
}

async function proxyRequest(request: NextRequest, pathSegments: string[]) {
  const backendUrl = buildBackendUrl(pathSegments);
  if (!backendUrl) {
    return new Response(null, { status: 404 });
  }

  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.delete("connection");
  headers.delete("content-length");

  const hasBody = !["GET", "HEAD"].includes(request.method);
  const response = await fetch(backendUrl, {
    method: request.method,
    headers,
    body: hasBody ? await request.arrayBuffer() : undefined,
  });

  return new Response(await response.arrayBuffer(), {
    status: response.status,
    headers: response.headers,
  });
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  return proxyRequest(request, (await params).path);
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  return proxyRequest(request, (await params).path);
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  return proxyRequest(request, (await params).path);
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  return proxyRequest(request, (await params).path);
}
