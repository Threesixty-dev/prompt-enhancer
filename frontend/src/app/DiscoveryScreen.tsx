import type { PromptEnhancerTransport } from "../shared/api/contracts";
import type { AppRoute } from "../shared/platform/platform";
import { DiscoveryInbox } from "../features/discovery-inbox/DiscoveryInbox";
import { FirstRunPanel } from "../features/onboarding/FirstRunPanel";

/**
 * Keep the discovery-only onboarding and review workspace out of every route's
 * startup graph. App retains the route error boundary and Suspense fallback,
 * so a failed chunk remains retryable and never replaces the privacy shell.
 */
export function DiscoveryScreen({
  navigate,
  onUndecidedCountChange,
  transport,
}: {
  navigate: (route: AppRoute) => void;
  onUndecidedCountChange: (count: number) => void;
  transport: PromptEnhancerTransport;
}) {
  return (
    <>
      <FirstRunPanel navigate={navigate} transport={transport} />
      <DiscoveryInbox
        navigate={navigate}
        onUndecidedCountChange={onUndecidedCountChange}
        transport={transport}
      />
    </>
  );
}
