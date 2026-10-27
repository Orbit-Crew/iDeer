import { render, screen, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import type { LocalPublication } from "@/core/library";

// ── Mocks ────────────────────────────────────────────────────────────────────

const mockRevisions = [
  {
    id: "rev-1",
    resource_id: "kb-1",
    revision_no: 1,
    status: "draft",
    manifest_hash:
      "a1b2c3d4e5f6a7b8a1b2c3d4e5f6a7b8a1b2c3d4e5f6a7b8a1b2c3d4e5f6a7b8",
    document_count: 2,
    failure_code: null,
    failure_message: null,
    created_at: "2026-09-13T00:00:00Z",
    published_at: null,
  },
  {
    id: "rev-2",
    resource_id: "kb-1",
    revision_no: 2,
    status: "published",
    manifest_hash:
      "b2c3d4e5f6a7b8a1b2c3d4e5f6a7b8a1b2c3d4e5f6a7b8a1b2c3d4e5f6a7b8a1",
    document_count: 3,
    failure_code: null,
    failure_message: null,
    created_at: "2026-09-13T01:00:00Z",
    published_at: "2026-09-13T02:00:00Z",
  },
];

const mockDetail = {
  ...mockRevisions[0],
  documents: [
    {
      document_id: "doc-1",
      content_hash:
        "f1e2d3c4b5a6f1e2d3c4b5a6f1e2d3c4b5a6f1e2d3c4b5a6f1e2d3c4b5a6f1e2",
      filename: "guide.txt",
      size_bytes: 15,
      mime_type: "text/plain",
      metadata: {},
    },
  ],
};

vi.mock("@/core/i18n/hooks", () => ({
  useI18n: () => ({
    t: {
      library: {
        revisionList: {
          selectKnowledgeBase: "Select a knowledge base to view revisions",
          loading: "Loading...",
          loadFailed: "Unable to load revisions.",
          empty: "No revision candidates yet",
          createCandidate: "Create revision candidate",
          creating: "Creating...",
          createFailed:
            "Unable to create a revision candidate. A candidate requires at least one ready document.",
          publishFailed: "Unable to publish this revision.",
          prepareFailed: "Unable to prepare this revision.",
          viewDetails: "View details",
          hideDetails: "Hide details",
          documentsAndManifest: (count: number, hash: string) =>
            `${count} documents · manifest ${hash}`,
          publishingStatus: "publishing",
          integrityFlagged: (status: string) =>
            `Reconciliation flagged this revision as ${status}`,
          publish: "Publish",
          publishingAction: "Publishing...",
          publishAria: (no: number) => `Publish v${no}`,
          prepare: "Prepare index",
          preparing: "Preparing...",
          prepareAria: (no: number) => `Prepare index for v${no}`,
          localPublication: {
            title: "Server publication",
            checking: "Checking publication status...",
            checkFailed: "Unable to load the publication status.",
            notPublished:
              "Not published to the server. This device-local revision stays private; publication is an explicit owner action from the Desktop.",
            awaitingContent: (missing: number) =>
              `Publication awaiting content: ${missing} document(s) not uploaded yet.`,
            readyToComplete:
              "All content uploaded and verified; publication completion is pending.",
            publishing: "Publishing the server copy...",
            failed: (code: string) => `Publication failed (${code}). You can retry from the Desktop; the failed attempt stays visible.`,
            published: (name: string) => `Published as server copy "${name}".`,
            copyVisibility: (visibility: string) => `copy visibility: ${visibility}`,
            governanceNote:
              "Team access was granted through the platform visibility application flow; the source device knowledge base stays private.",
          },
        },
      },
    },
  }),
}));

const createRevision = vi.fn();
const publishRevision = vi.fn();
const prepareRevision = vi.fn();

const notPublished: LocalPublication = {
  source: {
    resource_id: "kb-1",
    display_name: "Kb 1",
    revision_id: "rev-1",
    revision_no: 1,
    manifest_hash: "a".repeat(64),
    document_count: 1,
  },
  status: "none",
  missing_documents: [],
  copy: null,
  revision: null,
};

const publishedCopy: LocalPublication = {
  source: { ...notPublished.source },
  status: "published",
  missing_documents: [],
  copy: {
    resource_id: "copy-1",
    slug: "kb-1-pub-r1",
    display_name: "Kb 1 · Server copy R1",
    visibility: "department",
    document_count: 1,
    documents: [],
  },
  revision: {
    resource_id: "copy-1",
    id: "copy-rev-1",
    revision_no: 1,
    status: "published",
    manifest_hash: "b".repeat(64),
    failure_code: null,
    failure_message: null,
    published_at: "2026-10-27T00:00:00Z",
    provider_dataset_id: "dataset-1",
  },
};

const failedCopy: LocalPublication = {
  source: { ...notPublished.source },
  status: "failed",
  missing_documents: [],
  copy: publishedCopy.copy,
  revision: {
    resource_id: "copy-1",
    id: "copy-rev-1",
    revision_no: 1,
    status: "failed",
    manifest_hash: "b".repeat(64),
    failure_code: "parse_failed",
    failure_message: "provider build failed",
    published_at: null,
    provider_dataset_id: null,
  },
};

const awaitingCopy: LocalPublication = {
  source: { ...notPublished.source },
  status: "awaiting_content",
  missing_documents: ["guide.txt"],
  copy: publishedCopy.copy,
  revision: null,
};

let mockState: {
  revisions: typeof mockRevisions;
  isLoading: boolean;
  error: Error | null;
  detail: typeof mockDetail;
  detailError: Error | null;
  publication: typeof notPublished;
  publicationError: Error | null;
};

vi.mock("@/core/library", () => ({
  useKnowledgeRevisions: (_resourceId: string | undefined) => ({
    revisions: mockState.revisions,
    isLoading: mockState.isLoading,
    error: mockState.error,
  }),
  useKnowledgeRevision: (
    _resourceId: string | undefined,
    _revisionId: string | undefined,
  ) => ({
    data: mockState.detail,
    isLoading: false,
    error: mockState.detailError,
  }),
  useCreateKnowledgeRevision: () => ({
    isPending: false,
    error: null,
    mutateAsync: createRevision,
  }),
  usePublishKnowledgeRevision: () => ({
    isPending: false,
    error: null,
    mutateAsync: publishRevision,
  }),
  usePrepareKnowledgeRevision: () => ({
    isPending: false,
    error: null,
    mutateAsync: prepareRevision,
  }),
  useLocalPublication: (
    _resourceId: string | undefined,
    _revisionId: string | undefined,
  ) => ({
    data: mockState.publication,
    isLoading: false,
    error: mockState.publicationError,
  }),
}));

// ── Dynamic import ───────────────────────────────────────────────────────────

let RevisionList: typeof import("@/components/workspace/library/revision-list").RevisionList;

beforeEach(async () => {
  vi.clearAllMocks();
  mockState = {
    revisions: mockRevisions,
    isLoading: false,
    error: null,
    detail: mockDetail,
    detailError: null,
    publication: notPublished,
    publicationError: null,
  };
  const mod = await import("@/components/workspace/library/revision-list");
  RevisionList = mod.RevisionList;
});

afterEach(() => {
  cleanup();
});

// ── Tests ────────────────────────────────────────────────────────────────────

describe("RevisionList", () => {
  test("prompts to select a knowledge base when none is selected", () => {
    render(<RevisionList />);
    expect(
      screen.getByText("Select a knowledge base to view revisions"),
    ).toBeInTheDocument();
  });

  test("shows a loading state", () => {
    mockState.isLoading = true;
    render(<RevisionList knowledgeBaseId="kb-1" />);
    expect(screen.getByText("Loading...")).toBeInTheDocument();
  });

  test("shows an error state", () => {
    mockState.error = new Error("boom");
    render(<RevisionList knowledgeBaseId="kb-1" />);
    expect(screen.getByText("Unable to load revisions.")).toBeInTheDocument();
  });

  test("shows the empty state", () => {
    mockState.revisions = [];
    render(<RevisionList knowledgeBaseId="kb-1" canModify />);
    expect(screen.getByText("No revision candidates yet")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Create revision candidate" }),
    ).toBeInTheDocument();
  });

  test("renders revision cards with status and manifest short hash", () => {
    render(<RevisionList knowledgeBaseId="kb-1" />);
    expect(screen.getByText("v1")).toBeInTheDocument();
    expect(screen.getByText("v2")).toBeInTheDocument();
    expect(screen.getByText("draft")).toBeInTheDocument();
    expect(screen.getByText("published")).toBeInTheDocument();
    expect(screen.getAllByText(/manifest a1b2c3d4e5f6/)).toHaveLength(1);
  });

  test("create is hidden for users who cannot modify", () => {
    render(<RevisionList knowledgeBaseId="kb-1" />);
    expect(
      screen.queryByRole("button", { name: "Create revision candidate" }),
    ).not.toBeInTheDocument();
  });

  test("create button invokes the mutation", async () => {
    const user = userEvent.setup();
    render(<RevisionList knowledgeBaseId="kb-1" canModify />);
    await user.click(
      screen.getByRole("button", { name: "Create revision candidate" }),
    );
    expect(createRevision).toHaveBeenCalledTimes(1);
  });

  test("draft revision offers a publish action for owners", async () => {
    const user = userEvent.setup();
    render(<RevisionList knowledgeBaseId="kb-1" canModify />);
    await user.click(screen.getByRole("button", { name: "Publish v1" }));
    expect(publishRevision).toHaveBeenCalledWith("rev-1");
  });

  test("published revision offers no publish action", () => {
    render(<RevisionList knowledgeBaseId="kb-1" canModify />);
    expect(
      screen.queryByRole("button", { name: "Publish v2" }),
    ).not.toBeInTheDocument();
  });

  test("publish is hidden for users who cannot modify", () => {
    render(<RevisionList knowledgeBaseId="kb-1" />);
    expect(
      screen.queryByRole("button", { name: "Publish v1" }),
    ).not.toBeInTheDocument();
  });

  test("expanding a revision loads its document manifest", async () => {
    const user = userEvent.setup();
    render(<RevisionList knowledgeBaseId="kb-1" />);
    await user.click(
      screen.getAllByRole("button", { name: "View details" })[0]!,
    );
    expect(screen.getByText(/guide\.txt/)).toBeInTheDocument();
    expect(screen.getByText(/f1e2d3c4b5a6/)).toBeInTheDocument();
    const toggle = screen.getByRole("button", { name: "Hide details" });
    await user.click(toggle);
    expect(screen.queryByText(/guide\.txt/)).not.toBeInTheDocument();
  });

  test("details state the publication is not started for a private revision", async () => {
    const user = userEvent.setup();
    render(<RevisionList knowledgeBaseId="kb-1" />);
    await user.click(
      screen.getAllByRole("button", { name: "View details" })[0]!,
    );
    const panel = screen.getByTestId("local-publication-panel");
    expect(panel).toHaveTextContent("Not published to the server");
  });

  test("details show the published server copy and its governed visibility", async () => {
    mockState.publication = publishedCopy;
    const user = userEvent.setup();
    render(<RevisionList knowledgeBaseId="kb-1" />);
    await user.click(
      screen.getAllByRole("button", { name: "View details" })[0]!,
    );
    const panel = screen.getByTestId("local-publication-panel");
    expect(panel).toHaveTextContent(
      'Published as server copy "Kb 1 · Server copy R1"',
    );
    expect(panel).toHaveTextContent("copy visibility: department");
    expect(panel).toHaveTextContent("copy-1");
    expect(panel).toHaveTextContent("visibility application flow");
  });

  test("details show the failed publication with its failure code", async () => {
    mockState.publication = failedCopy;
    const user = userEvent.setup();
    render(<RevisionList knowledgeBaseId="kb-1" />);
    await user.click(
      screen.getAllByRole("button", { name: "View details" })[0]!,
    );
    const panel = screen.getByTestId("local-publication-panel");
    expect(panel).toHaveTextContent("Publication failed (parse_failed)");
    expect(panel).toHaveTextContent("provider build failed");
  });

  test("details show an interrupted upload as awaiting content", async () => {
    mockState.publication = awaitingCopy;
    const user = userEvent.setup();
    render(<RevisionList knowledgeBaseId="kb-1" />);
    await user.click(
      screen.getAllByRole("button", { name: "View details" })[0]!,
    );
    const panel = screen.getByTestId("local-publication-panel");
    expect(panel).toHaveTextContent(
      "Publication awaiting content: 1 document(s) not uploaded yet",
    );
    expect(panel).toHaveTextContent("guide.txt");
  });

  test("a failed publication query surfaces an explicit load failure", async () => {
    mockState.publicationError = new Error("boom");
    const user = userEvent.setup();
    render(<RevisionList knowledgeBaseId="kb-1" />);
    await user.click(
      screen.getAllByRole("button", { name: "View details" })[0]!,
    );
    expect(
      screen.getByText("Unable to load the publication status."),
    ).toBeInTheDocument();
  });
});
