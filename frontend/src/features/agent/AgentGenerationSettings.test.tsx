import { StrictMode } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AgentGenerationSettings, type AgentGenerationParameters } from "./AgentGenerationSettings";
import { TransportError } from "../../shared/api/httpTransport";

const initial: AgentGenerationParameters = { temperature: 0.2, top_p: 0.95, max_tokens: 1400, enable_thinking: false };
const field = () => screen.getByLabelText("Generation max tokens");
const saveButton = () => screen.getByRole("button", { name: "Save generation settings" });
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((accept) => { resolve = accept; });
  return { promise, resolve };
}

describe("AgentGenerationSettings", () => {
  it("saves explicit edits without submitting the surrounding composer form", async () => {
    const onSave = vi.fn(async () => undefined);
    const onSubmit = vi.fn((event: React.FormEvent) => event.preventDefault());
    render(<form onSubmit={onSubmit}><AgentGenerationSettings contextLimit={4096} onSave={onSave} parameters={initial} /></form>);
    fireEvent.change(field(), { target: { value: "2048" } });
    fireEvent.keyDown(field(), { key: "Enter" });
    fireEvent.keyDown(field(), { key: "Enter", ctrlKey: true });
    expect(onSubmit).not.toHaveBeenCalled();
    fireEvent.click(saveButton());
    await waitFor(() => expect(onSave).toHaveBeenCalledWith(
      { ...initial, max_tokens: 2048 },
      initial,
    ));
    expect(saveButton()).toBeDisabled();
  });

  it.each(["", "63", "8193", "1.5", "NaN"])("keeps invalid raw max token input (%s) and blocks save", (value) => {
    const onSave = vi.fn(async () => undefined);
    render(<AgentGenerationSettings contextLimit={null} onSave={onSave} parameters={initial} />);
    fireEvent.change(field(), { target: { value } });
    expect(field()).toHaveValue(value);
    expect(saveButton()).toBeDisabled();
    expect(screen.getByRole("alert")).toHaveTextContent(/integer from 64 to 8,192/i);
    expect(onSave).not.toHaveBeenCalled();
  });

  it("blocks an impossible context budget and keeps edits after a failed save", async () => {
    const onSave = vi.fn(async () => { throw { error_code: "agent_session_parameters_conflict" }; });
    render(<AgentGenerationSettings contextLimit={4096} onSave={onSave} parameters={initial} />);
    fireEvent.change(field(), { target: { value: "4096" } });
    expect(saveButton()).toBeDisabled();
    expect(screen.getByRole("alert")).toHaveTextContent(/must be below the 4096-token context limit/i);
    fireEvent.change(field(), { target: { value: "1200" } });
    fireEvent.click(saveButton());
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/changed elsewhere/i));
    expect(field()).toHaveValue("1200");
  });

  it.each(["agent_session_parameters_conflict", "agent_catalog_session_revision_conflict"] as const)("keeps the raw edit and offers Reload for real %s transport conflicts", async (reasonCode) => {
    const onSave = vi.fn(async () => { throw new TransportError("stale", 409, reasonCode); });
    render(<AgentGenerationSettings contextLimit={4096} onReload={async () => null} onSave={onSave} parameters={initial} />);
    fireEvent.click(screen.getByText("Generation settings", { selector: "summary" }));
    fireEvent.change(field(), { target: { value: "1200" } });
    fireEvent.click(saveButton());
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/changed elsewhere/i));
    expect(field()).toHaveValue("1200");
    expect(screen.getByRole("button", { name: "Reload current settings" })).toBeEnabled();
  });

  it("preserves edits across same-value rerenders and requires reload after an external change", async () => {
    const onSave = vi.fn(async () => undefined);
    const onReload = vi.fn(async () => ({ ...initial, max_tokens: 1800 }));
    const { rerender } = render(<AgentGenerationSettings contextLimit={null} onReload={onReload} onSave={onSave} parameters={initial} />);
    fireEvent.change(field(), { target: { value: "2000" } });
    rerender(<AgentGenerationSettings contextLimit={null} onReload={onReload} onSave={onSave} parameters={{ ...initial }} />);
    expect(field()).toHaveValue("2000");
    const latest = { ...initial, max_tokens: 1800 };
    rerender(<AgentGenerationSettings contextLimit={null} onReload={onReload} onSave={onSave} parameters={latest} />);
    expect(field()).toHaveValue("2000");
    expect(saveButton()).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Reload current settings" }));
    await waitFor(() => expect(field()).toHaveValue("1800"));
    expect(saveButton()).toBeDisabled();
  });

  it("keeps thinking available for model-neutral chats with a conditional label", () => {
    const { rerender } = render(<AgentGenerationSettings contextLimit={null} onSave={vi.fn(async () => undefined)} parameters={initial} />);
    fireEvent.click(screen.getByText("Generation settings", { selector: "summary" }));
    expect(screen.getByLabelText("Generation thinking")).toBeInTheDocument();
    expect(screen.getByText(/template\/model dependent/i)).toBeVisible();
    rerender(<AgentGenerationSettings contextLimit={4096} modelProvided onSave={vi.fn(async () => undefined)} parameters={initial} />);
    expect(screen.getByText(/Enable thinking for this model/i)).toBeVisible();
  });

  it("awaits Reload and adopts only the exact returned parameters", async () => {
    const pending = deferred<AgentGenerationParameters | null>();
    const onReload = vi.fn(() => pending.promise);
    const { rerender } = render(<AgentGenerationSettings contextLimit={null} onReload={onReload} onSave={vi.fn(async () => undefined)} parameters={initial} />);
    fireEvent.click(screen.getByText("Generation settings", { selector: "summary" }));
    fireEvent.change(field(), { target: { value: "2048" } });
    rerender(<AgentGenerationSettings contextLimit={null} onReload={onReload} onSave={vi.fn(async () => undefined)} parameters={{ ...initial, max_tokens: 1600 }} />);
    fireEvent.click(screen.getByRole("button", { name: "Reload current settings" }));
    expect(screen.getAllByRole("button", { name: "Reloading…" })[0]).toBeDisabled();
    expect(onReload).toHaveBeenCalledOnce();
    pending.resolve({ ...initial, max_tokens: 1800 });
    await waitFor(() => expect(field()).toHaveValue("1800"));
  });

  it("retains raw edits when Reload fails or returns no acknowledgement", async () => {
    const onReload = vi.fn(async () => { throw new Error("synthetic reload failure"); });
    const { rerender } = render(<AgentGenerationSettings contextLimit={null} onReload={onReload} onSave={vi.fn(async () => undefined)} parameters={initial} />);
    fireEvent.click(screen.getByText("Generation settings", { selector: "summary" }));
    fireEvent.change(field(), { target: { value: "2048" } });
    rerender(<AgentGenerationSettings contextLimit={null} onReload={onReload} onSave={vi.fn(async () => undefined)} parameters={{ ...initial, max_tokens: 1600 }} />);
    fireEvent.click(screen.getByRole("button", { name: "Reload current settings" }));
    await waitFor(() => expect(screen.getAllByRole("alert").some((node) => /could not be reloaded/i.test(node.textContent ?? ""))).toBe(true));
    expect(field()).toHaveValue("2048");
    rerender(<AgentGenerationSettings contextLimit={null} onReload={async () => null} onSave={vi.fn(async () => undefined)} parameters={{ ...initial, max_tokens: 1600 }} />);
  });

  it("does not clear editor state when Save reports false", async () => {
    const onSave = vi.fn(async () => false);
    render(<AgentGenerationSettings contextLimit={null} onSave={onSave} parameters={initial} />);
    fireEvent.click(screen.getByText("Generation settings", { selector: "summary" }));
    fireEvent.change(field(), { target: { value: "2048" } });
    fireEvent.click(saveButton());
    await waitFor(() => expect(onSave).toHaveBeenCalledOnce());
    expect(field()).toHaveValue("2048");
    expect(saveButton()).toBeEnabled();
  });

  it("shows explicit Reload before any conflict when supplied by the parent", () => {
    render(<AgentGenerationSettings contextLimit={null} onReload={async () => null} onSave={vi.fn(async () => undefined)} parameters={initial} />);
    fireEvent.click(screen.getByText("Generation settings", { selector: "summary" }));
    expect(screen.getByRole("button", { name: "Reload current settings" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Save generation settings" })).toHaveAccessibleDescription(/no unsaved generation changes/i);
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveAccessibleDescription(/no unsaved generation changes/i);
  });

  it("blocks Save until the current catalog is ready while leaving Reload available", () => {
    render(<AgentGenerationSettings contextLimit={null} onReload={async () => initial} onSave={vi.fn(async () => undefined)} parameters={initial} saveReady={false} />);
    fireEvent.click(screen.getByText("Generation settings", { selector: "summary" }));
    fireEvent.change(field(), { target: { value: "2048" } });
    expect(saveButton()).toBeDisabled();
    expect(saveButton()).toHaveAccessibleDescription(/until the current generation settings load/i);
    expect(screen.getByRole("button", { name: "Reload current settings" })).toBeEnabled();
  });

  it("does not remain mounted-fenced after StrictMode setup cleanup", async () => {
    const onSave = vi.fn(async () => undefined);
    const onReload = vi.fn(async () => ({ ...initial, max_tokens: 1800 }));
    render(<StrictMode><AgentGenerationSettings contextLimit={null} onReload={onReload} onSave={onSave} parameters={initial} /></StrictMode>);
    fireEvent.click(screen.getByText("Generation settings", { selector: "summary" }));
    fireEvent.change(field(), { target: { value: "2048" } });
    fireEvent.click(saveButton());
    await waitFor(() => expect(onSave).toHaveBeenCalledOnce());
    expect(saveButton()).toBeDisabled();
  });

  it("keeps Reload available after an API conflict and failed retry", async () => {
    const onSave = vi.fn(async () => { throw new TransportError("stale", 409, "agent_catalog_session_revision_conflict"); });
    const onReload = vi.fn()
      .mockRejectedValueOnce(new Error("synthetic reload failure"))
      .mockResolvedValueOnce({ ...initial, max_tokens: 1600 });
    render(<AgentGenerationSettings contextLimit={null} onReload={onReload} onSave={onSave} parameters={initial} />);
    fireEvent.click(screen.getByText("Generation settings", { selector: "summary" }));
    fireEvent.change(field(), { target: { value: "2048" } });
    fireEvent.click(saveButton());
    await waitFor(() => expect(screen.getByRole("button", { name: "Reload current settings" })).toBeVisible());
    fireEvent.click(screen.getByRole("button", { name: "Reload current settings" }));
    await waitFor(() => expect(screen.getByText(/could not be reloaded/i)).toBeVisible());
    expect(screen.getByRole("button", { name: "Reload current settings" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Reload current settings" }));
    await waitFor(() => expect(field()).toHaveValue("1600"));
    expect(screen.getByRole("button", { name: "Reload current settings" })).toBeEnabled();
  });
});
