import { useEffect, useMemo, useRef, useState } from "react";
import { ProviderBadge, providersOf } from "../../shared/ui/ProviderBadge";
import type {
  CodexSession,
  PromptEnhancerTransport,
  Provider,
} from "../../shared/api/contracts";
import { TransportError } from "../../shared/api/httpTransport";
import type { AppRoute } from "../../shared/platform/platform";
import { isPseudonym } from "../../shared/platform/platform";
import { parseSessionCatalogPage } from "../../shared/api/sessionCatalogContract";
import { ErrorState, LoadingState } from "../../shared/ui/AsyncState";
import { BoundedListPager, useBoundedListPage } from "../../shared/ui/BoundedListPager";
import { Icon } from "../../shared/ui/Icon";
import { openLiveWindow } from "../live-window/LiveMiniWindow";
import { MetricCoveragePanel } from "../metric-coverage";
import {
  ProjectComparison,
  resolveProjectComparison,
  type ResolvedProjectComparison,
} from "./ProjectComparison";

type ProjectSort = "recent" | "name" | "sessions";

const PROJECT_RENDER_PAGE = 30;
const CATALOG_PAGE_SIZE = 100;
const CATALOG_REQUEST_DEADLINE_MS = 15_000;

interface ProjectCatalogItem {
  projectId: string;
  displayName: string;
  sessions: CodexSession[];
  latestStartedAt: string | null;
  completeSessionCount: number;
  /** Distinct providers that contributed sessions, in stable display order. */
  providers: string[];
}

function visibleLabel(value: string | null | undefined, fallback: string): string {
  return value?.trim() || fallback;
}

function projectLabel(sessions: readonly CodexSession[]): string {
  const labeled =
    sessions.find(
      (session) =>
        session.project_display_name_origin === "manual" &&
        session.project_display_name?.trim(),
    ) ??
    sessions.find(
      (session) =>
        session.project_display_name_origin === "provider" &&
        session.project_display_name?.trim(),
    ) ??
    sessions.find((session) => session.project_display_name?.trim());
  return visibleLabel(labeled?.project_display_name, "Unnamed project");
}

function timestampValue(value: string | null): number {
  if (!value) return Number.NEGATIVE_INFINITY;
  const timestamp = new Date(value).valueOf();
  return Number.isNaN(timestamp) ? Number.NEGATIVE_INFINITY : timestamp;
}

function visibleDate(value: string | null): string {
  const timestamp = timestampValue(value);
  if (!Number.isFinite(timestamp)) return "Latest activity unknown";
  return `Latest ${new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeZone: "UTC",
  }).format(timestamp)}`;
}

function buildCatalog(sessions: readonly CodexSession[]): ProjectCatalogItem[] {
  const grouped = new Map<string, CodexSession[]>();
  for (const session of sessions) {
    if (!isPseudonym(session.project_id) || !isPseudonym(session.session_id)) continue;
    const group = grouped.get(session.project_id) ?? [];
    group.push(session);
    grouped.set(session.project_id, group);
  }

  return [...grouped.entries()].map(([projectId, projectSessions]) => {
    const latestStartedAt = projectSessions.reduce<string | null>(
      (latest, session) =>
        timestampValue(session.started_at) > timestampValue(latest)
          ? session.started_at
          : latest,
      null,
    );
    return {
      projectId,
      displayName: projectLabel(projectSessions),
      sessions: projectSessions,
      latestStartedAt,
      completeSessionCount: projectSessions.filter((session) => session.events_complete)
        .length,
      providers: providersOf(projectSessions),
    };
  });
}

export function ProjectCatalog({
  transport,
  navigate,
  coverageProvider = "codex",
}: {
  transport: PromptEnhancerTransport;
  navigate: (route: AppRoute) => void;
  coverageProvider?: Provider;
}) {
  const [sessions, setSessions] = useState<CodexSession[] | null>(null);
  const [catalogComplete, setCatalogComplete] = useState(false);
  const [loadingOffset, setLoadingOffset] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [moreError, setMoreError] = useState("");
  const [retryKey, setRetryKey] = useState(0);
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<ProjectSort>("recent");
  const [selectedProjectIds, setSelectedProjectIds] = useState<Set<string>>(
    () => new Set(),
  );
  const [comparison, setComparison] = useState<ResolvedProjectComparison | null>(null);
  const [comparisonTransport, setComparisonTransport] =
    useState<PromptEnhancerTransport | null>(null);
  const [comparisonLoading, setComparisonLoading] = useState(false);
  const [comparisonError, setComparisonError] = useState("");
  const comparisonController = useRef<AbortController | null>(null);
  const comparisonButtonRef = useRef<HTMLButtonElement | null>(null);
  const catalogRequest = useRef<{
    controller: AbortController;
    generation: number;
    offset: number;
    timeout: number;
  } | null>(null);
  const catalogGeneration = useRef(0);
  const [catalogOwner, setCatalogOwner] =
    useState<PromptEnhancerTransport | null>(null);
  const catalogIsCurrent = catalogOwner === transport;
  const visibleSessions = catalogIsCurrent ? sessions : null;
  const visibleError = catalogIsCurrent ? error : "";
  const visibleMoreError = catalogIsCurrent ? moreError : "";

  function clearCatalogRequest() {
    const request = catalogRequest.current;
    if (request === null) return;
    catalogRequest.current = null;
    window.clearTimeout(request.timeout);
    request.controller.abort();
    setLoadingOffset(null);
  }

  function cancelCatalogRequest() {
    const request = catalogRequest.current;
    if (request === null) return;
    const wasFirstPage = request.offset === 0;
    clearCatalogRequest();
    if (wasFirstPage) {
      setError("The catalog request was cancelled. Reload the catalog to try again.");
    } else {
      setMoreError(
        "The next catalog page was cancelled. Loaded projects are unchanged; try again or reload the catalog.",
      );
    }
  }

  function loadCatalogPage(offset: number, existing: readonly CodexSession[]) {
    if (catalogRequest.current !== null) return;
    const controller = new AbortController();
    const generation = catalogGeneration.current;
    const request = {
      controller,
      generation,
      offset,
      timeout: 0,
    };
    const ownsRequest = () =>
      catalogRequest.current === request &&
      request.generation === catalogGeneration.current &&
      !controller.signal.aborted;
    const finish = () => {
      if (catalogRequest.current !== request) return;
      catalogRequest.current = null;
      window.clearTimeout(request.timeout);
      setLoadingOffset(null);
    };
    request.timeout = window.setTimeout(() => {
      if (catalogRequest.current !== request) return;
      catalogRequest.current = null;
      controller.abort();
      setLoadingOffset(null);
      if (offset === 0) {
        setError("The local project catalog request timed out. Reload the catalog to try again.");
      } else {
        setMoreError(
          "The next catalog page timed out. Loaded projects are unchanged; try again or reload the catalog.",
        );
      }
    }, CATALOG_REQUEST_DEADLINE_MS);
    catalogRequest.current = request;
    setLoadingOffset(offset);
    if (offset === 0) setError("");
    else setMoreError("");

    void Promise.resolve()
      .then(() => {
        if (!ownsRequest()) return undefined;
        return transport.listCodexSessions(
          CATALOG_PAGE_SIZE,
          offset,
          controller.signal,
        );
      })
      .then((response) => {
        if (!ownsRequest()) return;
        const parsed = parseSessionCatalogPage(response, offset);
        const allSessions = [...existing, ...(parsed ?? [])];
        const uniqueSessionCount = new Set(
          allSessions.map((session) => session.session_id),
        ).size;
        if (parsed === null || uniqueSessionCount !== allSessions.length) {
          if (offset === 0) {
            setError("The locally indexed project catalog response was invalid.");
          } else {
            setMoreError(
              "The catalog changed or the next page could not be verified. Loaded projects are unchanged; try again or reload the catalog.",
            );
          }
          return;
        }
        setSessions(allSessions);
        setCatalogOwner(transport);
        setCatalogComplete(parsed.length < CATALOG_PAGE_SIZE);
      })
      .catch(() => {
        if (!ownsRequest()) return;
        if (offset === 0) {
          setError("The locally indexed project catalog could not be loaded.");
        } else {
          setMoreError(
            "More projects could not be loaded. Loaded projects are unchanged; try again or reload the catalog.",
          );
        }
      })
      .finally(finish);
  }

  useEffect(() => {
    catalogGeneration.current += 1;
    clearCatalogRequest();
    comparisonController.current?.abort();
    comparisonController.current = null;
    setComparisonLoading(false);
    setSelectedProjectIds(new Set());
    setComparison(null);
    setComparisonTransport(null);
    setComparisonError("");
    setSessions(null);
    setCatalogOwner(transport);
    setCatalogComplete(false);
    setError("");
    setMoreError("");
    loadCatalogPage(0, []);
    return clearCatalogRequest;
  }, [retryKey, transport]);

  useEffect(
    () => () => {
      clearCatalogRequest();
      comparisonController.current?.abort();
    },
    [],
  );

  useEffect(() => {
    if (comparison === null) document.title = "Projects · Prompt Enhancer";
  }, [comparison]);

  const projects = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase();
    const items = buildCatalog(visibleSessions ?? []).filter((project) => {
      if (!normalizedQuery) return true;
      return (
        project.displayName.toLocaleLowerCase().includes(normalizedQuery) ||
        project.sessions.some((session) =>
          session.session_display_name
            ?.toLocaleLowerCase()
            .includes(normalizedQuery),
        )
      );
    });
    return items.sort((left, right) => {
      if (sort === "name") {
        return left.displayName.localeCompare(right.displayName, "en", {
          sensitivity: "base",
        });
      }
      if (sort === "sessions") {
        return (
          right.sessions.length - left.sessions.length ||
          left.displayName.localeCompare(right.displayName)
        );
      }
      return (
        timestampValue(right.latestStartedAt) - timestampValue(left.latestStartedAt) ||
        left.displayName.localeCompare(right.displayName)
      );
    });
  }, [query, sort, visibleSessions]);
  const loadedProjectCount = useMemo(
    () => buildCatalog(visibleSessions ?? []).length,
    [visibleSessions],
  );
  const hiddenSelectedCount = useMemo(() => {
    const visibleProjectIds = new Set(projects.map((project) => project.projectId));
    return [...selectedProjectIds].filter(
      (projectId) => !visibleProjectIds.has(projectId),
    ).length;
  }, [projects, selectedProjectIds]);
  const projectPage = useBoundedListPage({
    itemCount: projects.length,
    pageSize: PROJECT_RENDER_PAGE,
    resetKey: `${query.trim().toLocaleLowerCase()}:${sort}:${retryKey}`,
  });

  function toggleProject(projectId: string, checked: boolean) {
    if (comparisonLoading) return;
    setComparisonError("");
    setSelectedProjectIds((current) => {
      const next = new Set(current);
      if (checked) {
        if (next.size >= 25) return current;
        next.add(projectId);
      } else {
        next.delete(projectId);
      }
      return next;
    });
  }

  function loadMoreCatalog() {
    if (!catalogIsCurrent || visibleSessions === null || catalogComplete) return;
    loadCatalogPage(visibleSessions.length, visibleSessions);
  }

  function restartCatalog() {
    catalogGeneration.current += 1;
    clearCatalogRequest();
    comparisonController.current?.abort();
    comparisonController.current = null;
    setSessions(null);
    setCatalogOwner(null);
    setCatalogComplete(false);
    setLoadingOffset(null);
    setError("");
    setMoreError("");
    setSelectedProjectIds(new Set());
    setComparison(null);
    setComparisonTransport(null);
    setComparisonLoading(false);
    setComparisonError("");
    setRetryKey((value) => value + 1);
  }

  async function compareSelectedProjects() {
    const projectIds = [...selectedProjectIds];
    if (projectIds.length < 1 || projectIds.length > 25) return;
    comparisonController.current?.abort();
    const controller = new AbortController();
    const generation = catalogGeneration.current;
    comparisonController.current = controller;
    setComparisonError("");
    setComparisonLoading(true);
    try {
      const response = await transport.aggregateProjectQuality(
        {
          project_ids: projectIds,
          selection_mode: "all_analyzed_work",
        },
        controller.signal,
      );
      if (controller.signal.aborted || generation !== catalogGeneration.current) return;
      const resolved = resolveProjectComparison(response, projectIds.length);
      if (resolved === null) {
        setComparisonError(
          "The local aggregate returned an incompatible metric contract.",
        );
        return;
      }
      setComparison(resolved);
      setComparisonTransport(transport);
    } catch (reason: unknown) {
      if (controller.signal.aborted || generation !== catalogGeneration.current) return;
      if (reason instanceof TransportError && reason.status === 409) {
        setComparisonError(
          "One or more selected projects are no longer available in the safe local index.",
        );
      } else if (reason instanceof TransportError && reason.status === 422) {
        setComparisonError(
          "The selected work exceeds the bounded local aggregate limit.",
        );
      } else {
        setComparisonError("The local project aggregate could not be completed.");
      }
    } finally {
      if (comparisonController.current === controller) {
        comparisonController.current = null;
        setComparisonLoading(false);
      }
    }
  }

  if (comparison !== null && comparisonTransport === transport) {
    return (
      <section className="project-catalog">
        <ProjectComparison
          comparison={comparison}
          onBack={() => {
            setComparison(null);
            setComparisonTransport(null);
            window.setTimeout(() => comparisonButtonRef.current?.focus(), 0);
          }}
        />
      </section>
    );
  }

  return (
    <section className="project-catalog" aria-labelledby="project-catalog-title">
      <header className="project-catalog__header route-header">
        <div>
          <p className="eyebrow">Fast analysis loops</p>
          <h1 id="project-catalog-title">Projects</h1>
          <p>
            Choose an indexed project, then keep sessions and metric views inside one
            focused workspace.
          </p>
        </div>
        <span className="status-pill status-pill--info">
          <Icon name="lock" /> Stored local index
        </span>
      </header>

      <MetricCoveragePanel provider={coverageProvider} transport={transport} />

      {visibleSessions !== null && (
        <div className="project-catalog__paging-actions">
          <button
            className="button button--ghost button--compact"
            disabled={loadingOffset !== null}
            onClick={restartCatalog}
            type="button"
          >
            Reload catalog
          </button>
        </div>
      )}

      <div className="project-catalog__controls" role="search">
        <label className="field project-catalog__search">
          <span>Find a project or session</span>
          <input
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search local labels"
            type="search"
            value={query}
          />
        </label>
        <label className="field project-catalog__sort">
          <span>Sort projects</span>
          <select
            aria-label="Sort projects"
            onChange={(event) => setSort(event.target.value as ProjectSort)}
            value={sort}
          >
            <option value="recent">Latest activity</option>
            <option value="name">Project name</option>
            <option value="sessions">Session count</option>
          </select>
        </label>
      </div>

      {catalogIsCurrent && selectedProjectIds.size > 0 && (
        <aside
          aria-busy={comparisonLoading}
          aria-label="Project aggregate selection"
          className="project-catalog__selection"
        >
          <span aria-atomic="true" aria-live="polite" role="status">
            <strong>{selectedProjectIds.size}</strong>
            {` project${selectedProjectIds.size === 1 ? "" : "s"} selected`}
            {hiddenSelectedCount > 0 && (
              <small>
                {`${hiddenSelectedCount} hidden by the current filter`}
              </small>
            )}
            {comparisonLoading && <small>Combining selected projects locally</small>}
            {selectedProjectIds.size === 25 && <small>Selection limit reached</small>}
            <small>
              Combine uses all analyzed work for each selected project, not only
              loaded catalog sessions.
            </small>
          </span>
          <button
            className="button button--primary button--compact"
            disabled={comparisonLoading}
            onClick={compareSelectedProjects}
            ref={comparisonButtonRef}
            type="button"
          >
            {comparisonLoading ? "Combining locally..." : "Combine selected"}
          </button>
        </aside>
      )}
      {catalogIsCurrent && comparisonError && (
        <p className="project-catalog__comparison-error" role="alert">
          {comparisonError}
        </p>
      )}

      {visibleError ? (
        <ErrorState
          actionLabel="Reload catalog"
          message={visibleError}
          onRetry={restartCatalog}
        />
      ) : visibleSessions === null ? (
        <>
          <LoadingState label="Loading the local project catalog..." />
          {loadingOffset !== null && (
            <button
              className="button button--ghost"
              onClick={cancelCatalogRequest}
              type="button"
            >
              Cancel catalog request
            </button>
          )}
        </>
      ) : projects.length === 0 ? (
        <div className="empty-inbox">
          <span><Icon name="search" /></span>
          <h2>{query.trim() ? "No matching projects" : "No indexed projects"}</h2>
          <p>
            {query.trim()
              ? catalogComplete
                ? "Try a different local label or reload the catalog."
                : "No matches in the loaded index. Load the next page or try a different local label."
              : "Use Data sources to run a bounded, content-discarding index first."}
          </p>
        </div>
      ) : (
        <div className="project-catalog__grid">
          {projects.slice(projectPage.start, projectPage.end).map((project) => (
            <article
              className={
                selectedProjectIds.has(project.projectId)
                  ? "project-catalog-card project-catalog-card--selected"
                  : "project-catalog-card"
              }
              key={project.projectId}
            >
              <label className="project-catalog-card__select">
                <input
                  aria-label={`Select ${project.displayName} for combined profile`}
                  checked={selectedProjectIds.has(project.projectId)}
                  disabled={
                    comparisonLoading ||
                    (!selectedProjectIds.has(project.projectId) &&
                      selectedProjectIds.size >= 25)
                  }
                  onChange={(event) =>
                    toggleProject(project.projectId, event.target.checked)
                  }
                  type="checkbox"
                />
                <span>Combine</span>
              </label>
              <button
                aria-label={`Open project ${project.displayName}`}
                onClick={() =>
                  navigate({
                    name: "project_overview",
                    projectId: project.projectId,
                  })
                }
                type="button"
              >
                <span className="project-catalog-card__icon"><Icon name="layers" /></span>
                <span className="project-catalog-card__copy">
                  <strong>{project.displayName}</strong>
                  <small>Open its sessions and signal views</small>
                  <span aria-label="Session sources" className="provider-badge-row">
                    {project.providers.map((provider) => (
                      <ProviderBadge compact key={provider} provider={provider} />
                    ))}
                  </span>
                </span>
                <Icon name="arrow" />
              </button>
              <div className="project-catalog-card__windows">
                <button
                  aria-label={`Open a live window for ${project.displayName ?? "this project"}`}
                  className="project-catalog-card__live"
                  onClick={() => { openLiveWindow({ name: "live", projectId: project.projectId }); }}
                  title="Open a small self-refreshing window for this project"
                  type="button"
                >
                  <Icon name="layers" /> Live window
                </button>
              </div>
              <dl className="project-catalog-card__facts">
                <div><dt>Loaded sessions</dt><dd>{project.sessions.length}</dd></div>
                <div><dt>Complete loaded streams</dt><dd>{project.completeSessionCount}</dd></div>
                <div><dt>Activity</dt><dd>{visibleDate(project.latestStartedAt)}</dd></div>
              </dl>
            </article>
          ))}
        </div>
      )}
      <BoundedListPager label="Project catalog pages" page={projectPage} />
      {visibleSessions !== null && (
        <>
          <p
            aria-label="Loaded catalog coverage"
            aria-live="polite"
            className="project-catalog__boundary"
            role="status"
          >
            Loaded index coverage: {loadedProjectCount} project{loadedProjectCount === 1 ? "" : "s"} from {visibleSessions.length} session{visibleSessions.length === 1 ? "" : "s"}. Project counts, search, and sorting cover only these loaded index records; this view does not read or mutate any provider cache.
            {catalogComplete
              ? " End of the current index reached. Reload catalog to refresh it."
              : " More current index records may be available."}
          </p>
          {!catalogComplete && (
            <div className="project-catalog__paging-actions">
              <button
                className="button button--secondary"
                disabled={loadingOffset !== null}
                onClick={loadMoreCatalog}
                type="button"
              >
                {loadingOffset === null
                  ? `Load next ${CATALOG_PAGE_SIZE} sessions`
                  : "Loading next catalog page..."}
              </button>
              {loadingOffset !== null && (
                <button
                  className="button button--ghost"
                  onClick={cancelCatalogRequest}
                  type="button"
                >
                  Cancel catalog request
                </button>
              )}
            </div>
          )}
          {visibleMoreError && (
            <ErrorState
              actionLabel="Retry next page"
              message={visibleMoreError}
              onRetry={loadMoreCatalog}
              title="More catalog data needs attention"
            />
          )}
        </>
      )}
    </section>
  );
}
