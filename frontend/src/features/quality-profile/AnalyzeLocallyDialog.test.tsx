import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import type { SessionQualityAnalysisRequest } from "../../shared/api/contracts";
import { TransportError } from "../../shared/api/httpTransport";
import { AnalyzeLocallyDialog } from "./AnalyzeLocallyDialog";
import { COACHING_ANALYSIS_REQUEST } from "./standardEngineeringAnalysisPreset";

describe("AnalyzeLocallyDialog", () => {
  it("starts the exact coaching profile with one explicit action and no configurators", async () => {
    const onAnalyze = vi.fn(
      async (
        _request: SessionQualityAnalysisRequest,
        _idempotencyKey: string,
        _signal: AbortSignal,
      ) => undefined,
    );
    render(
      <div className="app-shell">
        <AnalyzeLocallyDialog
          onAnalyze={onAnalyze}
          onClose={vi.fn()}
          sessionDescriptor="Reviewed implementation · 11 Aug 2026 · abcd1234"
        />
      </div>,
    );

    const dialog = screen.getByRole("dialog", { name: "Ready to analyze" });
    const submit = within(dialog).getByRole("button", {
      name: "Analyze this session",
    });
    expect(submit).toHaveFocus();
    expect(
      within(dialog).getByText("Reviewed implementation · 11 Aug 2026 · abcd1234"),
    ).toBeVisible();
    expect(within(dialog).getByText(/20 prompt, collaboration, logic, and outcome metric attempts/i)).toBeVisible();
    expect(within(dialog).getByText(/unknown or abstained/i)).toBeVisible();
    expect(within(dialog).queryByRole("checkbox")).not.toBeInTheDocument();
    expect(within(dialog).queryByRole("combobox")).not.toBeInTheDocument();
    expect(within(dialog).queryByRole("radio")).not.toBeInTheDocument();
    expect(within(dialog).queryByRole("textbox")).not.toBeInTheDocument();
    expect(within(dialog).queryByRole("spinbutton")).not.toBeInTheDocument();
    expect(dialog.querySelector("fieldset, details, input, select, textarea")).toBeNull();
    expect(dialog.querySelectorAll("button[type='submit']")).toHaveLength(1);

    fireEvent.click(submit);

    await waitFor(() => expect(onAnalyze).toHaveBeenCalledTimes(1));
    const [request, idempotencyKey, signal] = onAnalyze.mock.calls[0];
    expect(request).toEqual(COACHING_ANALYSIS_REQUEST);
    expect(request).toEqual({
      preset_id: "coaching_profile_v1",
      confirmation: "analyze_selected_redacted_text",
    });
    expect(idempotencyKey).toMatch(/^dashboard-quality-analysis-/);
    expect(signal).toBeInstanceOf(AbortSignal);
  });

  it("locks submission while pending and keeps one explicit cancel path", async () => {
    let capturedSignal: AbortSignal | undefined;
    const onAnalyze = vi.fn((
      _request: SessionQualityAnalysisRequest,
      _key: string,
      signal: AbortSignal,
    ) => {
      capturedSignal = signal;
      return new Promise<void>(() => undefined);
    });
    const onClose = vi.fn();
    render(
      <div className="app-shell">
        <AnalyzeLocallyDialog onAnalyze={onAnalyze} onClose={onClose} />
      </div>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Analyze this session" }));
    await waitFor(() => expect(capturedSignal).toBeDefined());

    const dialog = screen.getByRole("dialog", { name: "Ready to analyze" });
    expect(within(dialog).getByRole("button", { name: "Analyzing locally…" })).toBeDisabled();
    expect(within(dialog).getByRole("button", { name: "Close analysis review" })).toBeDisabled();
    const cancel = within(dialog).getByRole("button", { name: "Cancel request" });
    expect(cancel).toBeEnabled();
    expect(cancel).toHaveFocus();
    fireEvent.click(cancel);

    expect(capturedSignal?.aborted).toBe(true);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("traps focus, closes with Escape, and restores focus to the opener", async () => {
    function Harness() {
      const [open, setOpen] = useState(false);
      return (
        <div className="app-shell">
          <button onClick={() => setOpen(true)} type="button">Open analysis review</button>
          {open && (
            <AnalyzeLocallyDialog onAnalyze={vi.fn()} onClose={() => setOpen(false)} />
          )}
        </div>
      );
    }
    render(<Harness />);
    const opener = screen.getByRole("button", { name: "Open analysis review" });
    opener.focus();
    fireEvent.click(opener);
    const primary = screen.getByRole("button", { name: "Analyze this session" });
    const close = screen.getByRole("button", { name: "Close analysis review" });
    expect(primary).toHaveFocus();

    fireEvent.keyDown(window, { key: "Tab" });
    expect(close).toHaveFocus();
    fireEvent.keyDown(window, { key: "Tab", shiftKey: true });
    expect(primary).toHaveFocus();
    fireEvent.keyDown(window, { key: "Escape" });

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(opener).toHaveFocus();
  });

  it("sanitizes failures and allows a one-click retry", async () => {
    const onAnalyze = vi
      .fn()
      .mockRejectedValueOnce(
        new TransportError("PRIVATE-PROVIDER-ERROR-CANARY", 503, "provider_unavailable"),
      )
      .mockResolvedValueOnce(undefined);
    const onClose = vi.fn();
    render(
      <div className="app-shell">
        <AnalyzeLocallyDialog onAnalyze={onAnalyze} onClose={onClose} />
      </div>,
    );
    const submit = screen.getByRole("button", { name: "Analyze this session" });
    fireEvent.click(submit);

    expect(await screen.findByText(/provider is temporarily unavailable/i)).toBeVisible();
    expect(document.body.textContent).not.toContain("PRIVATE-PROVIDER-ERROR-CANARY");
    expect(submit).toBeEnabled();
    expect(submit).toHaveAccessibleName("Retry analysis");
    fireEvent.click(submit);

    await waitFor(() => expect(onAnalyze).toHaveBeenCalledTimes(2));
    expect(onAnalyze.mock.calls[1][0]).toEqual(COACHING_ANALYSIS_REQUEST);
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
  });

  it.each([
    ["source_schema_unsupported", /content schema/i],
    ["selection_snapshot_miss", /indexed session changed/i],
    ["source_resource_limit", /fixed local safety limit/i],
    ["source_timeout", /timed out/i],
    ["no_analyzable_text", /no analyzable prompt or response text/i],
    ["provider_protocol_rejected", /schema compatibility passed.*rejected this session read/i],
    ["provider_compatibility_blocked", /installed-schema compatibility status changed/i],
  ])("maps allowlisted reason %s without displaying server content", async (reasonCode, copy) => {
    const onAnalyze = vi.fn(async () => {
      throw new TransportError("PRIVATE-SERVER-MESSAGE-CANARY", 503, reasonCode as never);
    });
    render(
      <div className="app-shell">
        <AnalyzeLocallyDialog onAnalyze={onAnalyze} onClose={vi.fn()} />
      </div>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Analyze this session" }));

    expect(await screen.findByText(copy)).toBeVisible();
    expect(document.body.textContent).not.toContain("PRIVATE-SERVER-MESSAGE-CANARY");
  });

  it("keeps a live read rejection separate from installed-schema compatibility", async () => {
    const onAnalyze = vi
      .fn()
      .mockRejectedValueOnce(
        new TransportError("PRIVATE-PROVIDER-CANARY", 503, "provider_protocol_rejected"),
      )
      .mockResolvedValueOnce(undefined);
    const onClose = vi.fn();
    render(
      <div className="app-shell">
        <AnalyzeLocallyDialog onAnalyze={onAnalyze} onClose={onClose} />
      </div>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Analyze this session" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/schema compatibility passed/i);
    expect(alert).toHaveTextContent(/rechecking schema compatibility alone will not repair/i);
    expect(alert).not.toHaveTextContent(/check compatibility again/i);
    fireEvent.click(screen.getByRole("button", { name: "Retry analysis" }));

    await waitFor(() => expect(onAnalyze).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
  });

  it("turns a lost local response into actionable content-free guidance", async () => {
    const onAnalyze = vi.fn(async () => {
      throw new Error("PRIVATE-NETWORK-CANARY");
    });
    render(
      <div className="app-shell">
        <AnalyzeLocallyDialog onAnalyze={onAnalyze} onClose={vi.fn()} />
      </div>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Analyze this session" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /browser lost the local analysis response/i,
    );
    expect(document.body.textContent).not.toContain("PRIVATE-NETWORK-CANARY");
    expect(screen.getByRole("button", { name: "Retry analysis" })).toBeEnabled();
  });

  it("offers one content-free recheck when compatibility changed during analysis", async () => {
    const onAnalyze = vi.fn(async () => {
      throw new TransportError(
        "PRIVATE-PROVIDER-CANARY",
        503,
        "provider_compatibility_blocked",
      );
    });
    const onCheckCompatibility = vi.fn(async (_signal: AbortSignal) => undefined);
    const onClose = vi.fn();
    render(
      <div className="app-shell">
        <AnalyzeLocallyDialog
          onAnalyze={onAnalyze}
          onCheckCompatibility={onCheckCompatibility}
          onClose={onClose}
        />
      </div>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Analyze this session" }));
    expect(await screen.findByRole("button", { name: "Recheck compatibility" })).toBeEnabled();
    expect(screen.getByRole("status")).toHaveTextContent(/analysis is paused/i);

    fireEvent.click(screen.getByRole("button", { name: "Recheck compatibility" }));

    await waitFor(() => expect(onCheckCompatibility).toHaveBeenCalledTimes(1));
    expect(onCheckCompatibility.mock.calls[0][0]).toBeInstanceOf(AbortSignal);
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
    expect(onAnalyze).toHaveBeenCalledTimes(1);
  });
});
