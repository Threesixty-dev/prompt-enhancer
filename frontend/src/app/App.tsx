import { useEffect, useState } from "react";
import type { PromptEnhancerTransport } from "../shared/api/contracts";
import type { AppRoute, PlatformAdapter } from "../shared/platform/platform";
import { DiscoveryInbox } from "../features/discovery-inbox/DiscoveryInbox";
import { LocalSources } from "../features/local-sources/LocalSources";
import { TaskDetail } from "../features/task-detail/TaskDetail";
import { Icon } from "../shared/ui/Icon";

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
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
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
              <span>Local sources</span>
            </button>
          )}
          <button aria-disabled="true" className="primary-nav__item--future" disabled type="button">
            <Icon name="layers" />
            <span>Metric catalog</span>
            <small>Later</small>
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

      <div className="workspace">
        <header className="topbar">
          <div className="topbar__trail">
            <span>Personal workspace</span>
            <Icon name="chevron" />
            <strong>
              {route.name === "discovery"
                ? "Discovery"
                : route.name === "local_sources"
                  ? "Local sources"
                  : "Task analysis"}
            </strong>
          </div>
          <div className="topbar__right">
            <span className="mode-chip"><span /> {mode === "synthetic" ? "Synthetic preview" : "Local mode"}</span>
            <span className="avatar" aria-label="Local profile">L</span>
          </div>
        </header>
        <p aria-live="polite" className="sr-only">{navigationNotice}</p>
        {navigationNotice && <div className="navigation-notice" role="status">{navigationNotice}</div>}
        <main id="main-content">
          {route.name === "discovery" ? (
            <DiscoveryInbox
              navigate={navigate}
              onUndecidedCountChange={setUndecidedCount}
              transport={transport}
            />
          ) : route.name === "local_sources" ? (
            mode === "local" ? (
              <LocalSources transport={transport} />
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
