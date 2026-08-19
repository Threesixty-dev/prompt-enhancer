import { useEffect, useMemo, useState } from "react";
import {
  isLocalProvider,
  providerLabel,
  type CodexSession,
  type LocalProvider,
  type PromptEnhancerTransport,
} from "../../shared/api/contracts";
import { TransportError } from "../../shared/api/httpTransport";
import type { AppRoute } from "../../shared/platform/platform";
import { isPseudonym } from "../../shared/platform/platform";
import { ErrorState, LoadingState } from "../../shared/ui/AsyncState";
import { Icon } from "../../shared/ui/Icon";
import { ProviderBadge } from "../../shared/ui/ProviderBadge";
import "./Sessions.css";

const PAGE = 100;
const MAX_PAGES = 10;

type Filter = "all" | LocalProvider;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function safeLabel(value: unknown, max: number): value is string | null {
  return value === null || (typeof value === "string" && value.length >= 1 && value.length <= max && !/[\u0000-\u001f\u007f]/.test(value));
}

/** Fail closed on any row that is not the content-free catalog shape. */
export function safeSessionRow(value: unknown): value is CodexSession {
  return (
    isRecord(value) &&
    isLocalProvider(value.provider) &&
    typeof value.session_id === "string" && isPseudonym(value.session_id) &&
    typeof value.project_id === "string" && isPseudonym(value.project_id) &&
    typeof value.installation_id === "string" && isPseudonym(value.installation_id) &&
    safeLabel(value.project_display_name, 120) &&
    safeLabel(value.session_display_name, 160) &&
    typeof value.started_at === "string" &&
    (value.ended_at === null || typeof value.ended_at === "string") &&
    typeof value.events_complete === "boolean"
  );
}

function ms(value: string | null): number | null {
  if (!value) return null;
  const t = new Date(value).valueOf();
  return Number.isNaN(t) ? null : t;
}

export function durationLabel(started: string, ended: string | null): string {
  const a = ms(started);
  const b = ms(ended);
  if (a === null) return "Start unknown";
  if (b === null) return "End not recorded";
  const seconds = Math.max(0, Math.round((b - a) / 1000));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  return `${hours} h ${minutes - hours * 60} min`;
}

function startedLabel(value: string): string {
  const t = ms(value);
  if (t === null) return "Unknown start";
  return new Intl.DateTimeFormat("en", { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" }).format(t) + " UTC";
}

function visible(value: string | null, fallback: string): string {
  const trimmed = value?.trim();
  return trimmed ? trimmed : fallback;
}

/**
 * Every session across every provider, newest first, findable by name.
 * Identifiers never appear in this view; they live in detail routes only.
 */
export function SessionsPage({
  transport,
  navigate,
}: {
  transport: Pick<PromptEnhancerTransport, "listCodexSessions">;
  navigate: (route: AppRoute) => void;
}) {
  const [rows, setRows] = useState<CodexSession[] | null>(null);
  const [complete, setComplete] = useState(false);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setRows(null);
    setError("");
    (async () => {
      const collected: CodexSession[] = [];
      try {
        for (let page = 0; page < MAX_PAGES; page += 1) {
          const response = await transport.listCodexSessions(PAGE, page * PAGE, controller.signal);
          if (controller.signal.aborted) return;
          if (!isRecord(response) || !Array.isArray(response.sessions) || !response.sessions.every(safeSessionRow)) {
            setError("The stored session catalog response was invalid and was not shown.");
            return;
          }
          collected.push(...response.sessions);
          if (response.sessions.length < PAGE) {
            setComplete(true);
            break;
          }
          if (page === MAX_PAGES - 1) setComplete(false);
        }
        setRows(collected);
      } catch (caught) {
        if (controller.signal.aborted) return;
        setError(caught instanceof TransportError && caught.status === 401
          ? "Sign in to the local service to list sessions."
          : "The stored session catalog could not be loaded.");
      }
    })();
    return () => controller.abort();
  }, [transport, retry]);

  const providers = useMemo(() => {
    const seen = new Set<string>();
    for (const row of rows ?? []) seen.add(row.provider);
    return ["codex", "claude_code", "synthetic"].filter((p) => seen.has(p)) as LocalProvider[];
  }, [rows]);

  const filtered = useMemo(() => {
    if (rows === null) return [];
    const needle = query.trim().toLowerCase();
    return [...rows]
      .filter((row) => filter === "all" || row.provider === filter)
      .filter((row) => {
        if (!needle) return true;
        const hay = `${row.project_display_name ?? ""} ${row.session_display_name ?? ""}`.toLowerCase();
        return hay.includes(needle);
      })
      .sort((a, b) => (ms(b.started_at) ?? 0) - (ms(a.started_at) ?? 0));
  }, [rows, query, filter]);

  const unnamed = useMemo(() => filtered.filter((row) => !row.session_display_name?.trim()).length, [filtered]);

  return (
    <section className="sessions-page" aria-labelledby="sessions-title">
      <header className="page-header">
        <div>
          <p className="eyebrow">Personal workspace</p>
          <h1 id="sessions-title">Sessions</h1>
          <p>Every captured session from every source, newest first. Find one by project or title.</p>
        </div>
        <div className="page-header__meta">
          <span className="privacy-chip"><Icon name="lock" /> Local only</span>
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
        <div aria-label="Filter by source" className="segmented-control sessions-filter" role="group">
          <button
            aria-pressed={filter === "all"}
            className={filter === "all" ? "segmented-control__item--active" : ""}
            onClick={() => setFilter("all")}
            type="button"
          >
            All sources
          </button>
          {providers.map((provider) => (
            <button
              aria-pressed={filter === provider}
              className={filter === provider ? "segmented-control__item--active" : ""}
              key={provider}
              onClick={() => setFilter(provider)}
              type="button"
            >
              {providerLabel(provider)}
            </button>
          ))}
        </div>
      </div>

      {error !== "" ? (
        <ErrorState message={error} onRetry={() => setRetry((value) => value + 1)} />
      ) : rows === null ? (
        <LoadingState label="Loading sessions…" />
      ) : filtered.length === 0 ? (
        <div className="sessions-empty" role="note">
          <strong>{rows.length === 0 ? "No sessions captured yet" : "No sessions match"}</strong>
          <p>
            {rows.length === 0
              ? "Grant a source on the Data source page and index it; sessions appear here with their project and title."
              : "Try a different search or source filter."}
          </p>
        </div>
      ) : (
        <>
          <p className="sessions-count" aria-live="polite">
            {filtered.length} of {rows.length} session{rows.length === 1 ? "" : "s"}
            {complete ? "" : ` · showing the first ${MAX_PAGES * PAGE}`}
            {unnamed > 0 ? ` · ${unnamed} without a title` : ""}
          </p>
          <ul className="sessions-list">
            {filtered.map((row) => (
              <li key={row.session_id}>
                <button
                  aria-label={`Open ${visible(row.session_display_name, "untitled session")} in ${visible(row.project_display_name, "unnamed project")}`}
                  className="session-row"
                  onClick={() => navigate({
                    name: "session_metrics",
                    projectId: row.project_id,
                    sessionId: row.session_id,
                    category: "readiness",
                  })}
                  type="button"
                >
                  <span className="session-row__title">
                    <strong>{visible(row.session_display_name, "Untitled session")}</strong>
                    <small>{visible(row.project_display_name, "Unnamed project")}</small>
                  </span>
                  <span className="session-row__meta">
                    <ProviderBadge compact provider={row.provider} />
                    <time dateTime={row.started_at}>{startedLabel(row.started_at)}</time>
                    <span className="session-row__duration">{durationLabel(row.started_at, row.ended_at)}</span>
                  </span>
                  <Icon className="session-row__arrow" name="arrow" />
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
