import { useEffect, useId, useRef, type ReactNode } from "react";
import { Icon } from "./Icon";

const FOCUSABLE = [
  "a[href]",
  "button:not(:disabled)",
  "input:not(:disabled)",
  "select:not(:disabled)",
  "textarea:not(:disabled)",
  "summary",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

/**
 * Modal dialog primitive: `role="dialog"`, `aria-modal`, labelled by its title,
 * described by an optional description, focus trapped inside, Escape closes,
 * and focus returns to the opener on close. It renders nothing while closed so
 * it can never reserve or shift layout, and the panel is a fixed viewport
 * overlay so opening it never reflows the surface beneath it.
 */
export function Dialog({
  open,
  title,
  description,
  onClose,
  children,
  footer,
  tone = "neutral",
  closeLabel = "Close dialog",
  initialFocusRef,
}: {
  open: boolean;
  title: string;
  description?: ReactNode;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  tone?: "neutral" | "danger";
  closeLabel?: string;
  initialFocusRef?: React.RefObject<HTMLElement | null>;
}) {
  const titleId = useId();
  const descriptionId = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  // Latest handlers live in refs so re-renders while open (for example a
  // simulated transfer tick behind the dialog) never re-run focus management
  // and yank focus back to the initial control.
  const onCloseRef = useRef(onClose);
  const initialFocusRefRef = useRef(initialFocusRef);
  useEffect(() => {
    onCloseRef.current = onClose;
    initialFocusRefRef.current = initialFocusRef;
  });

  useEffect(() => {
    if (!open) return undefined;
    const previous = document.activeElement as HTMLElement | null;
    const panel = panelRef.current;
    const initial = initialFocusRefRef.current?.current ?? closeRef.current;
    initial?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab" || panel === null) return;
      const focusable = [...panel.querySelectorAll<HTMLElement>(FOCUSABLE)];
      if (focusable.length === 0) {
        event.preventDefault();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      if (event.shiftKey && (active === first || !panel.contains(active))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (active === last || !panel.contains(active))) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      previous?.focus();
    };
  }, [open]);

  if (!open) return null;
  return (
    <div className="ui-dialog" data-tone={tone}>
      <div aria-hidden="true" className="ui-dialog__scrim" onClick={onClose} />
      <div
        aria-describedby={description === undefined ? undefined : descriptionId}
        aria-labelledby={titleId}
        aria-modal="true"
        className="ui-dialog__panel"
        ref={panelRef}
        role="dialog"
      >
        <header className="ui-dialog__header">
          <h2 id={titleId}>{title}</h2>
          <button
            aria-label={closeLabel}
            className="ui-dialog__close"
            onClick={onClose}
            ref={closeRef}
            type="button"
          >
            <Icon name="x" />
          </button>
        </header>
        {description !== undefined && (
          <p className="ui-dialog__description" id={descriptionId}>{description}</p>
        )}
        <div className="ui-dialog__body">{children}</div>
        {footer !== undefined && <footer className="ui-dialog__footer">{footer}</footer>}
      </div>
    </div>
  );
}
