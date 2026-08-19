import { FirstRunPanel } from "../features/onboarding/FirstRunPanel";
import {
  Component,
  Suspense,
  lazy,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { PromptEnhancerTransport, Provider } from "../shared/api/contracts";
import type { TeamControlPlanePort } from "../shared/api/teamControlPlane";
import { composeTeamControlPlanePort } from "../shared/api/teamControlPlaneRuntime";
import type { SocialHubPort } from "../shared/api/socialHubSchema";
import { composeSocialHubPort } from "../shared/api/socialHubRuntime";
import type { AppRoute, PlatformAdapter } from "../shared/platform/platform";
import { routePath } from "../shared/platform/platform";
import type {
  RuntimeComposition,
  RuntimeDataMode,
  RuntimeServiceState,
} from "../shared/platform/runtimeMode";
import { DiscoveryInbox } from "../features/discovery-inbox/DiscoveryInbox";
import type { ProjectWorkspaceRoute } from "../features/project-workspace";
import { Icon } from "../shared/ui/Icon";
import { LoadingState } from "../shared/ui/AsyncState";

const AnalysisJobCentreScreen = lazy(() =>
  import("../features/analysis-job-centre").then((module) => ({
    default: module.AnalysisJobCentre,
  })),
);
const LocalSourcesScreen = lazy(() =>
  import("../features/local-sources/LocalSources").then((module) => ({
    default: module.LocalSources,
  })),
);
const SessionsScreen = lazy(() =>
  import("../features/session-catalog/SessionsPage").then((module) => ({ default: module.SessionsPage })),
);
const CalibrationScreen = lazy(() =>
  import("../features/calibration/CalibrationPage").then((module) => ({ default: module.CalibrationPage })),
);
const LiveMiniWindowScreen = lazy(() =>
  import("../features/live-window/LiveMiniWindow").then((module) => ({ default: module.LiveMiniWindow })),
);
const ProjectCatalogScreen = lazy(() =>
  import("../features/project-catalog").then((module) => ({
    default: module.ProjectCatalog,
  })),
);
const ProjectAutomationScreen = lazy(() =>
  import("../features/project-automation").then((module) => ({
    default: module.ProjectAutomationSettings,
  })),
);
const ProjectWorkspaceScreen = lazy(() =>
  import("../features/project-workspace").then((module) => ({
    default: module.ProjectWorkspace,
  })),
);
const ResearchLabScreen = lazy(() =>
  import("../features/research-lab").then((module) => ({
    default: module.ResearchLab,
  })),
);
const TaskDetailScreen = lazy(() =>
  import("../features/task-detail/TaskDetail").then((module) => ({
    default: module.TaskDetail,
  })),
);
const TeamAnalyticsScreen = lazy(() =>
  import("../features/team-analytics").then((module) => ({
    default: module.TeamAnalyticsPage,
  })),
);
const TaskFlowScreen = lazy(() =>
  import("../features/task-flow").then((module) => ({
    default: module.TaskFlowPage,
  })),
);
const SocialHubScreen = lazy(() =>
  import("../features/social").then((module) => ({
    default: module.SocialHubPage,
  })),
);

interface RouteErrorBoundaryProps {
  children: ReactNode;
  onExit: () => void;
  resetKey: string;
}

interface RouteErrorBoundaryState {
  failed: boolean;
  resetKey: string;
}

/** Keep a failed route bundle from taking down the runtime/privacy shell. */
export class RouteErrorBoundary extends Component<
  RouteErrorBoundaryProps,
  RouteErrorBoundaryState
> {
  constructor(props: RouteErrorBoundaryProps) {
    super(props);
    this.state = { failed: false, resetKey: props.resetKey };
  }

  static getDerivedStateFromError(): Partial<RouteErrorBoundaryState> {
    return { failed: true };
  }

  static getDerivedStateFromProps(
    props: RouteErrorBoundaryProps,
    state: RouteErrorBoundaryState,
  ): Partial<RouteErrorBoundaryState> | null {
    if (props.resetKey !== state.resetKey) {
      return { failed: false, resetKey: props.resetKey };
    }
    return null;
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="async-state async-state--error" role="alert">
        <span className="async-state__icon"><Icon name="x" /></span>
        <div>
          <strong>This screen could not be loaded</strong>
          <p>
            Its local route bundle failed safely. No provider error or session content is shown.
          </p>
        </div>
        <button
          className="button button--secondary"
          onClick={this.props.onExit}
          type="button"
        >
          Return to Discovery
        </button>
      </div>
    );
  }
}

function isProjectWorkspaceRoute(route: AppRoute): route is ProjectWorkspaceRoute {
  return (
    route.name === "project_overview" ||
    route.name === "project_sessions" ||
    route.name === "project_metrics" ||
    route.name === "session_metrics"
  );
}

function routeTitle(route: AppRoute): string {
  if (route.name === "discovery") return "Discovery";
  if (route.name === "local_sources") return "Data source";
  if (route.name === "analysis_jobs") return "Analysis jobs";
  if (route.name === "project_automation") return "Project automation";
  if (route.name === "projects") return "Projects";
  if (route.name === "sessions") return "Sessions";
  if (route.name === "calibration") return "Calibration";
  if (route.name === "live") return "Live";
  if (route.name === "research") return "Methods & models";
  if (route.name === "team") return "Team analytics";
  if (route.name === "social") return "Social hub";
  if (route.name === "task_flow") return "Task flow";
  if (isProjectWorkspaceRoute(route)) return "Project workspace";
  return "Task analysis";
}

function workspaceTrail(route: AppRoute): string {
  if (route.name === "team") return "Scoped workspace";
  if (route.name === "social") return "Social workspace";
  return "Personal workspace";
}

function RouteLoading({ route }: { route: AppRoute }) {
  return <LoadingState label={`Loading ${routeTitle(route)}…`} />;
}

function runtimeStatusCopy(
  mode: RuntimeDataMode,
  serviceState: RuntimeServiceState,
): {
  chip: string;
  detail: string;
  indicator: string;
} {
  if (mode === "synthetic_demo") {
    return {
      chip: "Synthetic demo · Fixture ready",
      detail: "Fictional in-memory fixtures",
      indicator: "Synthetic demo fixture ready",
    };
  }
  if (serviceState === "checking") {
    return {
      chip: "Local real · Checking service",
      detail: "Checking loopback service",
      indicator: "Local loopback service is being checked",
    };
  }
  if (serviceState === "available") {
    return {
      chip: "Local real · Service available",
      detail: "Loopback service available",
      indicator: "Local loopback service available",
    };
  }
  return {
    chip: "Local real · Service unavailable",
    detail: "Loopback service unavailable",
    indicator: "Local loopback service unavailable",
  };
}

export function App({
  platform,
  runtime,
  teamControlPlane,
  socialHub,
}: {
  platform: PlatformAdapter;
  runtime: RuntimeComposition;
  /** Defaults to the honest port for the runtime: fixture in synthetic demo, unavailable in local real. */
  teamControlPlane?: TeamControlPlanePort;
  /** Defaults to the honest social port for the runtime; a fixture can never cross into local real. */
  socialHub?: SocialHubPort;
}) {
  const transport: PromptEnhancerTransport = runtime.transport;
  const teamPort = useMemo(
    () => composeTeamControlPlanePort(runtime.mode, teamControlPlane),
    [runtime.mode, teamControlPlane],
  );
  const socialPort = useMemo(
    () => composeSocialHubPort(runtime.mode, socialHub),
    [runtime.mode, socialHub],
  );
  const [route, setRoute] = useState<AppRoute>(() => platform.currentRoute());
  const [navigationNotice, setNavigationNotice] = useState("");
  const [undecidedCount, setUndecidedCount] = useState<number | null>(null);
  const [serviceState, setServiceState] = useState<RuntimeServiceState>(() =>
    runtime.mode === "synthetic_demo" ? "available" : "checking",
  );
  const runtimeCopy = runtimeStatusCopy(runtime.mode, serviceState);
  const coverageProvider: Provider =
    runtime.mode === "synthetic_demo" ? "synthetic" : "codex";

  useEffect(() => platform.subscribe(setRoute), [platform]);

  useEffect(() => {
    if (runtime.mode === "synthetic_demo") {
      setServiceState("available");
      return;
    }
    const controller = new AbortController();
    setServiceState("checking");
    void runtime.transport
      .getRuntimeHealth(controller.signal)
      .then(() => {
        if (!controller.signal.aborted) setServiceState("available");
      })
      .catch(() => {
        if (!controller.signal.aborted) setServiceState("unavailable");
      });
    return () => controller.abort();
  }, [runtime]);

  function navigate(next: AppRoute) {
    platform.navigate(next);
  }

  async function openLatestTask() {
    setNavigationNotice("");
    try {
      const response = await transport.listTaskRevisions();
      const latest = response.tasks[0];
      if (!latest) {
        setNavigationNotice("No reviewed task is available yet.");
        return;
      }
      navigate({ name: "task", taskId: latest.task_id, revision: latest.revision });
    } catch {
      setNavigationNotice("The task index could not be loaded.");
    }
  }

  if (route.name === "live") {
    // Chrome-less mini window: no sidebar, no header - just the live view.
    return (
      <div className="app-shell app-shell--live" data-layout="live-window">
        <main id="main-content" tabIndex={-1}>
          <RouteErrorBoundary onExit={() => navigate({ name: "discovery" })} resetKey={routePath(route)}>
            <Suspense fallback={<RouteLoading route={route} />}>
              <LiveMiniWindowScreen projectId={route.projectId} sessionId={route.sessionId} transport={transport} />
            </Suspense>
          </RouteErrorBoundary>
        </main>
      </div>
    );
  }

  return (
    <div className="app-shell" data-layout="responsive-shell">
      <a className="skip-link" href="#main-content">Skip to dashboard</a>
      <aside aria-label="Application" className="sidebar">
        <div aria-label="Prompt Enhancer" className="brand">
          <span className="brand__mark" aria-hidden="true">
            <span />
            <span />
            <span />
          </span>
          <span>
            <strong>Prompt</strong>
            <small>Enhancer</small>
          </span>
        </div>

        <nav aria-label="Primary" className="primary-nav">
          <p>Workspace</p>
          <button
            aria-current={
              route.name === "projects" || route.name === "project_automation" ||
                isProjectWorkspaceRoute(route)
                ? "page"
                : undefined
            }
            className={
              route.name === "projects" || route.name === "project_automation" ||
                isProjectWorkspaceRoute(route)
                ? "primary-nav__item--active"
                : ""
            }
            onClick={() => navigate({ name: "projects" })}
            type="button"
          >
            <Icon name="layers" />
            <span>Projects</span>
          </button>
          <button
            aria-current={route.name === "sessions" ? "page" : undefined}
            className={route.name === "sessions" ? "primary-nav__item--active" : ""}
            onClick={() => navigate({ name: "sessions" })}
            type="button"
          >
            <Icon name="clock" />
            <span>Sessions</span>
          </button>
          <button
            aria-current={route.name === "calibration" ? "page" : undefined}
            className={route.name === "calibration" ? "primary-nav__item--active" : ""}
            onClick={() => navigate({ name: "calibration" })}
            type="button"
          >
            <Icon name="check" />
            <span>Calibration</span>
          </button>
          <button
            aria-current={route.name === "discovery" ? "page" : undefined}
            className={route.name === "discovery" ? "primary-nav__item--active" : ""}
            onClick={() => navigate({ name: "discovery" })}
            type="button"
          >
            <Icon name="branch" />
            <span>Discovery</span>
            {undecidedCount !== null && (
              <span
                className="nav-indicator"
                aria-label={`${undecidedCount} ${undecidedCount === 1 ? "candidate needs" : "candidates need"} review`}
              >
                {undecidedCount}
              </span>
            )}
          </button>
          <button
            aria-current={route.name === "task" ? "page" : undefined}
            className={route.name === "task" ? "primary-nav__item--active" : ""}
            onClick={() => void openLatestTask()}
            type="button"
          >
            <Icon name="tasks" />
            <span>Reviewed tasks</span>
          </button>
          <button
            aria-current={route.name === "task_flow" ? "page" : undefined}
            className={route.name === "task_flow" ? "primary-nav__item--active" : ""}
            onClick={() => navigate({ name: "task_flow" })}
            type="button"
          >
            <Icon name="board" />
            <span>Task flow</span>
          </button>
          <button
            aria-current={route.name === "team" ? "page" : undefined}
            className={route.name === "team" ? "primary-nav__item--active" : ""}
            onClick={() => navigate({ name: "team" })}
            type="button"
          >
            <Icon name="users" />
            <span>Team analytics</span>
          </button>
          <button
            aria-current={route.name === "social" ? "page" : undefined}
            className={route.name === "social" ? "primary-nav__item--active" : ""}
            onClick={() => navigate({ name: "social" })}
            type="button"
          >
            <Icon name="chat" />
            <span>Social</span>
          </button>
          {runtime.mode === "local_real" && (
            <button
              aria-current={route.name === "local_sources" ? "page" : undefined}
              className={route.name === "local_sources" ? "primary-nav__item--active" : ""}
              onClick={() => navigate({ name: "local_sources" })}
              type="button"
            >
              <Icon name="layers" />
              <span>Data source</span>
            </button>
          )}
          <button
            aria-current={route.name === "analysis_jobs" ? "page" : undefined}
            className={route.name === "analysis_jobs" ? "primary-nav__item--active" : ""}
            onClick={() => navigate({ name: "analysis_jobs" })}
            type="button"
          >
            <Icon name="activity" />
            <span>Job centre</span>
          </button>
          <button
            aria-current={route.name === "research" ? "page" : undefined}
            className={route.name === "research" ? "primary-nav__item--active" : ""}
            onClick={() => navigate({ name: "research" })}
            type="button"
          >
            <Icon name="layers" />
            <span>Methods & models</span>
          </button>
        </nav>

        <div className="sidebar__footer">
          <div className="privacy-status">
            <span className="privacy-status__icon"><Icon name="lock" /></span>
            <div>
              <strong>Private by default</strong>
              <span>{runtimeCopy.detail}</span>
            </div>
            <span
              aria-label={runtimeCopy.indicator}
              className={`online-dot online-dot--${serviceState}`}
            />
          </div>
          <p>No remote analytics - no content export</p>
        </div>
      </aside>

      <div className="workspace" data-route={route.name}>
        <header className="topbar">
          <div aria-label="Current location" className="topbar__trail">
            <span>{workspaceTrail(route)}</span>
            <Icon name="chevron" />
            <strong>{routeTitle(route)}</strong>
          </div>
          <div className="topbar__right">
            <span
              aria-label={`Runtime status: ${runtimeCopy.indicator}`}
              aria-live="polite"
              className="mode-chip"
              data-service-state={serviceState}
            >
              <span /> {runtimeCopy.chip}
            </span>
            <span className="avatar" aria-label="Local profile">L</span>
          </div>
        </header>
        <p aria-live="polite" className="sr-only">{navigationNotice}</p>
        {navigationNotice && <div className="navigation-notice" role="status">{navigationNotice}</div>}
        <main id="main-content" tabIndex={-1}>
          <RouteErrorBoundary
            onExit={() => navigate({ name: "discovery" })}
            resetKey={routePath(route)}
          >
            <Suspense fallback={<RouteLoading route={route} />}>
              {route.name === "discovery" ? (
                <>
                  <FirstRunPanel navigate={navigate} transport={transport} />
                  <DiscoveryInbox
                    navigate={navigate}
                    onUndecidedCountChange={setUndecidedCount}
                    transport={transport}
                  />
                </>
              ) : route.name === "sessions" ? (
                <SessionsScreen navigate={navigate} transport={transport} />
              ) : route.name === "calibration" ? (
                <CalibrationScreen transport={transport} />
              ) : route.name === "projects" ? (
                <ProjectCatalogScreen
                  coverageProvider={coverageProvider}
                  navigate={navigate}
                  transport={transport}
                />
              ) : route.name === "project_automation" ? (
                <ProjectAutomationScreen
                  navigate={navigate}
                  projectId={route.projectId}
                  runtimeMode={runtime.mode}
                  serviceState={serviceState}
                  transport={transport}
                />
              ) : isProjectWorkspaceRoute(route) ? (
                <ProjectWorkspaceScreen
                  coverageProvider={coverageProvider}
                  navigate={navigate}
                  route={route}
                  transport={transport}
                />
              ) : route.name === "local_sources" ? (
                runtime.mode === "local_real" ? (
                  <LocalSourcesScreen navigate={navigate} transport={transport} />
                ) : (
                  <section className="local-sources-page">
                    <div className="async-state" role="status">
                      <span className="privacy-status__icon"><Icon name="lock" /></span>
                      <strong>Local sources are disabled in synthetic preview</strong>
                      <span>
                        Run the integrated loopback build to grant and inspect local-source access.
                      </span>
                      <button
                        className="button button--secondary"
                        onClick={() => navigate({ name: "discovery" })}
                        type="button"
                      >
                        Return to Discovery
                      </button>
                    </div>
                  </section>
                )
              ) : route.name === "analysis_jobs" ? (
                <AnalysisJobCentreScreen
                  runtimeMode={runtime.mode}
                  serviceState={serviceState}
                  transport={transport}
                />
              ) : route.name === "research" ? (
                <ResearchLabScreen transport={transport} />
              ) : route.name === "team" ? (
                <TeamAnalyticsScreen
                  navigate={navigate}
                  port={teamPort}
                  runtimeMode={runtime.mode}
                  serviceState={serviceState}
                />
              ) : route.name === "social" ? (
                <SocialHubScreen port={socialPort} runtimeMode={runtime.mode} />
              ) : route.name === "task_flow" ? (
                <TaskFlowScreen
                  navigate={navigate}
                  runtimeMode={runtime.mode}
                  transport={transport}
                />
              ) : (
                <TaskDetailScreen
                  navigate={navigate}
                  revision={route.revision}
                  taskId={route.taskId}
                  transport={transport}
                />
              )}
            </Suspense>
          </RouteErrorBoundary>
        </main>
      </div>
    </div>
  );
}
