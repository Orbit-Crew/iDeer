import type { NextRequest } from "next/server";

import {
  MOCK_API_UNAVAILABLE,
  mockApiDisabled,
} from "@/app/mock/api/mock-api-gate";
import type { MCPConfig } from "@/core/mcp/types";

const defaultConfig: MCPConfig = {
  mcp_servers: {
    "mcp-github-trending": {
      enabled: true,
      type: "stdio",
      command: "uvx",
      args: ["mcp-github-trending"],
      env: {},
      headers: {},
      description:
        "A MCP server that provides access to GitHub trending repositories and developers data",
    },
    "context-7": {
      enabled: true,
      type: "stdio",
      command: "",
      args: [],
      env: {},
      headers: {},
      description:
        "Get the latest documentation and code into Cursor, Claude, or other LLMs",
    },
    "feishu-importer": {
      enabled: true,
      type: "stdio",
      command: "",
      args: [],
      env: {},
      headers: {},
      description: "Import Feishu documents",
    },
  },
};

let storedConfig: MCPConfig = structuredClone(defaultConfig);

export function GET() {
  if (mockApiDisabled()) return MOCK_API_UNAVAILABLE;
  return Response.json(storedConfig);
}

export async function PUT(request: NextRequest) {
  if (mockApiDisabled()) return MOCK_API_UNAVAILABLE;
  const config = (await request.json()) as MCPConfig;
  storedConfig = config;
  return Response.json(storedConfig);
}
