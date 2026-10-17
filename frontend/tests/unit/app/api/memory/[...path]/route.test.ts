import { afterAll, beforeEach, describe, expect, test, vi } from "vitest";

vi.hoisted(() => {
  vi.stubEnv(
    "IDEER_INTERNAL_GATEWAY_BASE_URL",
    "http://internal-gateway.test:9123",
  );
  vi.stubEnv("NEXT_PUBLIC_BACKEND_BASE_URL", "http://public-gateway.test:8123");
});

const mockFetch = vi.fn();
global.fetch = mockFetch;

vi.mock("next/server", () => ({
  NextRequest: class {},
  NextResponse: class {
    static json(data: unknown, init?: { status?: number }) {
      return { json: () => data, status: init?.status ?? 200 };
    }
  },
}));

import { GET, POST, DELETE, PATCH } from "@/app/api/memory/[...path]/route";

afterAll(() => {
  vi.unstubAllEnvs();
});

function createRequest(method = "GET") {
  const headers = new Headers({
    host: "localhost:3000",
    connection: "keep-alive",
    "content-length": "0",
  });
  return {
    method,
    headers,
    arrayBuffer: () => Promise.resolve(new ArrayBuffer(0)),
  } as unknown as import("next/server").NextRequest;
}

const mockParams = { params: Promise.resolve({ path: ["facts"] }) };

describe("memory catch-all API route", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("GET proxies to /api/memory/facts", async () => {
    const mockResponse = new Response(JSON.stringify({ facts: [] }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
    mockFetch.mockResolvedValueOnce(mockResponse);

    await GET(createRequest("GET"), mockParams);

    expect(mockFetch).toHaveBeenCalledOnce();
    const [url, options] = mockFetch.mock.calls[0]!;
    expect(url.toString()).toBe(
      "http://internal-gateway.test:9123/api/memory/facts",
    );
    expect(options.method).toBe("GET");
  });

  test("POST proxies to /api/memory/facts", async () => {
    const mockResponse = new Response(JSON.stringify({ ok: true }), {
      status: 200,
    });
    mockFetch.mockResolvedValueOnce(mockResponse);

    await POST(createRequest("POST"), mockParams);

    const [url, options] = mockFetch.mock.calls[0]!;
    expect(url.toString()).toContain("/api/memory/facts");
    expect(options.method).toBe("POST");
  });

  test("DELETE proxies to /api/memory/facts", async () => {
    const mockResponse = new Response(JSON.stringify({ deleted: true }), {
      status: 200,
    });
    mockFetch.mockResolvedValueOnce(mockResponse);

    await DELETE(createRequest("DELETE"), mockParams);

    const [url, options] = mockFetch.mock.calls[0]!;
    expect(url.toString()).toContain("/api/memory/facts");
    expect(options.method).toBe("DELETE");
  });

  test("PATCH proxies to /api/memory/facts", async () => {
    const mockResponse = new Response(JSON.stringify({ updated: true }), {
      status: 200,
    });
    mockFetch.mockResolvedValueOnce(mockResponse);

    await PATCH(createRequest("PATCH"), mockParams);

    const [url, options] = mockFetch.mock.calls[0]!;
    expect(url.toString()).toContain("/api/memory/facts");
    expect(options.method).toBe("PATCH");
  });

  test("strips host and connection headers", async () => {
    const mockResponse = new Response("", { status: 200 });
    mockFetch.mockResolvedValueOnce(mockResponse);

    await GET(createRequest("GET"), mockParams);

    const [, options] = mockFetch.mock.calls[0]!;
    expect(options.headers.get("host")).toBeNull();
    expect(options.headers.get("connection")).toBeNull();
  });

  test("strips client-forged x-forwarded headers", async () => {
    const request = createRequest("GET");
    const headers = request.headers;
    headers.set("x-forwarded-for", "203.0.113.9");
    headers.set("x-forwarded-host", "evil.example");
    headers.set("x-forwarded-proto", "https");
    const mockResponse = new Response("", { status: 200 });
    mockFetch.mockResolvedValueOnce(mockResponse);

    await GET(request, mockParams);

    const [, options] = mockFetch.mock.calls[0]!;
    expect(options.headers.get("x-forwarded-for")).toBeNull();
    expect(options.headers.get("x-forwarded-host")).toBeNull();
    expect(options.headers.get("x-forwarded-proto")).toBeNull();
  });

  test("drops stale transfer headers from the decoded backend response", async () => {
    // undici already decoded the body; forwarding content-encoding/length
    // verbatim would make the browser double-decode once the gateway enables
    // compression (report 07-M3).
    const mockResponse = new Response("decoded", {
      status: 200,
      headers: {
        "content-type": "application/json",
        "content-encoding": "gzip",
        "content-length": "42",
        "transfer-encoding": "chunked",
      },
    });
    mockFetch.mockResolvedValueOnce(mockResponse);

    const proxied = await GET(createRequest("GET"), mockParams);

    expect(proxied.headers.get("content-encoding")).toBeNull();
    expect(proxied.headers.get("content-length")).toBeNull();
    expect(proxied.headers.get("transfer-encoding")).toBeNull();
    expect(proxied.headers.get("content-type")).toBe("application/json");
    await expect(proxied.text()).resolves.toBe("decoded");
  });

  test("forwards body for POST requests", async () => {
    const mockResponse = new Response("", { status: 200 });
    mockFetch.mockResolvedValueOnce(mockResponse);

    await POST(createRequest("POST"), mockParams);

    const [, options] = mockFetch.mock.calls[0]!;
    expect(options.body).toBeDefined();
  });

  test("does not forward body for GET requests", async () => {
    const mockResponse = new Response("", { status: 200 });
    mockFetch.mockResolvedValueOnce(mockResponse);

    await GET(createRequest("GET"), mockParams);

    const [, options] = mockFetch.mock.calls[0]!;
    expect(options.body).toBeUndefined();
  });

  test("joins multiple path segments", async () => {
    const mockResponse = new Response("", { status: 200 });
    mockFetch.mockResolvedValueOnce(mockResponse);

    const multiParams = {
      params: Promise.resolve({ path: ["facts", "123", "edit"] }),
    };
    await GET(createRequest("GET"), multiParams);

    const [url] = mockFetch.mock.calls[0]!;
    expect(url.toString()).toContain("/api/memory/facts/123/edit");
  });

  // --- path traversal rejection ---

  test.each([
    {
      name: "multi-segment .. segments",
      path: ["..", "v1", "admin"],
    },
    {
      name: "decoded ..%2F.. form (slashes inside one segment)",
      path: ["../../v1/admin"],
    },
    {
      name: "re-encoded %2e%2e segment",
      path: ["%2e%2e", "v1", "admin"],
    },
    {
      name: ".. nested between valid segments",
      path: ["a", "..", ".."],
    },
    {
      name: "backslash traversal segment",
      path: ["..\\v1"],
    },
    {
      name: "empty segment",
      path: ["facts", ""],
    },
  ])("returns 404 for $name without proxying", async ({ path }) => {
    const traversalParams = { params: Promise.resolve({ path }) };
    const result = await GET(createRequest("GET"), traversalParams);

    expect(result.status).toBe(404);
    expect(mockFetch).not.toHaveBeenCalled();
    expect(await result.text()).toBe("");
  });

  test("returns the backend response", async () => {
    const body = JSON.stringify({ data: "test" });
    const mockResponse = new Response(body, {
      status: 201,
      headers: { "content-type": "application/json" },
    });
    mockFetch.mockResolvedValueOnce(mockResponse);

    const result = await GET(createRequest("GET"), mockParams);
    expect(result.status).toBe(201);
  });
});
