import { useEffect, useMemo, useRef, useState } from "react";
import {
  providerLabel,
  type CodexSession,
  type LocalProvider,
  type PromptEnhancerTransport,
} from "../../shared/api/contracts";
import {
  parseSessionCatalogPage,
  safeSessionCatalogRow,
  SESSION_CATALOG_PAGE_SIZE,
} from "../../shared/api/sessionCatalogContract";
import { TransportError } from "../../shared/api/httpTransport";
import type { AppRoute } from "../../shared/platform/platform";
import type { RuntimeDataMode } from "../../shared/platform/runtimeMode";
import { ErrorState, LoadingState } from "../../shared/ui/AsyncState";
import { BoundedListPager, useBoundedListPage } from "../../shared/ui/BoundedListPager";
import { Icon } from "../../shared/ui/Icon";
import { ProviderBadge } from "../../shared/ui/ProviderBadge";
import { openLiveWindow } from "../live-window/LiveMiniWindow";
import "./Sessions.css";
const PAGE = SESSION_CATALOG_PAGE_SIZE;
const RENDER_PAGE = 50;
const REQUEST_DEADLINE_MS = 15000;
type Filter = "all" | LocalProvider;
export const safeSessionRow = safeSessionCatalogRow;
function ms(value: string | null): number | null {
  const timestamp = value ? new Date(value).valueOf() : Number.NaN;
  return Number.isNaN(timestamp) ? null : timestamp;
}
export function durationLabel(started: string, ended: string | null): string {
  const start = ms(started);
  const end = ms(ended);
  if (start === null) return "Start unknown";
  if (end === null) return "End not recorded";
  if (end < start) return "Duration unavailable";
  const seconds = Math.round((end - start) / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  return `${hours} h ${minutes - hours * 60} min`;
}
function startedLabel(value: string): string {
  const timestamp = ms(value);
  if (timestamp === null) return "Unknown start";
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium", timeStyle: "short", timeZone: "UTC",
  }).format(timestamp) + " UTC";
}
function visible(value: string | null, fallback: string): string {
  return value?.trim() || fallback;
}
export function SessionsPage({ transport, navigate, runtimeMode = "synthetic_demo" }: {
    transport: Pick<PromptEnhancerTransport, "listCodexSessions">;
    navigate: (route: AppRoute) => void;
    runtimeMode?: RuntimeDataMode;
}) {
    const [rows, setRows] = useState<CodexSession[] | null>(null);
    const [owner, setOwner] = useState<typeof transport | null>(null);
    const [complete, setComplete] = useState(false);
    const [loadingOffset, setLoadingOffset] = useState<number | null>(null);
    const [error, setError] = useState("");
    const [moreError, setMoreError] = useState("");
    const [query, setQuery] = useState("");
    const [filter, setFilter] = useState<Filter>("all");
    const [reloadKey, setReloadKey] = useState(0);
    const request = useRef<{
        controller: AbortController;
        generation: number;
        offset: number;
        timeout: number;
    } | null>(null);
    const generation = useRef(0);
    const mounted = useRef(true);
    const current = owner === transport;
    const visibleRows = current ? rows : null;
    const visibleError = current ? error : "";
    const visibleMoreError = current ? moreError : "";
    const activeFilter: Filter = current ? filter : "all";
    const visibleLoadingOffset = current ? loadingOffset : null;
    function clearRequest() {
        const active = request.current;
        if (!active) return;
        request.current = null;
        window.clearTimeout(active.timeout);
        active.controller.abort();
        if (mounted.current) setLoadingOffset(null);
    }
    function cancelRequest() {
        const active = request.current;
        if (!active) return;
        const initial = active.offset === 0;
        clearRequest();
        if (!mounted.current) return;
        if (initial) {
            setError("The catalog request was cancelled. Reload the catalog to try again.");
        } else {
            setMoreError("The next catalog page was cancelled. Loaded sessions are unchanged; try again or reload the catalog.");
        }
    }
    function requestPage(offset: number, existing: readonly CodexSession[]) {
        if (request.current !== null || !mounted.current) {
            return;
        }
        const controller = new AbortController();
        const requestGeneration = generation.current;
        const active = {
            controller,
            generation: requestGeneration,
            offset,
            timeout: 0,
        };
        const owns = () =>
            mounted.current &&
            request.current === active &&
            active.generation === generation.current &&
            !controller.signal.aborted;
        const finish = () => {
            if (request.current !== active) {
                return;
            }
            request.current = null;
            window.clearTimeout(active.timeout);
            if (mounted.current) {
                setLoadingOffset(null);
            }
        };
        active.timeout = window.setTimeout(() => {
            if (request.current !== active) {
                return;
            }
            request.current = null;
            controller.abort();
            if (!mounted.current) {
                return;
            }
            setLoadingOffset(null);
            if (offset === 0) {
                setError("The local session catalog request timed out. Reload the catalog to try again.");
            } else {
                setMoreError("The next catalog page timed out. Loaded sessions are unchanged; try again or reload the catalog.");
            }
        }, REQUEST_DEADLINE_MS);
        request.current = active;
        setLoadingOffset(offset);
        if (offset === 0) {
            setError("");
        } else {
            setMoreError("");
        }
        void Promise.resolve()
            .then(() =>
                owns()
                    ? transport.listCodexSessions(PAGE, offset, controller.signal)
                    : undefined,
            )
            .then((response) => {
                if (!owns()) {
                    return;
                }
                const parsed = parseSessionCatalogPage(response, offset);
                const all = [...existing, ...(parsed ?? [])];
                if (
                    parsed === null ||
                    new Set(all.map((row) => row.session_id)).size !== all.length
                ) {
                    if (offset === 0) {
                        setError("The stored session catalog response was invalid and was not shown.");
                    } else {
                        setMoreError("The catalog changed or the next page could not be verified. Loaded sessions are unchanged; try again or reload the catalog.");
                    }
                    return;
                }
                setRows(all);
                setOwner(transport);
                setComplete(parsed.length < PAGE);
            })
            .catch((caught: unknown) => {
                if (!owns()) {
                    return;
                }
                if (offset === 0) {
                    setError(
                        caught instanceof TransportError && caught.status === 401
                            ? "Sign in to the local service to list sessions."
                            : "The stored session catalog could not be loaded.",
                    );
                } else {
                    setMoreError("More sessions could not be loaded. The loaded sessions are unchanged; try again or reload the catalog.");
                }
            })
            .finally(finish);
    }
    function reloadCatalog() {
        generation.current += 1;
        clearRequest();
        setRows(null);
        setOwner(null);
        setComplete(false);
        setError("");
        setMoreError("");
        setFilter("all");
        setReloadKey((key) => key + 1);
    }
    useEffect(() => {
        mounted.current = true;
        generation.current += 1;
        clearRequest();
        setRows(null);
        setOwner(transport);
        setComplete(false);
        setError("");
        setMoreError("");
        setFilter("all");
        requestPage(0, []);
        return () => {
            mounted.current = false;
            clearRequest();
        };
    }, [transport, reloadKey]);
    const providers = useMemo(() => {
        const seen = new Set((visibleRows ?? []).map((row) => row.provider));
        const candidates: LocalProvider[] = ["codex", "claude_code", "synthetic"];
        return candidates.filter((provider) => seen.has(provider));
    }, [visibleRows]);
    const filtered = useMemo(() => {
        const needle = query.trim().toLowerCase();
        return [...(visibleRows ?? [])]
            .filter((row) => activeFilter === "all" || row.provider === activeFilter)
            .filter(
                (row) =>
                    !needle ||
                    `${row.project_display_name ?? ""} ${row.session_display_name ?? ""}`
                        .toLowerCase()
                        .includes(needle),
            )
            .sort((a, b) => (ms(b.started_at) ?? 0) - (ms(a.started_at) ?? 0));
    }, [visibleRows, query, activeFilter]);
    const unnamed = useMemo(
        () => filtered.filter((row) => !row.session_display_name?.trim()).length,
        [filtered],
    );
    const renderPage = useBoundedListPage({
        itemCount: filtered.length,
        pageSize: RENDER_PAGE,
        resetKey: `${query.trim().toLocaleLowerCase()}:${activeFilter}:${reloadKey}`,
    });
    const loadMore = () => {
        if (visibleRows === null || complete) {
            return;
        }
        requestPage(visibleRows.length, visibleRows);
    };
    return (
      <section className="sessions-page" aria-labelledby="sessions-title">
        <header className="page-header route-header">
          <div>
            <p className="eyebrow">Personal workspace</p>
            <h1 id="sessions-title">Sessions</h1>
            <p>
              Captured sessions across your sources, newest first. Search the loaded catalog by project or title.
            </p>
          </div>
          <div className="page-header__meta">
            <span className="privacy-chip">
              <Icon name="lock" /> Local only
            </span>
            <button
              className="button button--ghost button--compact"
              onClick={reloadCatalog}
              type="button"
            >
              Reload catalog
            </button>
          </div>
        </header>
        <div className="sessions-toolbar" role="search">
          <label className="sessions-search">
            <Icon name="search" />
            <input
              aria-label="Search sessions by project or title"
              onChange={(event) => setQuery(event.currentTarget.value)}
              placeholder="Search by project or title"
              type="search"
              value={query}
            />
          </label>
          <div
            aria-label="Filter by source"
            className="segmented-control sessions-filter"
            role="group"
          >
            <button
              aria-pressed={activeFilter === "all"}
              className={activeFilter === "all" ? "segmented-control__item--active" : ""}
              onClick={() => setFilter("all")}
              type="button"
            >
              All sources
            </button>
            {providers.map((provider) => (
              <button
                aria-pressed={activeFilter === provider}
                className={activeFilter === provider ? "segmented-control__item--active" : ""}
                key={provider}
                onClick={() => setFilter(provider)}
                type="button"
              >
                {providerLabel(provider)}
              </button>
            ))}
          </div>
        </div>
        {visibleRows !== null && !visibleError && (
          <>
            <p className="sessions-count" aria-live="polite">
              {filtered.length} of {visibleRows.length} session
              {visibleRows.length === 1 ? "" : "s"}
              {unnamed > 0 ? ` · ${unnamed} without a title` : ""}
              {!complete && (
                <>
                  {" · Partial catalog: search covers only the "}
                  {visibleRows.length}
                  {" loaded sessions. Load more to search beyond this batch."}
                </>
              )}
            </p>
            <p aria-label="Loaded session catalog coverage" aria-live="polite" className="sessions-coverage" role="status">
              Loaded session catalog coverage: {visibleRows.length} session
              {visibleRows.length === 1 ? "" : "s"}. Counts, search, and source
              filters cover only these loaded catalog records; this view does not
              read or mutate any provider cache. {complete
                ? "The end of the current catalog was reached. Reload catalog to refresh it."
                : "More current catalog records may be available."}
            </p>
          </>
        )}
        {visibleError ? (
          <ErrorState message={visibleError} onRetry={reloadCatalog} />
        ) : visibleRows === null ? (
          <>
            <LoadingState label="Loading sessions…" />
            {visibleLoadingOffset !== null && (
              <button className="button button--ghost" onClick={cancelRequest} type="button">
                Cancel catalog request
              </button>
            )}
          </>
        ) : filtered.length === 0 ? (
          <div className="sessions-empty" role="note">
            <strong>
              {visibleRows.length === 0 ? "No sessions captured yet" : "No sessions match"}
            </strong>
            <p>
              {visibleRows.length === 0
                ? runtimeMode === "local_real"
                  ? "Grant a source on the Data sources page and index it; sessions appear here with their project and title."
                  : "This synthetic preview has no session fixtures to show. Local-source access is available only in the local application."
                : complete
                  ? "Try a different search or source filter."
                  : "No matches in the loaded batch. Load more sessions or change the search or source filter."}
            </p>
            {visibleRows.length === 0 && runtimeMode === "local_real" && (
              <button
                className="button button--ghost"
                onClick={() => navigate({ name: "local_sources" })}
                type="button"
              >
                Open Data sources
              </button>
            )}
          </div>
        ) : (
          <>
            <ul className="sessions-list">
              {filtered.slice(renderPage.start, renderPage.end).map((row) => (
                <li key={row.session_id}>
                  <button
                    aria-label={`Open ${visible(row.session_display_name, "untitled session")} in ${visible(row.project_display_name, "unnamed project")}`}
                    className="session-row"
                    onClick={() =>
                      navigate({
                        name: "session_metrics",
                        projectId: row.project_id,
                        sessionId: row.session_id,
                        category: "readiness",
                      })
                    }
                    type="button"
                  >
                    <span className="session-row__title">
                      <strong>{visible(row.session_display_name, "Untitled session")}</strong>
                      <small>{visible(row.project_display_name, "Unnamed project")}</small>
                    </span>
                    <span className="session-row__meta">
                      <ProviderBadge compact provider={row.provider} />
                      <time dateTime={row.started_at}>{startedLabel(row.started_at)}</time>
                      <span className="session-row__duration">
                        {durationLabel(row.started_at, row.ended_at)}
                      </span>
                    </span>
                    <Icon className="session-row__arrow" name="arrow" />
                  </button>
                  <button
                    aria-label={`Open a live window for ${visible(row.session_display_name, "this session")}`}
                    className="session-row__live"
                    onClick={() => {
                      openLiveWindow({
                        name: "live",
                        projectId: row.project_id,
                        sessionId: row.session_id,
                      });
                    }}
                    title="Open a small self-refreshing window for this session"
                    type="button"
                  >
                    <Icon name="layers" />
                  </button>
                </li>
              ))}
            </ul>
            <BoundedListPager label="Stored session pages" page={renderPage} />
          </>
        )}
        {visibleRows !== null && !visibleError && !complete && (
          <div className="sessions-pagination">
            <button
              className="button button--secondary"
              disabled={visibleLoadingOffset !== null}
              onClick={loadMore}
              type="button"
            >
              {visibleLoadingOffset === null ? `Load next ${PAGE} sessions` : "Loading more…"}
            </button>
            {visibleLoadingOffset !== null && (
              <button className="button button--ghost" onClick={cancelRequest} type="button">
                Cancel catalog request
              </button>
            )}
            {visibleMoreError && (
              <ErrorState
                actionLabel="Retry next page"
                message={visibleMoreError}
                onRetry={loadMore}
                title="More catalog data needs attention"
              />
            )}
          </div>
        )}
      </section>
    );
}
