import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ErrorState } from "./AsyncState";

describe("ErrorState recovery contracts", () => {
  it("offers the supplied in-place retry action for recoverable failures", () => {
    const retry = vi.fn();
    render(<ErrorState actionLabel="Retry synthetic read" message="Synthetic read failed." onRetry={retry} />);

    fireEvent.click(screen.getByRole("button", { name: "Retry synthetic read" }));
    expect(retry).toHaveBeenCalledOnce();
  });

  it("guides preservation before a manual reload for the explicit non-retryable mode", () => {
    render(<ErrorState
      message="Synthetic optional download did not finish."
      recovery="preserve-work-before-reload"
    />);

    const failure = screen.getByRole("alert");
    expect(failure).toHaveTextContent("Preserve or copy unsent drafts and unsaved file work before explicitly reloading the app.");
    expect(within(failure).queryByRole("button", { name: /Retry|Reload/u })).toBeNull();
  });
});
