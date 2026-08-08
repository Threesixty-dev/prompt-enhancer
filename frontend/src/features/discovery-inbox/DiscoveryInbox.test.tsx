import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { createSyntheticTransport } from "../../shared/api/syntheticTransport";
import { DiscoveryInbox } from "./DiscoveryInbox";

describe("DiscoveryInbox", () => {
  it("loads the undecided review queue and supports merge selection", async () => {
    const onUndecidedCountChange = vi.fn();
    render(
      <DiscoveryInbox
        navigate={vi.fn()}
        onUndecidedCountChange={onUndecidedCountChange}
        transport={createSyntheticTransport()}
      />,
    );

    expect(await screen.findByRole("button", { name: /Candidate aaaaaa/ })).toBeVisible();
    expect(onUndecidedCountChange).toHaveBeenLastCalledWith(2);
    expect(screen.getByRole("button", { name: /Candidate bbbbbb/ })).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "Reviewed" }));
    expect(await screen.findByRole("button", { name: /Candidate cccccc/ })).toBeVisible();
    await waitFor(() =>
      expect(onUndecidedCountChange).toHaveBeenLastCalledWith(2),
    );
    fireEvent.click(screen.getByRole("button", { name: "Needs review" }));
    expect(await screen.findByRole("button", { name: /Candidate aaaaaa/ })).toBeVisible();
    expect(onUndecidedCountChange).toHaveBeenLastCalledWith(2);

    const checkboxes = screen.getAllByRole("checkbox");
    fireEvent.click(checkboxes[0]);
    fireEvent.click(checkboxes[1]);

    const merge = screen.getByRole("button", { name: "Merge selected" });
    expect(merge).toBeEnabled();
    fireEvent.click(merge);

    await waitFor(() =>
      expect(screen.getByText(/merge decision saved/i)).toBeVisible(),
    );
    await waitFor(() =>
      expect(onUndecidedCountChange).toHaveBeenLastCalledWith(0),
    );
  });
});
