import { act, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { PromptEnhancerTransport } from "../../shared/api/contracts";
import { createSyntheticTransport } from "../../shared/api/syntheticTransport";
import { ModelEnsembleOverlay } from "./ModelEnsembleOverlay";

async function settlePoll() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

describe("ModelEnsembleOverlay", () => {
  it("renders an absent active watch as an idle choice, not a disconnection", async () => {
    const getActiveModelEnsembleWatch = vi.fn().mockRejectedValue({ status: 404 });
    const transport: PromptEnhancerTransport = {
      ...createSyntheticTransport(),
      getActiveModelEnsembleWatch,
    };

    render(<ModelEnsembleOverlay transport={transport} />);
    await waitFor(() => expect(getActiveModelEnsembleWatch).toHaveBeenCalledOnce());
    await settlePoll();

    expect(screen.getByText("No active watch")).toBeVisible();
    expect(screen.getByText(/choose “Watch this session”/i)).toBeVisible();
    expect(screen.queryByText(/Disconnected/)).not.toBeInTheDocument();
  });

  it("reserves disconnected for an actual service failure", async () => {
    const getActiveModelEnsembleWatch = vi.fn().mockRejectedValue({ status: 503 });
    const transport: PromptEnhancerTransport = {
      ...createSyntheticTransport(),
      getActiveModelEnsembleWatch,
    };

    render(<ModelEnsembleOverlay transport={transport} />);

    expect(await screen.findByText(/Disconnected · retaining last receipt/i)).toBeVisible();
  });
});
