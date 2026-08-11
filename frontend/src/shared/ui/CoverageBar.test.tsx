import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CoverageBar } from "./CoverageBar";

describe("CoverageBar", () => {
  it("preserves a small nonzero value for sighted and assistive output", () => {
    render(<CoverageBar coverage={1 / 1000} eligible={1000} observed={1} />);

    const progress = screen.getByRole("progressbar", {
      name: "1 of 1000 observations (0.1%)",
    });
    expect(progress).toHaveAttribute("aria-valuenow", "0.1");
    expect(screen.getByText("0.1%")).toBeVisible();
  });
});
