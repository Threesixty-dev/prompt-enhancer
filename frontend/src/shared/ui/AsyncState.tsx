import { Icon } from "./Icon";

export function LoadingState({ label }: { label: string }) {
  return (
    <div aria-busy="true" aria-live="polite" className="async-state">
      <span className="spinner" />
      <p>{label}</p>
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="async-state async-state--error" role="alert">
      <span className="async-state__icon">
        <Icon name="x" />
      </span>
      <div>
        <strong>Something needs attention</strong>
        <p>{message}</p>
      </div>
      {onRetry && (
        <button className="button button--secondary" onClick={onRetry} type="button">
          Try again
        </button>
      )}
    </div>
  );
}
