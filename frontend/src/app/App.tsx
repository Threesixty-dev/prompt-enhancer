import { useEffect, useState } from "react";
import type { PromptEnhancerTransport } from "../shared/api/contracts";
import type { AppRoute, PlatformAdapter } from "../shared/platform/platform";
import type {
  RuntimeComposition,
  RuntimeDataMode,
  RuntimeServiceState,
} from "../shared/platform/runtimeMode";
import { DiscoveryInbox } from "../features/discovery-inbox/DiscoveryInbox";
import { AnalysisJobCentre } from "../features/analysis-job-centre";
import { LocalSources } from "../features/local-sources/LocalSources";
import { ProjectCatalog } from "../features/project-catalog";
import { ProjectAutomationSettings } from "../features/project-automation";
import {
  ProjectWorkspace,
  type ProjectWorkspaceRoute,
} from "../features/project-workspace";
import { TaskDetail } from "../features/task-detail/TaskDetail";
import { ResearchLab } from "../features/research-lab";
import { Icon } from "../shared/ui/Icon";

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
  if (route.name === "research") return "Methods & models";
  if (isProjectWorkspaceRoute(route)) return "Project workspace";
  return "Task analysis";
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
}: {
  platform: PlatformAdapter;
  runtime: RuntimeComposition;
}) {
  const transport: PromptEnhancerTransport = runtime.transport;
  const [route, setRoute] = useState<AppRoute>(() => platform.currentRoute());
  const [navigationNotice, setNavigationNotice] = useState("");
  const [undecidedCount, setUndecidedCount] = useState<number | null>(null);
  const [serviceState, setServiceState] = useState<RuntimeServiceState>(() =>
    runtime.mode === "synthetic_demo" ? "available" : "checking",
  );
  const runtimeCopy = runtimeStatusCopy(runtime.mode, serviceState);

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
            <span>Personal workspace</span>
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
          {route.name === "discovery" ? (
            <DiscoveryInbox
              navigate={navigate}
              onUndecidedCountChange={setUndecidedCount}
              transport={transport}
            />
          ) : route.name === "projects" ? (
            <ProjectCatalog navigate={navigate} transport={transport} />
          ) : route.name === "project_automation" ? (
            <ProjectAutomationSettings
              navigate={navigate}
              projectId={route.projectId}
              runtimeMode={runtime.mode}
              serviceState={serviceState}
              transport={transport}
            />
          ) : isProjectWorkspaceRoute(route) ? (
            <ProjectWorkspace
              navigate={navigate}
              route={route}
              transport={transport}
            />
          ) : route.name === "local_sources" ? (
            runtime.mode === "local_real" ? (
              <LocalSources navigate={navigate} transport={transport} />
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
            <AnalysisJobCentre
              runtimeMode={runtime.mode}
              serviceState={serviceState}
              transport={transport}
            />
          ) : route.name === "research" ? (
            <ResearchLab transport={transport} />
          ) : (
            <TaskDetail
              navigate={navigate}
              revision={route.revision}
              taskId={route.taskId}
              transport={transport}
            />
          )}
        </main>
      </div>
    </div>
  );
}
