import {
  Component,
  Suspense,
  lazy,
  useMemo,
  useState,
  type ComponentProps,
  type ComponentType,
  type ReactNode,
} from "react";
import { ErrorState, LoadingState } from "./AsyncState";

type FeatureFailureBoundaryProps = {
  children: ReactNode;
  label: string;
  onRetry: () => void;
  resetKey: unknown;
};

type FeatureFailureKind = "download" | "render" | null;
type FeatureFailureBoundaryState = { failure: FeatureFailureKind };

// Browser ESM module failures can remain cached for the document lifetime.
// Keep this private so callers cannot misclassify arbitrary render failures.
class DeferredFeatureLoadError extends Error {}

/** Keeps an optional feature's chunk failure contained to that feature. */
class FeatureFailureBoundary extends Component<FeatureFailureBoundaryProps, FeatureFailureBoundaryState> {
  state: FeatureFailureBoundaryState = { failure: null };

  static getDerivedStateFromError(error: unknown): FeatureFailureBoundaryState {
    return { failure: error instanceof DeferredFeatureLoadError ? "download" : "render" };
  }

  componentDidUpdate(previous: FeatureFailureBoundaryProps) {
    if (this.state.failure !== null && previous.resetKey !== this.props.resetKey) {
      this.setState({ failure: null });
    }
  }

  render() {
    if (this.state.failure === "download") {
      return (
        <ErrorState
          message={`The optional ${this.props.label} download did not finish.`}
          recovery="preserve-work-before-reload"
          title={`Unable to load ${this.props.label}.`}
        />
      );
    }
    if (this.state.failure === "render") {
      return (
        <ErrorState
          actionLabel={`Retry ${this.props.label}`}
          message={`The optional ${this.props.label} surface did not finish loading. Check any action you already started before retrying.`}
          onRetry={this.props.onRetry}
          title={`Unable to load ${this.props.label}.`}
        />
      );
    }
    return this.props.children;
  }
}

/**
 * Lazily renders one optional feature without allowing a rejected chunk to
 * unmount the surrounding workspace. A render failure can retry only this
 * feature. A failed module download is contained but requires an explicit app
 * reload because browsers may cache that failed ESM import for the document.
 */
export function RetryableLazyFeature<T extends ComponentType<any>>({
  children,
  label,
  load,
}: {
  children: (Feature: ComponentType<ComponentProps<T>>) => ReactNode;
  label: string;
  load: () => Promise<{ default: T }>;
}) {
  const [attempt, setAttempt] = useState(0);
  const Feature = useMemo(
    () => lazy(() => load().catch(() => { throw new DeferredFeatureLoadError(); })) as ComponentType<ComponentProps<T>>,
    [attempt, load],
  );

  return (
    <FeatureFailureBoundary key={attempt} label={label} onRetry={() => setAttempt((value) => value + 1)} resetKey={load}>
      <Suspense fallback={<LoadingState label={`Loading ${label}…`} />}>
        {children(Feature)}
      </Suspense>
    </FeatureFailureBoundary>
  );
}
