import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const pdfMocks = vi.hoisted(() => ({
  getDocument: vi.fn(),
  workerOptions: { workerSrc: "" },
}));

vi.mock("pdfjs-dist", () => ({
  AnnotationMode: { DISABLE: 0 },
  getDocument: pdfMocks.getDocument,
  GlobalWorkerOptions: pdfMocks.workerOptions,
  RenderingCancelledException: class RenderingCancelledException extends Error {},
}));

vi.mock("pdfjs-dist/build/pdf.worker.min.mjs?url", () => ({
  default: "/assets/synthetic-pdf-worker.mjs",
}));

import { AgentPdfPreview } from "./AgentPdfPreview";
import previewCss from "./AgentPdfPreview.css?raw";

const originalCanvasContext = Object.getOwnPropertyDescriptor(
  HTMLCanvasElement.prototype,
  "getContext",
);
const originalResizeObserver = Reflect.get(globalThis, "ResizeObserver") as unknown;

// The stage is the only element measured by the component, so one prototype
// stub is enough to drive the fit calculation deterministically in jsdom.
// jsdom never lays out the canvas, so the overflow the stage would scroll is
// stated explicitly rather than derived from the rendered page. Both axes are
// stated: a page can overflow the stage vertically at the fitted width.
let stageClientWidth = 0;
let stageScrollWidth = 0;
let stageClientHeight = 0;
let stageScrollHeight = 0;
let resizeCallbacks: ResizeObserverCallback[] = [];

function triggerStageResize(): void {
  for (const callback of resizeCallbacks) callback([], {} as ResizeObserver);
}

function pdfDocument(pageCount = 3, base = { height: 800, width: 600 }) {
  const renderTasks: Array<{ cancel: ReturnType<typeof vi.fn>; promise: Promise<void> }> = [];
  const render = vi.fn(() => {
    const task = { cancel: vi.fn(), promise: Promise.resolve() };
    renderTasks.push(task);
    return task;
  });
  const getViewport = vi.fn(({ scale }: { scale: number }) => ({
    height: base.height * scale,
    width: base.width * scale,
  }));
  const cleanup = vi.fn(() => true);
  const pages = new Map<number, { cleanup: typeof cleanup; getViewport: typeof getViewport; render: typeof render }>();
  const getPage = vi.fn(async (requested: number) => {
    const existing = pages.get(requested);
    if (existing !== undefined) return existing;
    const page = { cleanup, getViewport, render };
    pages.set(requested, page);
    return page;
  });
  return {
    cleanup,
    document: { getPage, numPages: pageCount },
    getPage,
    getViewport,
    render,
    renderTasks,
  };
}

function loadingTask(document: unknown) {
  const destroy = vi.fn().mockResolvedValue(undefined);
  pdfMocks.getDocument.mockReturnValue({ destroy, promise: Promise.resolve(document) });
  return destroy;
}

function pdfBlob(): Blob {
  return new Blob(["%PDF-1.4\n%%EOF\n"], { type: "application/pdf" });
}

beforeEach(() => {
  stageClientWidth = 0;
  stageScrollWidth = 0;
  stageClientHeight = 0;
  stageScrollHeight = 0;
  resizeCallbacks = [];
  Object.defineProperty(HTMLCanvasElement.prototype, "getContext", {
    configurable: true,
    value: vi.fn(() => ({})),
  });
  Object.defineProperty(HTMLElement.prototype, "clientWidth", {
    configurable: true,
    get: () => stageClientWidth,
  });
  Object.defineProperty(HTMLElement.prototype, "scrollWidth", {
    configurable: true,
    get: () => stageScrollWidth,
  });
  Object.defineProperty(HTMLElement.prototype, "clientHeight", {
    configurable: true,
    get: () => stageClientHeight,
  });
  Object.defineProperty(HTMLElement.prototype, "scrollHeight", {
    configurable: true,
    get: () => stageScrollHeight,
  });
  Reflect.set(globalThis, "ResizeObserver", class {
    constructor(callback: ResizeObserverCallback) { resizeCallbacks.push(callback); }
    observe(): void { /* the stub is driven by triggerStageResize */ }
    unobserve(): void { /* the stub is driven by triggerStageResize */ }
    disconnect(): void { resizeCallbacks = []; }
  });
});

afterEach(() => {
  vi.restoreAllMocks();
  pdfMocks.getDocument.mockReset();
  Reflect.deleteProperty(HTMLElement.prototype, "clientWidth");
  Reflect.deleteProperty(HTMLElement.prototype, "scrollWidth");
  Reflect.deleteProperty(HTMLElement.prototype, "clientHeight");
  Reflect.deleteProperty(HTMLElement.prototype, "scrollHeight");
  if (originalResizeObserver === undefined) {
    Reflect.deleteProperty(globalThis, "ResizeObserver");
  } else {
    Reflect.set(globalThis, "ResizeObserver", originalResizeObserver);
  }
  if (originalCanvasContext) {
    Object.defineProperty(HTMLCanvasElement.prototype, "getContext", originalCanvasContext);
  } else {
    Reflect.deleteProperty(HTMLCanvasElement.prototype, "getContext");
  }
});

describe("AgentPdfPreview", () => {
  it("renders verified in-memory bytes page by page with annotations disabled and no URL fetch", async () => {
    const fixture = pdfDocument();
    const destroy = vi.fn().mockResolvedValue(undefined);
    pdfMocks.getDocument.mockReturnValue({
      destroy,
      promise: Promise.resolve(fixture.document),
    });
    const onStateChange = vi.fn();
    const { unmount } = render(<AgentPdfPreview
      blob={new Blob(["%PDF-1.4\n%%EOF\n"], { type: "application/pdf" })}
      onStateChange={onStateChange}
      title="synthetic-report.pdf"
      versionNumber={2}
    />);

    const canvas = await screen.findByRole("img", { name: "Rendered PDF page 1 of 3" });
    await waitFor(() => expect(canvas).toHaveAttribute("data-state", "ready"));
    expect(pdfMocks.workerOptions.workerSrc).toBe("/assets/synthetic-pdf-worker.mjs");
    expect(pdfMocks.getDocument).toHaveBeenCalledWith(expect.objectContaining({
      data: expect.any(Uint8Array),
      disableAutoFetch: true,
      disableRange: true,
      disableStream: true,
      enableXfa: false,
      maxImageSize: 33_554_432,
      stopAtErrors: true,
      useWasm: false,
      useWorkerFetch: false,
    }));
    expect(fixture.render).toHaveBeenCalledWith(expect.objectContaining({
      annotationMode: 0,
      background: "#ffffff",
      canvas,
    }));
    expect(onStateChange).toHaveBeenCalledWith("loading");
    expect(onStateChange).toHaveBeenLastCalledWith("ready");
    expect(screen.getByText(/Links, forms, scripts, audio, and annotations are not interactive/u)).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "Next PDF page" }));
    await waitFor(() => expect(fixture.getPage).toHaveBeenLastCalledWith(2));
    expect(await screen.findByRole("img", { name: "Rendered PDF page 2 of 3" })).toHaveAttribute("data-state", "ready");
    fireEvent.click(screen.getByRole("button", { name: "Zoom in PDF" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Fit PDF page to viewer" })).toHaveTextContent("125%"));

    unmount();
    expect(destroy).toHaveBeenCalled();
    expect(fixture.renderTasks.at(-1)?.cancel).toHaveBeenCalled();
  });

  it("fails closed when the local parser rejects the verified bytes", async () => {
    const destroy = vi.fn().mockResolvedValue(undefined);
    pdfMocks.getDocument.mockReturnValue({
      destroy,
      promise: Promise.reject(new Error("synthetic parse failure")),
    });
    const onStateChange = vi.fn();
    render(<AgentPdfPreview
      blob={new Blob(["%PDF-synthetic-invalid"], { type: "application/pdf" })}
      onStateChange={onStateChange}
      title="synthetic-invalid.pdf"
      versionNumber={1}
    />);

    expect(await screen.findByRole("alert")).toHaveTextContent("could not be parsed safely");
    expect(onStateChange).toHaveBeenLastCalledWith("error");
    expect(screen.getByRole("img", { name: "Rendered PDF page 1 of 1" })).toHaveAttribute("data-state", "error");
    expect(screen.getByRole("button", { name: "Next PDF page" })).toBeDisabled();
    expect(screen.getByRole("region", { name: "PDF preview of synthetic-invalid.pdf v1" }))
      .toHaveAttribute("aria-busy", "false");
  });

  it("keeps the chosen zoom when a stage measurement only reflects the page scrollbar", async () => {
    stageClientWidth = 700;
    const fixture = pdfDocument(1);
    loadingTask(fixture.document);
    render(<AgentPdfPreview
      blob={pdfBlob()}
      onStateChange={vi.fn()}
      title="synthetic-report.pdf"
      versionNumber={1}
    />);

    const canvas = await screen.findByRole("img", { name: "Rendered PDF page 1 of 1" });
    await waitFor(() => expect(canvas).toHaveAttribute("data-state", "ready"));
    const settledRenders = fixture.render.mock.calls.length;
    const fit = screen.getByRole("button", { name: "Fit PDF page to viewer" });

    fireEvent.click(screen.getByRole("button", { name: "Zoom in PDF" }));
    await waitFor(() => expect(canvas).toHaveAttribute("data-state", "ready"));
    expect(fit).toHaveTextContent("125%");
    expect(fixture.render).toHaveBeenCalledTimes(settledRenders + 1);
    expect(screen.getByRole("group", { name: "PDF zoom, 125 percent" })).toBeInTheDocument();

    // The taller 125% page adds a scrollbar, which shrinks the measured stage.
    // That must not cancel and restart the render the zoom step just began.
    stageClientWidth = 694;
    await act(async () => { triggerStageResize(); });
    expect(fixture.render).toHaveBeenCalledTimes(settledRenders + 1);
    expect(fit).toHaveTextContent("125%");
    expect(canvas).toHaveAttribute("data-state", "ready");

    // A genuine width change still refits the page at the retained zoom.
    stageClientWidth = 420;
    await act(async () => { triggerStageResize(); });
    await waitFor(() => expect(fixture.render).toHaveBeenCalledTimes(settledRenders + 2));
    await waitFor(() => expect(canvas).toHaveAttribute("data-state", "ready"));
    expect(fit).toHaveTextContent("125%");
  });

  it("presents a wider page at a higher zoom instead of only relabelling the control", async () => {
    stageClientWidth = 700;
    const fixture = pdfDocument(1);
    loadingTask(fixture.document);
    render(<AgentPdfPreview
      blob={pdfBlob()}
      onStateChange={vi.fn()}
      title="synthetic-report.pdf"
      versionNumber={1}
    />);

    const canvas = await screen.findByRole<HTMLCanvasElement>("img", { name: "Rendered PDF page 1 of 1" });
    await waitFor(() => expect(canvas).toHaveAttribute("data-state", "ready"));
    const fittedWidth = Number.parseInt(canvas.style.width, 10);
    // 700px of padding box, less the 24px of stage padding and the pixel of
    // slack that keeps a fitted page inside a rounded `clientWidth`.
    expect(fittedWidth).toBe(675);

    fireEvent.click(screen.getByRole("button", { name: "Zoom in PDF" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Fit PDF page to viewer" })).toHaveTextContent("125%"));
    await waitFor(() => expect(canvas).toHaveAttribute("data-state", "ready"));
    const zoomedWidth = Number.parseInt(canvas.style.width, 10);
    expect(zoomedWidth).toBeGreaterThan(fittedWidth);
    expect(zoomedWidth).toBe(Math.floor(fittedWidth * 1.25));
    // The presented width, not only the backing store, has to grow: the global
    // `img, video, canvas { max-width: 100% }` reset would otherwise clamp the
    // zoomed page back to the fitted stage width in a real browser.
    expect(previewCss).toMatch(/\.agent-pdf-preview__canvas\s*\{[^}]*max-width:\s*none;/);
    // The overflow the enlarged page creates stays inside the stage.
    expect(previewCss).toMatch(/\.agent-pdf-preview__stage\s*\{[^}]*overflow:\s*auto;/);
    expect(previewCss).toMatch(/\.agent-pdf-preview\s*\{[^}]*overflow:\s*hidden;/);

    fireEvent.click(screen.getByRole("button", { name: "Fit PDF page to viewer" }));
    await waitFor(() => expect(canvas).toHaveAttribute("data-state", "ready"));
    expect(Number.parseInt(canvas.style.width, 10)).toBe(fittedWidth);
  });

  it("lets the keyboard reach a zoomed page without adding a dead tab stop when it fits", async () => {
    stageClientWidth = 700;
    stageScrollWidth = 700;
    const fixture = pdfDocument(1);
    loadingTask(fixture.document);
    render(<AgentPdfPreview
      blob={pdfBlob()}
      onStateChange={vi.fn()}
      title="synthetic-report.pdf"
      versionNumber={1}
    />);

    const canvas = await screen.findByRole("img", { name: "Rendered PDF page 1 of 1" });
    await waitFor(() => expect(canvas).toHaveAttribute("data-state", "ready"));
    const stage = screen.getByRole("group", { name: "Scrollable PDF page area" });
    expect(stage).not.toHaveAttribute("tabindex");
    expect(stage).toHaveAttribute("data-scrollable", "false");

    stageScrollWidth = 845;
    fireEvent.click(screen.getByRole("button", { name: "Zoom in PDF" }));
    await waitFor(() => expect(stage).toHaveAttribute("data-scrollable", "true"));
    expect(stage).toHaveAttribute("tabindex", "0");
    expect(previewCss).toMatch(/\.agent-pdf-preview__stage:focus-visible\s*\{[^}]*outline:/);
  });

  it("reaches a page that only overflows the stage vertically at the fitted width", async () => {
    stageClientWidth = 700;
    stageScrollWidth = 700;
    stageClientHeight = 520;
    stageScrollHeight = 900;
    loadingTask(pdfDocument(1).document);
    render(<AgentPdfPreview
      blob={pdfBlob()}
      onStateChange={vi.fn()}
      title="synthetic-report.pdf"
      versionNumber={1}
    />);

    const canvas = await screen.findByRole("img", { name: "Rendered PDF page 1 of 1" });
    await waitFor(() => expect(canvas).toHaveAttribute("data-state", "ready"));
    const stage = screen.getByRole("group", { name: "Scrollable PDF page area" });
    // The page fits the width it was fitted to, so only the vertical axis
    // scrolls. Without a tab stop the rest of that page is pointer-only.
    expect(stage).toHaveAttribute("data-scrollable", "true");
    expect(stage).toHaveAttribute("tabindex", "0");
    expect(screen.getByRole("button", { name: "Fit PDF page to viewer" })).toBeDisabled();

    stageScrollHeight = 500;
    await act(async () => { triggerStageResize(); });
    await waitFor(() => expect(stage).toHaveAttribute("data-scrollable", "false"));
    expect(stage).not.toHaveAttribute("tabindex");
  });

  it("adds the tab stop when the page box is committed, not when the render resolves", async () => {
    stageClientWidth = 700;
    stageScrollWidth = 700;
    const fixture = pdfDocument(1);
    loadingTask(fixture.document);
    render(<AgentPdfPreview
      blob={pdfBlob()}
      onStateChange={vi.fn()}
      title="synthetic-report.pdf"
      versionNumber={1}
    />);

    const canvas = await screen.findByRole("img", { name: "Rendered PDF page 1 of 1" });
    await waitFor(() => expect(canvas).toHaveAttribute("data-state", "ready"));
    const stage = screen.getByRole("group", { name: "Scrollable PDF page area" });
    expect(stage).toHaveAttribute("data-scrollable", "false");

    // A render in flight still holds the enlarged page box the stage scrolls,
    // so the keyboard must reach it before the pixels arrive.
    let releaseRender = (): void => undefined;
    fixture.render.mockImplementationOnce(() => ({
      cancel: vi.fn(),
      promise: new Promise<void>((resolve) => { releaseRender = () => { resolve(); }; }),
    }));
    stageScrollWidth = 845;
    fireEvent.click(screen.getByRole("button", { name: "Zoom in PDF" }));
    await waitFor(() => expect(stage).toHaveAttribute("data-scrollable", "true"));
    expect(canvas).toHaveAttribute("data-state", "loading");
    expect(stage).toHaveAttribute("tabindex", "0");

    await act(async () => { releaseRender(); });
    await waitFor(() => expect(canvas).toHaveAttribute("data-state", "ready"));
    expect(stage).toHaveAttribute("tabindex", "0");
  });

  it("bounds the canvas backing store instead of claiming a blank page was rendered", async () => {
    const fixture = pdfDocument(1, { height: 8000, width: 600 });
    loadingTask(fixture.document);
    render(<AgentPdfPreview
      blob={pdfBlob()}
      onStateChange={vi.fn()}
      title="synthetic-tall.pdf"
      versionNumber={1}
    />);

    const canvas = await screen.findByRole<HTMLCanvasElement>("img", { name: "Rendered PDF page 1 of 1" });
    await waitFor(() => expect(canvas).toHaveAttribute("data-state", "ready"));
    expect(canvas.width).toBeGreaterThan(0);
    expect(canvas.height).toBeGreaterThan(0);
    expect(canvas.width).toBeLessThanOrEqual(8192);
    expect(canvas.height).toBeLessThanOrEqual(8192);
    expect(canvas.width * canvas.height).toBeLessThanOrEqual(33_554_432);
    // The presented page still spans its full fitted height; only the backing
    // store was downscaled to a size the browser will actually allocate.
    expect(Number.parseInt(canvas.style.height, 10)).toBeGreaterThan(canvas.height);
  });

  it("fails closed when a page cannot fit any admissible canvas", async () => {
    const fixture = pdfDocument(1, { height: 400_000, width: 600 });
    loadingTask(fixture.document);
    const onStateChange = vi.fn();
    render(<AgentPdfPreview
      blob={pdfBlob()}
      onStateChange={onStateChange}
      title="synthetic-oversized.pdf"
      versionNumber={1}
    />);

    expect(await screen.findByRole("alert")).toHaveTextContent("could not be rendered safely");
    expect(onStateChange).toHaveBeenLastCalledWith("error");
    expect(fixture.render).not.toHaveBeenCalled();
  });

  it("releases a superseded page proxy on a page change but not on a zoom change", async () => {
    const fixture = pdfDocument(3);
    loadingTask(fixture.document);
    render(<AgentPdfPreview
      blob={pdfBlob()}
      onStateChange={vi.fn()}
      title="synthetic-report.pdf"
      versionNumber={1}
    />);

    await waitFor(() => expect(screen.getByRole("img", { name: "Rendered PDF page 1 of 3" }))
      .toHaveAttribute("data-state", "ready"));

    fireEvent.click(screen.getByRole("button", { name: "Zoom in PDF" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Fit PDF page to viewer" }))
      .toHaveTextContent("125%"));
    await waitFor(() => expect(screen.getByRole("img", { name: "Rendered PDF page 1 of 3" }))
      .toHaveAttribute("data-state", "ready"));
    expect(fixture.cleanup).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Next PDF page" }));
    await waitFor(() => expect(fixture.getPage).toHaveBeenLastCalledWith(2));
    await waitFor(() => expect(fixture.cleanup).toHaveBeenCalledTimes(1));
    expect(screen.getByRole("button", { name: "Fit PDF page to viewer" })).toHaveTextContent("125%");
  });
});
