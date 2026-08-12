import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { createSyntheticTransport } from "../../shared/api/syntheticTransport";
import { ResearchLab } from "./ResearchLab";

describe("ResearchLab", () => {
  it("shows a compact metric roadmap without reading sessions or activating models", async () => {
    const transport = createSyntheticTransport();
    const inventorySpy = vi.spyOn(transport, "getModelLabInventory");
    const catalogSpy = vi.spyOn(transport, "getTextAnalysisResearch");
    const sessionSpy = vi.spyOn(transport, "listCodexSessions");
    const analysisSpy = vi.spyOn(transport, "startSessionQualityAnalysis");

    render(<ResearchLab transport={transport} />);

    expect(await screen.findByRole("heading", { name: "Build useful metrics, then earn trust" })).toBeVisible();
    expect(screen.getByText("One profile, not one developer score")).toBeVisible();
    expect(screen.getByText("Task definition")).toBeVisible();
    expect(screen.getByText("Clarification value")).toBeVisible();
    expect(screen.getByText("0").closest("div")).toHaveTextContent("neural models activated");
    expect(catalogSpy).toHaveBeenCalledTimes(1);
    expect(sessionSpy).not.toHaveBeenCalled();
    expect(analysisSpy).not.toHaveBeenCalled();
    expect(inventorySpy).not.toHaveBeenCalled();
  });

  it("separates methods and candidate decisions into fast views", async () => {
    const transport = createSyntheticTransport();
    const modelStart = vi.spyOn(transport, "startTextModelEvaluation");
    const inventorySpy = vi.spyOn(transport, "getModelLabInventory");
    const sessionSpy = vi.spyOn(transport, "listCodexSessions");
    render(<ResearchLab transport={transport} />);
    await screen.findByRole("heading", { name: "Build useful metrics, then earn trust" });

    fireEvent.click(screen.getByRole("tab", { name: "Method stack" }));
    expect(screen.getByRole("heading", { name: "Multilingual semantic retrieval" })).toBeVisible();
    expect(screen.getByText("Blocked by validation")).toBeVisible();

    fireEvent.click(screen.getByRole("tab", { name: "Model candidates" }));
    expect(screen.getByRole("heading", { name: "Multilingual E5 small" })).toBeVisible();
    expect(screen.getAllByText("Rejected by gate").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Product use is off").length).toBeGreaterThan(0);
    expect(await screen.findByRole("heading", { name: "Synthetic evaluation inventory" })).toBeVisible();
    expect(inventorySpy).toHaveBeenCalledTimes(1);
    expect(await screen.findByText("CUDA")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Test cached session models" }));
    expect(await screen.findByText("Screen complete")).toBeVisible();
    expect(screen.getAllByText(/Top1 Accuracy 75%/).length).toBeGreaterThan(0);
    expect(modelStart).toHaveBeenCalledWith(
      {
        candidate: "session-link",
        device: "auto",
        mode: "smoke",
        allow_download: false,
      },
    );
    expect(sessionSpy).not.toHaveBeenCalled();
  });

  it("fails closed when the catalog capability is absent", async () => {
    const transport = createSyntheticTransport();
    transport.getTextAnalysisResearch = undefined;
    render(<ResearchLab transport={transport} />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The methods catalog is unavailable",
    );
    expect(screen.getByRole("alert")).toHaveTextContent("No session was read");
  });
});
