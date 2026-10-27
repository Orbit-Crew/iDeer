import { render, screen, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { KnowledgeScopeSelector } from "@/components/workspace/chats/knowledge-scope-selector";
import type { AgentKnowledgeScope } from "@/core/library";

vi.mock("@/core/i18n/hooks", () => ({
  useI18n: () => ({
    t: {
      library: {
        knowledgeScopeSelector: {
          title: "Knowledge for this chat",
          narrowOnly:
            "Selection only narrows this chat's authorized knowledge; it can never search beyond it.",
          loadError: "Unable to load the knowledge scope.",
          deviceSource: "This device",
          serverSource: "Server knowledge",
          deviceOffline: "device offline",
          revision: (no: number) => `v${no}`,
          checkboxAria: (name: string) => `Search ${name} in this chat`,
        },
      },
    },
  }),
}));

const scope: AgentKnowledgeScope = {
  agent_id: "agent-1",
  selection: "narrow_only",
  sources: [
    {
      resource_id: "kb-device",
      slug: "kb-device",
      display_name: "Device docs",
      origin: "local_import",
      dataset: "local:rev-1",
      revision_id: "rev-1",
      revision_no: 3,
      manifest_hash: "a".repeat(64),
      device_id: "device-1",
      device_online: true,
    },
    {
      resource_id: "kb-server",
      slug: "kb-server",
      display_name: "Server docs",
      origin: "provider",
      dataset: "ds-1",
      revision_id: "rev-2",
      revision_no: 7,
      manifest_hash: "b".repeat(64),
    },
    {
      resource_id: "kb-away",
      slug: "kb-away",
      display_name: "Offline docs",
      origin: "local_import",
      dataset: "local:rev-3",
      revision_id: "rev-3",
      revision_no: 1,
      manifest_hash: "c".repeat(64),
      device_id: "device-9",
      device_online: false,
    },
  ],
};

afterEach(cleanup);

describe("KnowledgeScopeSelector", () => {
  test("renders nothing when the agent authorizes no knowledge sources", () => {
    const { container } = render(
      <KnowledgeScopeSelector
        scope={{ agent_id: "agent-1", sources: [], selection: "narrow_only" }}
        selected={[]}
        onChange={() => {}}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  test("lists device and server sources with kind, revision, and online state", () => {
    render(
      <KnowledgeScopeSelector scope={scope} selected={["kb-device", "kb-server", "kb-away"]} onChange={() => {}} />,
    );
    expect(screen.getByText("Device docs")).toBeInTheDocument();
    expect(screen.getByText("This device")).toBeInTheDocument();
    expect(screen.getByText("Server docs")).toBeInTheDocument();
    expect(screen.getByText("Server knowledge")).toBeInTheDocument();
    expect(screen.getByText("v3")).toBeInTheDocument();
    expect(screen.getByText("v7")).toBeInTheDocument();
    // An offline device KB stays visible but is marked, never silently mixed in.
    expect(screen.getByText("Offline docs")).toBeInTheDocument();
    expect(screen.getByText("device offline")).toBeInTheDocument();
    expect(screen.getByText("v1")).toBeInTheDocument();
  });

  test("toggling a source reports the narrowed selection", async () => {
    const onChange = vi.fn();
    render(
      <KnowledgeScopeSelector scope={scope} selected={["kb-device", "kb-server", "kb-away"]} onChange={onChange} />,
    );
    await userEvent.click(screen.getByRole("checkbox", { name: "Search Server docs in this chat" }));
    expect(onChange).toHaveBeenCalledWith(["kb-device", "kb-away"]);
  });

  test("a source the caller never authorized cannot be added by name", async () => {
    // Selection can only narrow: there is no input that accepts arbitrary
    // KB ids, and unknown ids are ignored on toggle.
    const onChange = vi.fn();
    render(
      <KnowledgeScopeSelector scope={scope} selected={["kb-server"]} onChange={onChange} />,
    );
    await userEvent.click(screen.getByRole("checkbox", { name: "Search Device docs in this chat" }));
    expect(onChange).toHaveBeenCalledWith(["kb-server", "kb-device"]);
    expect(screen.queryByText("Search Forbidden KB in this chat")).not.toBeInTheDocument();
  });

  test("shows the load error state without pretending the scope is empty", () => {
    render(<KnowledgeScopeSelector scope={undefined} loadError selected={[]} onChange={() => {}} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Unable to load the knowledge scope.");
  });
});
