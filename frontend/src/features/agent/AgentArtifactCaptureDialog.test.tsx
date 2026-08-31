import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type {
  AgentArtifactCapturePreview,
  AgentArtifactDetail,
  PromptEnhancerTransport,
} from "../../shared/api/contracts";
import { TransportError } from "../../shared/api/httpTransport";
import { AgentArtifactCaptureDialog } from "./AgentArtifactCaptureDialog";

const PROJECT_ID = "1".repeat(32);
const SESSION_ID = "2".repeat(32);

function preview(overrides: Partial<AgentArtifactCapturePreview> = {}): AgentArtifactCapturePreview {
  return {
    contract_version: "agent-artifact-capture-preview.v1",
    project_id: PROJECT_ID,
    session_id: SESSION_ID,
    path: "reports/example.pdf",
    title: "example.pdf",
    kind: "pdf",
    media_type: "application/pdf",
    preview_kind: "pdf",
    sha256: "a".repeat(64),
    byte_size: 2048,
    requires_native_confirmation: true,
    file_content_included: false,
    ...overrides,
  };
}

function renderDialog(overrides: {
  userPresenceAvailable?: boolean;
  previewAgentArtifactCapture?: ReturnType<typeof vi.fn>;
  captureAgentArtifact?: ReturnType<typeof vi.fn>;
} = {}) {
  const result = { title: "example.pdf" } as AgentArtifactDetail;
  const transport = {
    previewAgentArtifactCapture: overrides.previewAgentArtifactCapture
      ?? vi.fn(async () => preview()),
    captureAgentArtifact: overrides.captureAgentArtifact
      ?? vi.fn(async () => result),
  } as unknown as Pick<PromptEnhancerTransport, "previewAgentArtifactCapture" | "captureAgentArtifact">;
  const onCaptured = vi.fn();
  const onClose = vi.fn();
  render(
    <AgentArtifactCaptureDialog
      initialPath="reports/example.pdf"
      onCaptured={onCaptured}
      onClose={onClose}
      open
      projectId={PROJECT_ID}
      sessionId={SESSION_ID}
      transport={transport}
      userPresenceAvailable={overrides.userPresenceAvailable ?? true}
    />,
  );
  return { transport, onCaptured, onClose, result };
}

describe("AgentArtifactCaptureDialog", () => {
  it("reviews metadata first and captures only the exact reviewed revision", async () => {
    const { transport, onCaptured, onClose, result } = renderDialog();

    fireEvent.click(screen.getByRole("button", { name: "Review output" }));
    await screen.findByRole("region", { name: "Generated output review" });

    expect(transport.previewAgentArtifactCapture).toHaveBeenCalledWith(
      PROJECT_ID,
      SESSION_ID,
      { path: "reports/example.pdf" },
      expect.any(AbortSignal),
    );
    expect(transport.captureAgentArtifact).not.toHaveBeenCalled();
    expect(screen.getByText("Local PDF viewer")).toBeInTheDocument();
    expect(screen.getByText(/2,?048 bytes/u)).toBeInTheDocument();
    expect(screen.getByText(/No file bytes are included/u)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Add verified output" }));
    await waitFor(() => expect(transport.captureAgentArtifact).toHaveBeenCalledWith(
      PROJECT_ID,
      SESSION_ID,
      {
        path: "reports/example.pdf",
        title: "example.pdf",
        expected_sha256: "a".repeat(64),
        expected_byte_size: 2048,
      },
      expect.any(AbortSignal),
    ));
    expect(onCaptured).toHaveBeenCalledWith(result);
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("clears a stale review and requires reviewing the changed file again", async () => {
    const captureAgentArtifact = vi.fn(async () => {
      throw new TransportError(
        "synthetic revision conflict",
        409,
        "agent_artifact_revision_changed",
      );
    });
    renderDialog({ captureAgentArtifact });

    fireEvent.click(screen.getByRole("button", { name: "Review output" }));
    await screen.findByRole("button", { name: "Add verified output" });
    fireEvent.click(screen.getByRole("button", { name: "Add verified output" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The file changed after review. Nothing was captured",
    );
    expect(screen.getByRole("button", { name: "Review output" })).toBeEnabled();
    expect(screen.queryByRole("region", { name: "Generated output review" })).not.toBeInTheDocument();
  });

  it("keeps native capture disabled when user-presence confirmation is unavailable", async () => {
    const { transport } = renderDialog({ userPresenceAvailable: false });
    fireEvent.click(screen.getByRole("button", { name: "Review output" }));

    const add = await screen.findByRole("button", { name: "Add verified output" });
    expect(add).toBeDisabled();
    expect(screen.getByText(/native user-presence confirmation is not available/u)).toBeInTheDocument();
    fireEvent.click(add);
    expect(transport.captureAgentArtifact).not.toHaveBeenCalled();
  });

  it("invalidates the reviewed revision when the path or title changes", async () => {
    renderDialog();
    fireEvent.click(screen.getByRole("button", { name: "Review output" }));
    await screen.findByRole("button", { name: "Add verified output" });

    fireEvent.change(screen.getByLabelText(/Display title/u), { target: { value: "Updated title" } });
    expect(screen.queryByRole("button", { name: "Add verified output" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Review output" })).toBeEnabled();
  });
});
