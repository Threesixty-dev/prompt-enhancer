import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  AnnotationMode,
  getDocument,
  GlobalWorkerOptions,
  RenderingCancelledException,
  type PDFDocumentLoadingTask,
  type PDFDocumentProxy,
  type PDFPageProxy,
  type RenderTask,
} from "pdfjs-dist";
import pdfWorkerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";

import "./AgentPdfPreview.css";

const MIN_ZOOM = 0.75;
const MAX_ZOOM = 2.5;
const ZOOM_STEP = 0.25;
const MIN_OUTPUT_SCALE = 0.1;
const MAX_OUTPUT_SCALE = 2;
const MAX_PDF_IMAGE_PIXELS = 33_554_432;
const MAX_CANVAS_DIMENSION = 8_192;
// Rendering a page resizes the canvas, which can add or remove the stage
// scrollbar and therefore change the measured stage width again. Ignoring
// sub-scrollbar jitter stops that feedback from cancelling and restarting the
// render a zoom or page step just began.
const STAGE_WIDTH_EPSILON = 8;
const STAGE_PADDING = 24;
// `clientWidth` reports the padding box rounded to the nearest pixel, so a stage
// that is really 699.6px wide reports 700. A page fitted to the rounded width
// overflows by that rounding error, which would hand a visibly fitted page a
// scroll port with nothing in it to reach. One pixel of slack keeps the fitted
// page inside the box the browser measures, so scrollability can be read from
// the browser directly instead of through a tolerance that disagrees with it.
const STAGE_FIT_SLACK = 1;

type PdfRenderPhase = "loading" | "ready" | "error";

GlobalWorkerOptions.workerSrc = pdfWorkerUrl;

// The fit basis is the scrollable viewport, not the page: a page zoomed past
// the fit keeps the same basis while the stage scrolls under it.
function stageFitWidth(stage: HTMLElement): number {
  return Math.max(240, Math.floor(stage.clientWidth || 720));
}

// Either axis leaves the page unreachable without a pointer: a page zoomed past
// the fitted width scrolls horizontally, and a page taller than the stage
// scrolls vertically even at the fitted width. This is the browser's own
// scrollability test — the one that decides whether arrow keys move the port —
// so the tab stop appears exactly when there is something to scroll.
function stageOverflows(stage: HTMLElement): boolean {
  return stage.scrollWidth > stage.clientWidth || stage.scrollHeight > stage.clientHeight;
}

// A canvas larger than the browser's backing-store limit is silently refused,
// which would leave a blank surface that still claimed to be a rendered page.
function boundedOutputScale(cssWidth: number, cssHeight: number): number {
  const limit = Math.min(
    MAX_CANVAS_DIMENSION / cssWidth,
    MAX_CANVAS_DIMENSION / cssHeight,
    Math.sqrt(MAX_PDF_IMAGE_PIXELS / (cssWidth * cssHeight)),
  );
  if (!Number.isFinite(limit) || limit < MIN_OUTPUT_SCALE) {
    throw new Error("pdf_page_exceeds_canvas_limit");
  }
  return Math.min(window.devicePixelRatio || 1, MAX_OUTPUT_SCALE, limit);
}

export function AgentPdfPreview({
  blob,
  onStateChange,
  title,
  versionNumber,
}: {
  blob: Blob;
  onStateChange: (phase: PdfRenderPhase) => void;
  title: string;
  versionNumber: number;
}) {
  const [documentProxy, setDocumentProxy] = useState<PDFDocumentProxy | null>(null);
  const [pageCount, setPageCount] = useState(0);
  const [pageNumber, setPageNumber] = useState(1);
  const [zoom, setZoom] = useState(1);
  const [phase, setPhase] = useState<PdfRenderPhase>("loading");
  const [message, setMessage] = useState("Reading the verified PDF structure…");
  const [stageWidth, setStageWidth] = useState(720);
  const [stageScrollable, setStageScrollable] = useState(false);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const stageRef = useRef<HTMLDivElement | null>(null);
  const stateCallbackRef = useRef(onStateChange);
  const renderedPageRef = useRef<{ page: PDFPageProxy; pageNumber: number } | null>(null);

  useEffect(() => {
    stateCallbackRef.current = onStateChange;
  }, [onStateChange]);

  const measureScrollable = useCallback(() => {
    const stage = stageRef.current;
    if (stage === null) return;
    setStageScrollable(stageOverflows(stage));
  }, []);

  const measureStage = useCallback(() => {
    const stage = stageRef.current;
    if (stage === null) return;
    const next = stageFitWidth(stage);
    setStageWidth((current) => (Math.abs(current - next) < STAGE_WIDTH_EPSILON ? current : next));
    measureScrollable();
  }, [measureScrollable]);

  // Any commit can change the page box, the notice height or both, and the
  // browser decides scrollability from the layout that results. Measuring in a
  // layout effect keeps the tab stop in step with the DOM the user is about to
  // see rather than with the render phase that produced it.
  useLayoutEffect(measureScrollable);

  useEffect(() => {
    const stage = stageRef.current;
    const canvas = canvasRef.current;
    if (stage === null) return;
    measureStage();
    if (typeof ResizeObserver !== "function") return;
    const observer = new ResizeObserver(measureStage);
    observer.observe(stage);
    // The stage box does not change when only the page inside it does, so the
    // rendered page is observed too: a scrollbar the surrounding dialog adds or
    // drops changes the stage, while a refitted page changes only the canvas,
    // and either one decides whether the keyboard can reach the page.
    if (canvas !== null) observer.observe(canvas);
    return () => observer.disconnect();
  }, [measureStage]);

  useEffect(() => {
    let cancelled = false;
    let loadingTask: PDFDocumentLoadingTask | null = null;
    renderedPageRef.current = null;
    setDocumentProxy(null);
    setPageCount(0);
    setPageNumber(1);
    setZoom(1);
    setPhase("loading");
    setMessage("Reading the verified PDF structure…");
    stateCallbackRef.current("loading");
    void (async () => {
      const data = new Uint8Array(await blob.arrayBuffer());
      if (cancelled) return;
      loadingTask = getDocument({
        data,
        disableAutoFetch: true,
        disableRange: true,
        disableStream: true,
        enableXfa: false,
        maxImageSize: MAX_PDF_IMAGE_PIXELS,
        stopAtErrors: true,
        useWasm: false,
        useWorkerFetch: false,
      });
      const loaded = await loadingTask.promise;
      if (cancelled) {
        await loadingTask.destroy();
        return;
      }
      if (loaded.numPages < 1 || loaded.numPages > 10_000) {
        await loadingTask.destroy();
        throw new Error("pdf_page_count_invalid");
      }
      setDocumentProxy(loaded);
      setPageCount(loaded.numPages);
      setMessage("Rendering page 1…");
    })().catch(() => {
      if (cancelled) return;
      setPhase("error");
      setMessage("This digest-verified PDF could not be parsed safely. It was not rendered, executed, or sent anywhere.");
      stateCallbackRef.current("error");
    });
    return () => {
      cancelled = true;
      renderedPageRef.current = null;
      // `destroy` releases the worker, its operator lists and every page proxy
      // this document handed out. A rejection here is a disposal detail of an
      // already-superseded document, not a viewer failure.
      if (loadingTask !== null) void loadingTask.destroy().catch(() => undefined);
    };
  }, [blob]);

  useEffect(() => {
    if (documentProxy === null) return;
    let cancelled = false;
    let renderTask: RenderTask | null = null;
    setPhase("loading");
    setMessage(`Rendering page ${pageNumber} of ${pageCount}…`);
    stateCallbackRef.current("loading");
    void (async () => {
      const page = await documentProxy.getPage(pageNumber);
      if (cancelled) return;
      const previous = renderedPageRef.current;
      if (previous !== null && previous.pageNumber !== pageNumber) {
        // Release the operator list and image objects the superseded page kept
        // so paging through a long document does not accumulate them.
        previous.page.cleanup?.();
      }
      renderedPageRef.current = { page, pageNumber };
      const baseViewport = page.getViewport({ scale: 1 });
      // The basis is read from the live scroll port instead of the measured
      // state that last survived the epsilon. Fitting to a width the stage no
      // longer has renders a page the next measurement must immediately
      // re-render, and between those two renders the stage overflows while the
      // keyboard affordance still describes the superseded page.
      const stage = stageRef.current;
      const fitBasis = stage === null ? stageWidth : stageFitWidth(stage);
      const fitScale = Math.max(0.1, (fitBasis - STAGE_PADDING - STAGE_FIT_SLACK) / baseViewport.width);
      const viewport = page.getViewport({ scale: fitScale * zoom });
      const canvas = canvasRef.current;
      if (canvas === null || canvas.getContext("2d", { alpha: false }) === null) {
        throw new Error("pdf_canvas_unavailable");
      }
      const cssWidth = Math.max(1, Math.floor(viewport.width));
      const cssHeight = Math.max(1, Math.floor(viewport.height));
      const outputScale = boundedOutputScale(cssWidth, cssHeight);
      const pixelWidth = Math.max(1, Math.floor(cssWidth * outputScale));
      const pixelHeight = Math.max(1, Math.floor(cssHeight * outputScale));
      canvas.width = pixelWidth;
      canvas.height = pixelHeight;
      if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) {
        throw new Error("pdf_canvas_allocation_rejected");
      }
      canvas.style.width = `${cssWidth}px`;
      canvas.style.height = `${cssHeight}px`;
      // The page box is committed here, before a single pixel is drawn, so the
      // stage already scrolls. Measuring now rather than after the render keeps
      // the tab stop from lagging the layout for the whole time a render — or a
      // render that supersedes it — is in flight.
      measureScrollable();
      renderTask = page.render({
        annotationMode: AnnotationMode.DISABLE,
        background: "#ffffff",
        canvas,
        transform: outputScale === 1 ? undefined : [outputScale, 0, 0, outputScale, 0, 0],
        viewport,
      });
      await renderTask.promise;
      if (cancelled) return;
      setPhase("ready");
      setMessage(`Page ${pageNumber} of ${pageCount} ready. Links, forms, scripts, audio, and annotations are not interactive.`);
      stateCallbackRef.current("ready");
    })().catch((error: unknown) => {
      if (cancelled || error instanceof RenderingCancelledException) return;
      setPhase("error");
      setMessage(`Page ${pageNumber} could not be rendered safely. The PDF stayed local and no substitute content was shown.`);
      stateCallbackRef.current("error");
    });
    return () => {
      cancelled = true;
      renderTask?.cancel();
    };
  }, [documentProxy, measureScrollable, pageCount, pageNumber, stageWidth, zoom]);

  return (
    <section
      aria-busy={phase === "loading"}
      aria-label={`PDF preview of ${title} v${versionNumber}`}
      className="agent-pdf-preview"
      data-state={phase}
    >
      <header className="agent-pdf-preview__toolbar">
        <span>
          <strong>PDF preview</strong>
          <small>Local canvas renderer · interactive document features omitted</small>
        </span>
        <div aria-label="PDF page controls" role="group">
          <button
            aria-label="Previous PDF page"
            className="button button--ghost"
            disabled={phase === "error" || pageNumber <= 1}
            onClick={() => setPageNumber((current) => Math.max(1, current - 1))}
            type="button"
          >Previous</button>
          <span aria-live="polite">{pageCount > 0 ? `${pageNumber} / ${pageCount}` : "— / —"}</span>
          <button
            aria-label="Next PDF page"
            className="button button--ghost"
            disabled={phase === "error" || pageCount === 0 || pageNumber >= pageCount}
            onClick={() => setPageNumber((current) => Math.min(pageCount, current + 1))}
            type="button"
          >Next</button>
        </div>
        <div aria-label={`PDF zoom, ${Math.round(zoom * 100)} percent`} role="group">
          <button
            aria-label="Zoom out PDF"
            className="button button--ghost"
            disabled={phase === "error" || zoom <= MIN_ZOOM}
            onClick={() => setZoom((current) => Math.max(MIN_ZOOM, current - ZOOM_STEP))}
            type="button"
          >−</button>
          <button
            aria-label="Fit PDF page to viewer"
            className="button button--ghost"
            disabled={phase === "error" || zoom === 1}
            onClick={() => setZoom(1)}
            type="button"
          >Fit · {Math.round(zoom * 100)}%</button>
          <button
            aria-label="Zoom in PDF"
            className="button button--ghost"
            disabled={phase === "error" || zoom >= MAX_ZOOM}
            onClick={() => setZoom((current) => Math.min(MAX_ZOOM, current + ZOOM_STEP))}
            type="button"
          >+</button>
        </div>
      </header>
      {/* A page wider or taller than the stage is only reachable by pointer
          unless the scroll port itself can take focus, and a stage that scrolls
          in neither axis must not add a dead tab stop. */}
      <div
        aria-label="Scrollable PDF page area"
        className="agent-pdf-preview__stage"
        data-scrollable={stageScrollable}
        ref={stageRef}
        role="group"
        tabIndex={stageScrollable ? 0 : undefined}
      >
        {/* A live region that changes role in place is announced unreliably, so
            the failure notice is mounted as its own alert node. */}
        <p
          className={phase === "error" ? "agent-pdf-preview__state agent-pdf-preview__state--error" : "agent-pdf-preview__state"}
          key={phase === "error" ? "pdf-state-alert" : "pdf-state-status"}
          role={phase === "error" ? "alert" : "status"}
        >{message}</p>
        <canvas
          aria-label={`Rendered PDF page ${pageNumber} of ${Math.max(pageCount, 1)}`}
          className="agent-pdf-preview__canvas"
          data-state={phase}
          ref={canvasRef}
          role="img"
        />
      </div>
    </section>
  );
}
