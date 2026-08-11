import { useEffect, useState } from "react";
import type { PromptEnhancerTransport } from "../shared/api/contracts";
import type { AppRoute, PlatformAdapter } from "../shared/platform/platform";
import { DiscoveryInbox } from "../features/discovery-inbox/DiscoveryInbox";
import { LocalSources } from "../features/local-sources/LocalSources";
import { ProjectCatalog } from "../features/project-catalog";
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
  if (route.name === "projects") return "Projects";
  if (route.name === "research") return "Methods & models";
  if (isProjectWorkspaceRoute(route)) return "Project workspace";
  return "Task analysis";
}

export function App({
  transport,
  platform,
  mode,
}: {
  transport: PromptEnhancerTransport;
  platform: PlatformAdapter;
  mode: "synthetic" | "local";
}) {
  const [route, setRoute] = useState<AppRoute>(() => platform.currentRoute());
  const [navigationNotice, setNavigationNotice] = useState("");
  const [undecidedCount, setUndecidedCount] = useState<number | null>(null);

  useEffect(() => platform.subscribe(setRoute), [platform]);

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
              route.name === "projects" || isProjectWorkspaceRoute(route)
                ? "page"
                : undefined
            }
            className={
              route.name === "projects" || isProjectWorkspaceRoute(route)
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
          {mode === "local" && (
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
              <span>{mode === "synthetic" ? "Fictional fixture mode" : "Loopback connection"}</span>
            </div>
            <span className="online-dot" aria-label="Local service available" />
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
            <span className="mode-chip"><span /> {mode === "synthetic" ? "Synthetic preview" : "Local mode"}</span>
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
          ) : isProjectWorkspaceRoute(route) ? (
            <ProjectWorkspace
              navigate={navigate}
              route={route}
              transport={transport}
            />
          ) : route.name === "local_sources" ? (
            mode === "local" ? (
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
