import { fireEvent, render, screen } from "@testing-library/react";
import { useRef, useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { Dialog } from "./Dialog";
import { Disclosure } from "./Disclosure";
import { FactList } from "./FactList";
import { ProgressMeter } from "./ProgressMeter";
import { TabList, tabPanelId } from "./Tabs";

function DialogHarness({ onClose }: { onClose: () => void }) {
  const [tick, setTick] = useState(0);
  return (
    <>
      <button type="button">Opener</button>
      <button onClick={() => setTick((value) => value + 1)} type="button">Tick {tick}</button>
      <Dialog description="A short description." onClose={onClose} open title="Example dialog">
        <button type="button">First</button>
        <button type="button">Second</button>
      </Dialog>
    </>
  );
}

describe("shared UI primitives", () => {
  it("Dialog traps focus, closes on Escape, restores focus, and does not re-focus on unrelated re-renders", () => {
    const onClose = vi.fn();
    const view = render(<DialogHarness onClose={onClose} />);
    const opener = screen.getByRole("button", { name: "Opener" });
    opener.focus();
    // Mount with open=true focused the close button; simulate an opener-driven flow instead.
    view.rerender(<DialogHarness onClose={onClose} />);
    const dialog = screen.getByRole("dialog", { name: "Example dialog" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAccessibleDescription("A short description.");
    const close = screen.getByRole("button", { name: "Close dialog" });
    const second = screen.getByRole("button", { name: "Second" });
    second.focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(close).toHaveFocus();
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(second).toHaveFocus();
    // Unrelated re-render while open must not move focus back to the initial control.
    second.focus();
    fireEvent.click(screen.getByRole("button", { name: /Tick/ }));
    expect(screen.getByRole("button", { name: /Tick 1/ })).toBeInTheDocument();
    expect(second).toHaveFocus();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("Dialog returns focus to the element focused before it opened", () => {
    function Harness() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button onClick={() => setOpen(true)} type="button">Open</button>
          <Dialog onClose={() => setOpen(false)} open={open} title="Return focus">
            <p>Body</p>
          </Dialog>
        </>
      );
    }
    render(<Harness />);
    const open = screen.getByRole("button", { name: "Open" });
    open.focus();
    fireEvent.click(open);
    expect(screen.getByRole("button", { name: "Close dialog" })).toHaveFocus();
    fireEvent.click(screen.getByRole("button", { name: "Close dialog" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(open).toHaveFocus();
  });

  it("Dialog skips focusable descendants of a collapsed Disclosure", () => {
    function Harness() {
      const hiddenActionRef = useRef<HTMLButtonElement>(null);
      return (
        <Dialog
          initialFocusRef={hiddenActionRef}
          onClose={vi.fn()}
          open
          title="Disclosure dialog"
        >
          <Disclosure summary="Advanced options">
            <button ref={hiddenActionRef} type="button">Hidden action</button>
          </Disclosure>
        </Dialog>
      );
    }
    render(<Harness />);

    expect(screen.getByRole("button", { name: "Close dialog" })).toHaveFocus();
    const trigger = screen.getByRole("button", { name: "Advanced options" });
    trigger.focus();
    fireEvent.keyDown(document, { key: "Tab" });

    expect(screen.getByRole("button", { name: "Close dialog" })).toHaveFocus();
  });

  it("Dialog falls back when the requested initial control is disabled", () => {
    function Harness() {
      const disabledRef = useRef<HTMLButtonElement>(null);
      return (
        <Dialog initialFocusRef={disabledRef} onClose={vi.fn()} open title="Disabled initial control">
          <button disabled ref={disabledRef} type="button">Unavailable action</button>
        </Dialog>
      );
    }
    render(<Harness />);

    expect(screen.getByRole("button", { name: "Close dialog" })).toHaveFocus();
  });

  it("Dialog falls back when CSS hides the requested initial control", () => {
    function Harness() {
      const hiddenRef = useRef<HTMLButtonElement>(null);
      return (
        <Dialog initialFocusRef={hiddenRef} onClose={vi.fn()} open title="CSS-hidden initial control">
          <button ref={hiddenRef} style={{ display: "none" }} type="button">Hidden action</button>
        </Dialog>
      );
    }
    render(<Harness />);

    expect(screen.getByRole("button", { name: "Close dialog" })).toHaveFocus();
  });

  it("Disclosure is a real button bound to its panel and keeps the panel mounted but hidden", () => {
    render(<Disclosure detail="2 items" summary="Members"><p>Panel body</p></Disclosure>);
    const trigger = screen.getByRole("button", { name: /Members/ });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    const panel = document.getElementById(trigger.getAttribute("aria-controls")!)!;
    expect(panel).toHaveAttribute("hidden");
    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(panel).not.toHaveAttribute("hidden");
  });

  it("FactList renders null details as an explicit not-reported texture, never blank", () => {
    render(<FactList facts={[{ term: "Model", detail: null, missingLabel: "No model estimate reported" }, { term: "Scope", detail: "Me" }]} label="Facts" />);
    const list = screen.getByLabelText("Facts");
    const rows = list.querySelectorAll("div");
    expect(rows[0]).toHaveAttribute("data-unknown", "true");
    expect(rows[0].textContent).toBe("ModelNo model estimate reported");
    expect(rows[1]).not.toHaveAttribute("data-unknown");
  });

  it("ProgressMeter never draws an unknown amount as zero and echoes state in aria-valuetext", () => {
    const { rerender } = render(<ProgressMeter detail="waiting for consent" label="Transfer" state="idle" value={null} />);
    const bar = screen.getByRole("progressbar", { name: "Transfer" });
    expect(bar).not.toHaveAttribute("aria-valuenow");
    expect(bar).toHaveAttribute("data-unknown", "true");
    expect(bar).toHaveAttribute("aria-valuetext", "waiting for consent · amount unknown");
    rerender(<ProgressMeter detail="paused" label="Transfer" max={200} state="paused" value={50} />);
    expect(bar).toHaveAttribute("aria-valuenow", "25");
    expect(bar).toHaveAttribute("aria-valuetext", "25% · paused");
  });

  it("TabList exposes tabs with roving arrow-key focus and selection", () => {
    function Harness() {
      const [tab, setTab] = useState<"a" | "b">("a");
      return (
        <>
          <TabList idPrefix="x" label="Sections" onChange={setTab} tabs={[{ id: "a", label: "Alpha" }, { id: "b", label: "Beta", badge: 2 }]} value={tab} />
          <div id={tabPanelId("x", tab)} role="tabpanel">{tab}</div>
        </>
      );
    }
    render(<Harness />);
    const alpha = screen.getByRole("tab", { name: "Alpha" });
    const beta = screen.getByRole("tab", { name: /Beta/ });
    expect(alpha).toHaveAttribute("aria-selected", "true");
    expect(beta).toHaveAttribute("tabindex", "-1");
    alpha.focus();
    fireEvent.keyDown(screen.getByRole("tablist", { name: "Sections" }), { key: "ArrowRight" });
    expect(beta).toHaveFocus();
    expect(beta).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel")).toHaveTextContent("b");
    expect(screen.getByLabelText("2 unread")).toBeInTheDocument();
  });
});
