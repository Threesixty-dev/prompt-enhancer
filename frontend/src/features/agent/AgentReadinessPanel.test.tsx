import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AgentReadinessPanel } from "./AgentReadinessPanel";
import {
  AGENT_LEGACY_PARITY,
  AGENT_PARITY_SUMMARY,
  AGENT_REQUESTED_CAPABILITIES,
} from "./agentReleaseParity";

describe("AgentReadinessPanel", () => {
  it("reconciles every requested capability with frozen implementation evidence", () => {
    render(<AgentReadinessPanel onOpenConnections={vi.fn()} onOpenOwnerChecks={vi.fn()} />);

    expect(screen.getByRole("heading", { name: "Agent capability readiness" })).toBeVisible();
    expect(screen.getByLabelText("Requested Agent capabilities").children).toHaveLength(15);
    expect(screen.getAllByText("Implemented · owner check pending")).toHaveLength(10);
    expect(screen.getAllByText("Implemented · automated evidence passed")).toHaveLength(5);
    expect(screen.queryByText("Not implemented")).toBeNull();
    expect(screen.getByText(/Provider-neutral controller and MCP endpoint/u)).toBeVisible();
    expect(screen.getByText(/Create, view, edit, move, trash, diff, and review workspace files/u)).toBeVisible();
    expect(screen.getByText(/implementation and synthetic-test evidence—not a claim/u)).toBeVisible();
  });

  it("keeps every requested row bound to a known parity group", () => {
    const parityKeys = new Set(AGENT_LEGACY_PARITY.map((item) => item.key));
    expect(AGENT_REQUESTED_CAPABILITIES.every((item) => (
      item.parityKeys.length > 0 && item.parityKeys.every((key) => parityKeys.has(key))
    ))).toBe(true);
    expect(AGENT_PARITY_SUMMARY).toMatchObject({
      complete: 16,
      missing: 0,
      ownerPending: 10,
      platformBlocked: 0,
      total: 16,
    });
  });

  it("routes to controller setup and guarded owner checks without starting either", () => {
    const openConnections = vi.fn();
    const openOwnerChecks = vi.fn();
    render(<AgentReadinessPanel onOpenConnections={openConnections} onOpenOwnerChecks={openOwnerChecks} />);

    fireEvent.click(screen.getByRole("button", { name: "Open connections" }));
    fireEvent.click(screen.getByRole("button", { name: "Open owner checks" }));
    expect(openConnections).toHaveBeenCalledOnce();
    expect(openOwnerChecks).toHaveBeenCalledOnce();
  });
});
