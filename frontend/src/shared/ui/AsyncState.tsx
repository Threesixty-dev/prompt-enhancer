import { Icon } from "./Icon";

export function LoadingState({ label }: { label: string }) {
  return (
    <div aria-atomic="true" aria-live="polite" className="async-state" role="status">
      <span aria-hidden="true" className="spinner" />
      <p>{label}</p>
    </div>
  );
}

type ErrorStateRecovery =
  | {
    actionLabel?: string;
    onRetry: () => void;
    recovery?: never;
  }
  | {
    actionLabel?: never;
    onRetry?: never;
    recovery: "preserve-work-before-reload";
  };

export function ErrorState({
  message,
  onRetry,
  recovery,
  title = "Something needs attention",
  actionLabel,
}: {
  message: string;
  title?: string;
} & ErrorStateRecovery) {
  return (
    <div className="async-state async-state--error" role="alert">
      <span className="async-state__icon">
        <Icon name="x" />
      </span>
      <div>
        <strong>{title}</strong>
        <p>{message}</p>
        {recovery === "preserve-work-before-reload" && (
          <p>Preserve or copy unsent drafts and unsaved file work before explicitly reloading the app.</p>
        )}
      </div>
      {onRetry && (
        <button className="button button--secondary" onClick={onRetry} type="button">
          {actionLabel ?? "Try again"}
        </button>
      )}
    </div>
  );
}
