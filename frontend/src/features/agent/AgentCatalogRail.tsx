import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";

import type {
  AgentCatalogSession,
  AgentProject,
  AgentSessionView,
  PromptEnhancerTransport,
  UpdateAgentCatalogSession,
} from "../../shared/api/contracts";
import { TransportError } from "../../shared/api/httpTransport";
import { BoundedListPager, useBoundedListPage } from "../../shared/ui/BoundedListPager";
import { connectAgentCatalogSync, type AgentCatalogSync } from "./agentWindowChannel";
import "./AgentCatalogRail.css";

const CATALOG_RENDER_PAGE = 40;

type CatalogTransport = Pick<
  PromptEnhancerTransport,
  | "listAgentProjects"
  | "createAgentProject"
  | "updateAgentProject"
  | "deleteAgentProject"
  | "listAgentCatalogSessions"
  | "updateAgentCatalogSession"
  | "deleteAgentCatalogSession"
>;

type CatalogDialog =
  | { kind: "create-project" }
  | { kind: "rename-project"; project: AgentProject }
  | { kind: "delete-project"; project: AgentProject }
  | { kind: "rename-session"; session: AgentCatalogSession }
  | { kind: "move-session"; session: AgentCatalogSession }
  | { kind: "fork-session"; session: AgentCatalogSession }
  | { kind: "delete-session"; session: AgentCatalogSession };

type CatalogActionMenu =
  | { kind: "project"; project: AgentProject }
  | { kind: "session"; session: AgentCatalogSession };

const MODAL_FOCUSABLE = [
  "a[href]",
  "button:not(:disabled)",
  "input:not(:disabled)",
  "select:not(:disabled)",
  "textarea:not(:disabled)",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

function trapModalFocus(event: ReactKeyboardEvent<HTMLElement>): void {
  if (event.key !== "Tab") return;
  const eventTarget = event.target instanceof HTMLElement ? event.target : null;
  const container = event.currentTarget.matches("[role='dialog']")
    ? event.currentTarget
    : eventTarget?.closest<HTMLElement>("[role='dialog']") ?? event.currentTarget;
  // Filtering a DOM-ordered wildcard query avoids selector-list ordering differences
  // between browsers and jsdom while preserving the user's actual tab sequence.
  const focusable = [...container.querySelectorAll<HTMLElement>("*")]
    .filter((element) => element.matches(MODAL_FOCUSABLE));
  if (focusable.length === 0) {
    event.preventDefault();
    container.focus();
    return;
  }
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  const active = document.activeElement;
  if (event.shiftKey && (active === first || !container.contains(active))) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && (active === last || !container.contains(active))) {
    event.preventDefault();
    first.focus();
  }
}

export interface AgentCatalogRailProps {
  transport: Partial<CatalogTransport>;
  liveSessions: AgentSessionView[] | null;
  currentSessionId?: string;
  draftSessionIds?: ReadonlySet<string>;
  selectedProjectId: string | null;
  collapsed?: boolean;
  disabled?: boolean;
  newChatDisabled?: boolean;
  refreshKey?: number;
  onProjectChange: (projectId: string | null) => void;
  onToggleCollapsed?: () => void;
  onNewChat: (projectId: string | null, trigger: HTMLButtonElement) => void;
  onOpenLiveSession: (session: AgentSessionView) => void;
  onOpenUnavailableSession: (session: AgentCatalogSession) => void;
  onCloseLiveSession: (session: AgentSessionView) => void;
  onSessionDeleted?: (sessionId: string) => void;
  onSessionUpdated?: (session: AgentCatalogSession) => void;
  onForkSession?: (
    session: AgentCatalogSession,
    title: string,
    signal?: AbortSignal,
  ) => Promise<void>;
  onInitialCatalogLoad?: (session: AgentCatalogSession | null) => void;
}

function catalogAvailable(transport: Partial<CatalogTransport>): transport is CatalogTransport {
  return typeof transport.listAgentProjects === "function"
    && typeof transport.createAgentProject === "function"
    && typeof transport.updateAgentProject === "function"
    && typeof transport.deleteAgentProject === "function"
    && typeof transport.listAgentCatalogSessions === "function"
    && typeof transport.updateAgentCatalogSession === "function"
    && typeof transport.deleteAgentCatalogSession === "function";
}

function failureCopy(error: unknown): string {
  if (!(error instanceof TransportError)) return "The Agent catalog could not be updated.";
  switch (error.reasonCode) {
    case "agent_project_revision_conflict":
    case "agent_catalog_session_revision_conflict":
    case "agent_history_revision_conflict":
      return "This item changed in another window. It has been refreshed; retry your action.";
    case "agent_project_not_empty":
      return "Move, archive, or delete this project's chats before deleting the project.";
    case "agent_default_project_protected":
      return "The Personal workspace project cannot be archived or deleted.";
    case "agent_catalog_session_live":
      return "Close the live chat before deleting its saved navigation entry.";
    case "agent_session_fork_point_invalid":
      return "The selected branch point is no longer a completed turn. Refresh and retry.";
    case "agent_session_fork_request_conflict":
      return "This branch request no longer matches its original input. Refresh and retry.";
    case "agent_session_fork_conflict":
      return "Another branch operation changed this chat. Refresh and retry.";
    case "agent_project_archived":
      return "Restore the destination project before creating a branch.";
    case "agent_catalog_storage_unavailable":
    case "agent_catalog_unavailable":
      return "The private Agent catalog is unavailable. Live chats remain separate.";
    default:
      return "The Agent catalog could not be updated.";
  }
}

function sessionStatus(
  session: AgentCatalogSession,
  live: AgentSessionView | undefined,
  hasDraft = false,
): string {
  const status = live?.cleanup_unconfirmed
    ? "cleanup unconfirmed"
    : live?.closing
      ? "closing"
      : live?.pending_approval_id
        ? "waiting for approval"
        : live?.running
          ? "working"
          : live
            ? `${live.turns} ${live.turns === 1 ? "turn" : "turns"} · live${live.settings.retention_policy === "local_history" ? " · saved" : " · metadata only"}`
            : session.retention_policy === "local_history"
              ? `${session.turn_count} ${session.turn_count === 1 ? "turn" : "turns"} · saved locally`
              : "Metadata only · history unavailable";
  return hasDraft ? `${status} · draft in this window` : status;
}

function liveSessionTitle(session: AgentSessionView): string {
  return session.settings.title
    || session.settings.workspace.split(/[\\/]/).filter(Boolean).pop()
    || "Untitled chat";
}

function branchTitle(title: string): string {
  const suffix = " (branch)";
  return `${title.slice(0, 120 - suffix.length).trimEnd()}${suffix}`;
}

export function AgentCatalogRail({
  transport,
  liveSessions,
  currentSessionId,
  draftSessionIds,
  selectedProjectId,
  collapsed = false,
  disabled = false,
  newChatDisabled = disabled,
  refreshKey = 0,
  onProjectChange,
  onToggleCollapsed,
  onNewChat,
  onOpenLiveSession,
  onOpenUnavailableSession,
  onCloseLiveSession,
  onSessionDeleted,
  onSessionUpdated,
  onForkSession,
  onInitialCatalogLoad,
}: AgentCatalogRailProps) {
  const supported = catalogAvailable(transport);
  const [projects, setProjects] = useState<AgentProject[] | null>(supported ? null : []);
  const [catalogSessions, setCatalogSessions] = useState<AgentCatalogSession[] | null>(
    supported ? null : [],
  );
  const [search, setSearch] = useState("");
  const [includeArchived, setIncludeArchived] = useState(false);
  const [error, setError] = useState("");
  const [busyKey, setBusyKey] = useState("");
  const [dialog, setDialog] = useState<CatalogDialog | null>(null);
  const [actionMenu, setActionMenu] = useState<CatalogActionMenu | null>(null);
  const [dialogValue, setDialogValue] = useState("");
  const [moveDestinations, setMoveDestinations] = useState<AgentProject[] | null>(null);
  const [moveDestinationError, setMoveDestinationError] = useState("");
  const [moveDestinationNonce, setMoveDestinationNonce] = useState(0);
  const [refreshNonce, setRefreshNonce] = useState(0);
  const actionMenuTriggerRef = useRef<HTMLButtonElement | null>(null);
  const dialogTriggerRef = useRef<HTMLElement | null>(null);
  const catalogSyncRef = useRef<AgentCatalogSync | null>(null);
  const selectedProjectSnapshotRef = useRef<AgentProject | null>(null);
  const initialCatalogReported = useRef(false);
  const mutationOwnerRef = useRef(0);
  const mutationRef = useRef<{
    controller: AbortController;
    key: string;
    owner: number;
  } | null>(null);

  const liveById = useMemo(
    () => new Map((liveSessions ?? []).map((session) => [session.session_id, session])),
    [liveSessions],
  );
  const projectNameById = useMemo(
    () => new Map((projects ?? []).map((project) => [project.project_id, project.name])),
    [projects],
  );
  const normalizedSearch = search.trim();
  const projectItems = projects ?? [];
  const selectedProjectIndex = selectedProjectId === null
    ? null
    : projectItems.findIndex((project) => project.project_id === selectedProjectId);
  const projectPage = useBoundedListPage({
    itemCount: projectItems.length,
    pageSize: CATALOG_RENDER_PAGE,
    preferredIndex: selectedProjectIndex !== null && selectedProjectIndex >= 0 ? selectedProjectIndex : null,
    resetKey: `${normalizedSearch}:${String(includeArchived)}:${refreshKey}:${refreshNonce}:projects`,
  });
  const sessionItems = catalogSessions ?? [];
  const selectedSessionIndex = currentSessionId === undefined
    ? null
    : sessionItems.findIndex((session) => session.session_id === currentSessionId);
  const sessionPage = useBoundedListPage({
    itemCount: sessionItems.length,
    pageSize: CATALOG_RENDER_PAGE,
    preferredIndex: selectedSessionIndex !== null && selectedSessionIndex >= 0 ? selectedSessionIndex : null,
    resetKey: `${selectedProjectId ?? "all"}:${normalizedSearch}:${String(includeArchived)}:${refreshKey}:${refreshNonce}:sessions`,
  });

  const refresh = useCallback(() => setRefreshNonce((value) => value + 1), []);

  useEffect(() => {
    if (!supported) return;
    const sync = connectAgentCatalogSync(refresh);
    catalogSyncRef.current = sync;
    return () => {
      if (catalogSyncRef.current === sync) catalogSyncRef.current = null;
      sync.close();
    };
  }, [refresh, supported]);

  useEffect(() => {
    initialCatalogReported.current = false;
    selectedProjectSnapshotRef.current = null;
    mutationOwnerRef.current += 1;
    mutationRef.current?.controller.abort();
    mutationRef.current = null;
    setBusyKey("");
    setMoveDestinations(null);
    setMoveDestinationError("");
    return () => {
      mutationOwnerRef.current += 1;
      mutationRef.current?.controller.abort();
      mutationRef.current = null;
    };
  }, [transport]);

  useEffect(() => {
    if (!supported || dialog?.kind !== "move-session") return;
    const controller = new AbortController();
    setMoveDestinations(null);
    setMoveDestinationError("");
    transport.listAgentProjects({
      includeArchived: false,
      limit: 200,
    }, controller.signal).then((result) => {
      if (controller.signal.aborted) return;
      const destinations = result.projects.filter((project) => (
        project.project_id !== dialog.session.project_id && !project.archived_at
      ));
      setMoveDestinations(destinations);
      setDialogValue((current) => (
        destinations.some((project) => project.project_id === current)
          ? current
          : destinations[0]?.project_id ?? ""
      ));
    }).catch(() => {
      if (controller.signal.aborted) return;
      setMoveDestinations([]);
      setMoveDestinationError("Active projects could not be loaded. Retry this read before moving the chat.");
    });
    return () => controller.abort();
  }, [dialog, moveDestinationNonce, supported, transport]);

  useEffect(() => {
    if (!disabled) return;
    mutationOwnerRef.current += 1;
    mutationRef.current?.controller.abort();
    mutationRef.current = null;
    setBusyKey("");
    setActionMenu(null);
    setDialog(null);
  }, [disabled]);

  function closeActionMenu(restoreFocus = true): void {
    setActionMenu(null);
    if (restoreFocus) {
      window.setTimeout(() => actionMenuTriggerRef.current?.focus(), 0);
    }
  }

  function openActionMenu(
    next: CatalogActionMenu,
    trigger: HTMLButtonElement,
  ): void {
    actionMenuTriggerRef.current = trigger;
    setDialog(null);
    setActionMenu(next);
  }

  useEffect(() => {
    if (actionMenu === null) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      closeActionMenu();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [actionMenu]);

  const catalogModalOpen = actionMenu !== null || dialog !== null;
  useEffect(() => {
    if (!catalogModalOpen) return undefined;
    const bodyOverflow = document.body.style.overflow;
    const documentOverflow = document.documentElement.style.overflow;
    document.body.style.overflow = "hidden";
    document.documentElement.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = bodyOverflow;
      document.documentElement.style.overflow = documentOverflow;
    };
  }, [catalogModalOpen]);

  useEffect(() => {
    if (!supported) return;
    const controller = new AbortController();
    const handle = window.setTimeout(() => {
      transport.listAgentProjects({
        search: search.trim() || undefined,
        includeArchived,
        limit: 200,
      }, controller.signal).then((result) => {
        if (controller.signal.aborted) return;
        const selectedProject = result.projects.find(
          (project) => project.project_id === selectedProjectId,
        );
        if (selectedProject !== undefined) {
          selectedProjectSnapshotRef.current = selectedProject;
        }
        setProjects(result.projects);
        setError("");
        const filtering = search.trim() !== "";
        if (selectedProject === undefined && !filtering) {
          const preferredProject = result.projects.find((project) => (
            project.archived_at === null && project.session_count > 0
          )) ?? result.projects[0];
          onProjectChange(preferredProject?.project_id ?? null);
        }
        if (
          result.projects.length === 0
          && !filtering
          && !initialCatalogReported.current
        ) {
          initialCatalogReported.current = true;
          onInitialCatalogLoad?.(null);
        }
      }).catch((caught: unknown) => {
        if (controller.signal.aborted) return;
        setProjects((previous) => previous ?? []);
        setError(failureCopy(caught));
      });
    }, search.trim() ? 140 : 0);
    return () => {
      controller.abort();
      window.clearTimeout(handle);
    };
  }, [includeArchived, onInitialCatalogLoad, onProjectChange, refreshKey, refreshNonce, search, selectedProjectId, supported, transport]);

  useEffect(() => {
    const searchingAllProjects = normalizedSearch !== "";
    if (!supported || (selectedProjectId === null && !searchingAllProjects)) {
      setCatalogSessions([]);
      return;
    }
    const controller = new AbortController();
    const handle = window.setTimeout(() => {
      transport.listAgentCatalogSessions({
        projectId: searchingAllProjects ? undefined : selectedProjectId ?? undefined,
        search: normalizedSearch || undefined,
        includeArchived,
        limit: 200,
      }, controller.signal).then((result) => {
        if (controller.signal.aborted) return;
        setCatalogSessions(result.sessions);
        setError("");
        if (
          !initialCatalogReported.current
          && search.trim() === ""
          && !includeArchived
        ) {
          initialCatalogReported.current = true;
          onInitialCatalogLoad?.(result.sessions[0] ?? null);
        }
      }).catch((caught: unknown) => {
        if (controller.signal.aborted) return;
        setCatalogSessions((previous) => previous ?? []);
        setError(failureCopy(caught));
      });
    }, search.trim() ? 140 : 0);
    return () => {
      controller.abort();
      window.clearTimeout(handle);
    };
  }, [includeArchived, normalizedSearch, onInitialCatalogLoad, refreshKey, refreshNonce, selectedProjectId, supported, transport]);

  function openCatalogSession(
    session: AgentCatalogSession,
    live: AgentSessionView | undefined,
  ): void {
    if (session.project_id !== selectedProjectId) {
      onProjectChange(session.project_id);
    }
    if (live !== undefined) onOpenLiveSession(live);
    else onOpenUnavailableSession(session);
  }

  async function mutate(
    key: string,
    operation: (signal: AbortSignal) => Promise<unknown>,
  ): Promise<boolean> {
    if (disabled || !supported || mutationRef.current !== null) return false;
    const controller = new AbortController();
    const owner = mutationOwnerRef.current + 1;
    mutationOwnerRef.current = owner;
    mutationRef.current = { controller, key, owner };
    setActionMenu(null);
    setBusyKey(key);
    setError("");
    try {
      await operation(controller.signal);
      if (controller.signal.aborted || mutationRef.current?.owner !== owner) return false;
      catalogSyncRef.current?.notify();
      setDialog(null);
      setDialogValue("");
      refresh();
      return true;
    } catch (caught) {
      if (controller.signal.aborted || mutationRef.current?.owner !== owner) return false;
      setError(failureCopy(caught));
      refresh();
      return false;
    } finally {
      if (mutationRef.current?.owner === owner) {
        mutationRef.current = null;
        setBusyKey("");
      }
    }
  }

  async function updateCatalogSession(
    sessionId: string,
    command: UpdateAgentCatalogSession,
  ): Promise<boolean> {
    if (!supported) return false;
    const result: { session: AgentCatalogSession | null } = { session: null };
    const updated = await mutate(`session:${sessionId}`, async (signal) => {
      result.session = await transport.updateAgentCatalogSession(
        sessionId,
        command,
        signal,
      );
    });
    if (updated && result.session !== null) onSessionUpdated?.(result.session);
    return updated;
  }

  function openDialog(next: CatalogDialog, trigger?: HTMLElement): void {
    dialogTriggerRef.current = actionMenu === null
      ? trigger ?? document.activeElement as HTMLElement
      : actionMenuTriggerRef.current;
    setActionMenu(null);
    setDialog(next);
    setMoveDestinations(null);
    setMoveDestinationError("");
    setDialogValue(
      next.kind === "rename-project" ? next.project.name
        : next.kind === "rename-session" ? next.session.title
          : next.kind === "fork-session" ? branchTitle(next.session.title)
          : next.kind === "move-session" ? ""
          : "",
    );
  }

  function closeDialog(restoreFocus = true): void {
    setDialog(null);
    setDialogValue("");
    setMoveDestinations(null);
    setMoveDestinationError("");
    if (restoreFocus) {
      window.setTimeout(() => dialogTriggerRef.current?.focus(), 0);
    }
  }

  useEffect(() => {
    if (dialog === null) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || mutationRef.current !== null) return;
      event.preventDefault();
      closeDialog();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [dialog]);

  async function submitDialog(): Promise<void> {
    if (!supported || disabled || dialog === null) return;
    if (dialog.kind === "create-project") {
      const name = dialogValue.trim();
      if (!name) return;
      let createdProjectId: string | null = null;
      const created = await mutate("create-project", async (signal) => {
        const project = await transport.createAgentProject({ name }, signal);
        createdProjectId = project.project_id;
      });
      if (created && createdProjectId !== null) onProjectChange(createdProjectId);
      return;
    }
    if (dialog.kind === "rename-project") {
      const name = dialogValue.trim();
      if (!name) return;
      await mutate(`project:${dialog.project.project_id}`, (signal) => transport.updateAgentProject(
        dialog.project.project_id,
        { expected_revision: dialog.project.revision, name },
        signal,
      ));
      return;
    }
    if (dialog.kind === "rename-session") {
      const title = dialogValue.trim();
      if (!title) return;
      await updateCatalogSession(
        dialog.session.session_id,
        { expected_revision: dialog.session.revision, title },
      );
      return;
    }
    if (dialog.kind === "move-session") {
      if (!dialogValue || dialogValue === dialog.session.project_id) return;
      await updateCatalogSession(
        dialog.session.session_id,
        { expected_revision: dialog.session.revision, project_id: dialogValue },
      );
      return;
    }
    if (dialog.kind === "fork-session") {
      const title = dialogValue.trim();
      if (!title || onForkSession === undefined) return;
      await mutate(`fork:${dialog.session.session_id}`, (signal) => (
        onForkSession(dialog.session, title, signal)
      ));
      return;
    }
    if (dialog.kind === "delete-project") {
      const deleted = await mutate(`project:${dialog.project.project_id}`, async (signal) => {
        await transport.deleteAgentProject(
          dialog.project.project_id,
          { expected_revision: dialog.project.revision },
          signal,
        );
      });
      if (deleted && selectedProjectId === dialog.project.project_id) onProjectChange(null);
      return;
    }
    const deleted = await mutate(`session:${dialog.session.session_id}`, (signal) => (
      transport.deleteAgentCatalogSession(
        dialog.session.session_id,
        {
          expected_catalog_revision: dialog.session.revision,
          expected_history_revision: dialog.session.history_revision,
        },
        signal,
      )
    ));
    if (deleted) onSessionDeleted?.(dialog.session.session_id);
  }

  if (collapsed) {
    const selectedProject = projects?.find((project) => project.project_id === selectedProjectId)
      ?? (selectedProjectSnapshotRef.current?.project_id === selectedProjectId
        ? selectedProjectSnapshotRef.current
        : undefined);
    return (
      <nav aria-label="Agent projects and chats (collapsed)" className="agent-rail agent-rail--collapsed">
        <button
          aria-label="Expand projects and chats"
          className="agent-rail__icon-button"
          onClick={onToggleCollapsed}
          title="Expand projects and chats"
          type="button"
        >›</button>
        <button
          aria-label="New chat"
          className="agent-rail__collapsed-new"
          disabled={newChatDisabled}
          onClick={(event) => onNewChat(selectedProjectId, event.currentTarget)}
          title="New chat"
          type="button"
        >+</button>
        <span
          aria-label={selectedProject ? `Current project: ${selectedProject.name}` : "No project selected"}
          className="agent-rail__project-mark"
          title={selectedProject?.name ?? "No project selected"}
        >{selectedProject?.name.trim().charAt(0).toLocaleUpperCase() || "—"}</span>
        <span aria-label={`${catalogSessions?.length ?? liveSessions?.length ?? 0} chats`} className="agent-rail__collapsed-count">
          {catalogSessions?.length ?? liveSessions?.length ?? 0}
        </span>
      </nav>
    );
  }

  if (!supported) {
    return (
      <nav aria-label="Agent sessions" className="agent-rail">
        <header className="agent-rail__header">
          <div><small>Agent</small><strong>Live sessions</strong></div>
          <div className="agent-rail__header-actions">
            <button aria-label="Collapse projects and chats" className="agent-rail__icon-button" onClick={onToggleCollapsed} title="Collapse projects and chats" type="button">‹</button>
            <button className="button button--primary" disabled={newChatDisabled} onClick={(event) => onNewChat(null, event.currentTarget)} type="button">New chat</button>
          </div>
        </header>
        <p className="agent-rail__truth">These chats are temporary until the local app restarts.</p>
        <ul className="agent-rail__sessions">
          {(liveSessions ?? []).map((session) => (
            <li key={session.session_id} data-current={session.session_id === currentSessionId ? "true" : undefined}>
              <button
                aria-label={`${liveSessionTitle(session)} · ${sessionStatus({} as AgentCatalogSession, session, draftSessionIds?.has(session.session_id))}`}
                onClick={() => onOpenLiveSession(session)}
                type="button"
              >
                <strong>{liveSessionTitle(session)}</strong>
                <small>{sessionStatus({} as AgentCatalogSession, session, draftSessionIds?.has(session.session_id))}</small>
              </button>
              <button
                aria-label={`Close session ${liveSessionTitle(session)}`}
                disabled={disabled || session.closing || session.cleanup_unconfirmed}
                onClick={() => onCloseLiveSession(session)}
                type="button"
              >×</button>
            </li>
          ))}
        </ul>
      </nav>
    );
  }

  return (
    <nav aria-label="Agent projects and chats" className="agent-rail">
      <header className="agent-rail__header">
        <div><small>Local Agent</small><strong>Projects</strong></div>
        <div className="agent-rail__header-actions">
          <button aria-label="Collapse projects and chats" className="agent-rail__icon-button" onClick={onToggleCollapsed} title="Collapse projects and chats" type="button">‹</button>
          <button
            aria-label="Create project"
            className="agent-rail__icon-button"
            disabled={disabled || Boolean(busyKey)}
            onClick={(event) => openDialog({ kind: "create-project" }, event.currentTarget)}
            title="Create project"
            type="button"
          >+</button>
        </div>
      </header>

      <button
        className="button button--primary agent-rail__new-chat"
        disabled={newChatDisabled}
        onClick={(event) => onNewChat(selectedProjectId, event.currentTarget)}
        type="button"
      >New chat</button>

      <label className="agent-rail__search">
        <span className="sr-only">Search projects and chats</span>
        <input
          maxLength={120}
          onChange={(event) => setSearch(event.currentTarget.value)}
          placeholder="Search projects and chats"
          type="search"
          value={search}
        />
      </label>

      {error && <div className="agent-rail__error" role="alert"><span>{error}</span><button onClick={refresh} type="button">Retry</button></div>}

      <div className="agent-rail__project-list" role="list" aria-label="Projects">
        {projects === null ? <p role="status">Loading projects…</p> : projects.length === 0 ? (
          <p>No project matches this view. Create one, or start a chat to use Personal workspace.</p>
        ) : projectItems.slice(projectPage.start, projectPage.end).map((project) => (
          <div
            className="agent-rail__project"
            data-archived={project.archived_at ? "true" : undefined}
            data-current={project.project_id === selectedProjectId ? "true" : undefined}
            key={project.project_id}
            role="listitem"
          >
            <button
              className="agent-rail__project-pick"
              onClick={() => onProjectChange(project.project_id)}
              type="button"
            >
              <span aria-hidden="true" className="agent-rail__disclosure">{project.project_id === selectedProjectId ? "▾" : "›"}</span>
              <span><strong>{project.name}</strong><small>{project.session_count} {project.session_count === 1 ? "chat" : "chats"}{project.archived_at ? " · archived" : ""}</small></span>
              {project.pinned && <span className="agent-rail__pin">Pinned</span>}
            </button>
            <button
              aria-expanded={actionMenu?.kind === "project" && actionMenu.project.project_id === project.project_id}
              aria-haspopup="dialog"
              aria-label={`Project actions for ${project.name}`}
              className="agent-rail__menu-trigger"
              disabled={disabled || Boolean(busyKey)}
              onClick={(event) => openActionMenu({ kind: "project", project }, event.currentTarget)}
              type="button"
            >•••</button>
          </div>
        ))}
      </div>
      <BoundedListPager label="Agent project pages" page={projectPage} />

      <section aria-labelledby="agent-rail-chats" className="agent-rail__chat-section">
        <div className="agent-rail__section-head">
          <h2 id="agent-rail-chats">{normalizedSearch ? "Matching chats" : "Chats"}</h2>
          <span>{catalogSessions?.length ?? 0}</span>
        </div>
        {selectedProjectId === null && !normalizedSearch ? <p>Select or create a project.</p>
          : catalogSessions === null ? <p role="status">Loading chats…</p>
            : catalogSessions.length === 0 ? <p>{normalizedSearch ? "No chat matches your search." : "No chat matches this view."}</p>
              : (
                <ul className="agent-rail__sessions">
                  {sessionItems.slice(sessionPage.start, sessionPage.end).map((session) => {
                    const live = liveById.get(session.session_id);
                    const projectContext = normalizedSearch
                      ? projectNameById.get(session.project_id) ?? "Unknown project"
                      : "";
                    const status = sessionStatus(
                      session,
                      live,
                      draftSessionIds?.has(session.session_id),
                    );
                    return (
                      <li
                        data-archived={session.archived_at ? "true" : undefined}
                        data-current={session.session_id === currentSessionId ? "true" : undefined}
                        key={session.session_id}
                      >
                        <button
                          aria-label={`${session.title} · ${projectContext ? `${projectContext} · ` : ""}${status}${session.model_alias ? ` · ${session.model_alias}` : ""}`}
                          className="agent-rail__session-pick"
                          onClick={() => openCatalogSession(session, live)}
                          type="button"
                        >
                          <strong>{session.title}</strong>
                          <small>{projectContext ? `${projectContext} · ` : ""}{status}{session.model_alias ? ` · ${session.model_alias}` : ""}</small>
                        </button>
                        <button
                          aria-expanded={actionMenu?.kind === "session" && actionMenu.session.session_id === session.session_id}
                          aria-haspopup="dialog"
                          aria-label={`Chat actions for ${session.title}`}
                          className="agent-rail__menu-trigger"
                          disabled={disabled || Boolean(busyKey)}
                          onClick={(event) => openActionMenu({ kind: "session", session }, event.currentTarget)}
                          type="button"
                        >•••</button>
                      </li>
                    );
                  })}
                </ul>
              )}
        <BoundedListPager label="Agent chat pages" page={sessionPage} />
      </section>

      <label className="agent-rail__archived">
        <input checked={includeArchived} onChange={(event) => setIncludeArchived(event.currentTarget.checked)} type="checkbox" />
        <span>Show archived</span>
      </label>

      <footer className="agent-rail__truth">
        Every chat keeps local navigation. Chats marked Save locally also retain bounded conversation history; approvals and reusable authority never persist.
      </footer>

      {actionMenu && (
        <div
          className="agent-rail__action-backdrop"
          onMouseDown={(event) => {
            if (event.currentTarget === event.target) closeActionMenu();
          }}
        >
          <section
            aria-labelledby="agent-catalog-actions-title"
            aria-modal="true"
            className="agent-rail__action-dialog"
            onKeyDownCapture={trapModalFocus}
            role="dialog"
            tabIndex={-1}
          >
            <header>
              <div>
                <small>{actionMenu.kind === "project" ? "Project" : "Chat"}</small>
                <h2 id="agent-catalog-actions-title">
                  {actionMenu.kind === "project"
                    ? `Project actions for ${actionMenu.project.name}`
                    : `Chat actions for ${actionMenu.session.title}`}
                </h2>
              </div>
              <button aria-label="Close actions" className="button button--ghost" onClick={() => closeActionMenu()} type="button">Close</button>
            </header>
            <div className="agent-rail__action-grid">
              {actionMenu.kind === "project" ? (
                <>
                  <button autoFocus disabled={disabled || Boolean(busyKey)} onClick={() => openDialog({ kind: "rename-project", project: actionMenu.project })} type="button">Rename</button>
                  <button disabled={disabled || Boolean(busyKey)} onClick={() => void mutate(`project:${actionMenu.project.project_id}`, (signal) => transport.updateAgentProject(actionMenu.project.project_id, { expected_revision: actionMenu.project.revision, pinned: !actionMenu.project.pinned }, signal))} type="button">{actionMenu.project.pinned ? "Unpin" : "Pin"}</button>
                  {!actionMenu.project.is_default && <button disabled={disabled || Boolean(busyKey)} onClick={() => void mutate(`project:${actionMenu.project.project_id}`, (signal) => transport.updateAgentProject(actionMenu.project.project_id, { expected_revision: actionMenu.project.revision, archived: !actionMenu.project.archived_at }, signal))} type="button">{actionMenu.project.archived_at ? "Restore" : "Archive"}</button>}
                  {!actionMenu.project.is_default && actionMenu.project.session_count === 0 && <button className="agent-rail__danger" disabled={disabled || Boolean(busyKey)} onClick={() => openDialog({ kind: "delete-project", project: actionMenu.project })} type="button">Delete</button>}
                </>
              ) : (() => {
                const session = actionMenu.session;
                const live = liveById.get(session.session_id);
                return <>
                  <button autoFocus disabled={disabled || Boolean(busyKey)} onClick={() => openDialog({ kind: "rename-session", session })} type="button">Rename</button>
                  <button disabled={disabled || Boolean(busyKey)} onClick={() => openDialog({ kind: "move-session", session })} type="button">Move to project</button>
                  {session.retention_policy === "local_history" && onForkSession !== undefined && (
                    <button
                      disabled={disabled || Boolean(session.archived_at || live?.running || live?.closing || live?.pending_approval_id)}
                      onClick={() => openDialog({ kind: "fork-session", session })}
                      type="button"
                    >Fork latest completed turn</button>
                  )}
                  <button disabled={disabled || Boolean(busyKey)} onClick={() => void updateCatalogSession(session.session_id, { expected_revision: session.revision, pinned: !session.pinned })} type="button">{session.pinned ? "Unpin" : "Pin"}</button>
                  {live
                    ? <button disabled={disabled || Boolean(busyKey)} onClick={() => { closeActionMenu(false); onCloseLiveSession(live); }} type="button">Close live chat</button>
                    : <button disabled={disabled || Boolean(busyKey)} onClick={() => void updateCatalogSession(session.session_id, { expected_revision: session.revision, archived: !session.archived_at })} type="button">{session.archived_at ? "Restore" : "Archive"}</button>}
                  {!live && <button className="agent-rail__danger" disabled={disabled || Boolean(busyKey)} onClick={() => openDialog({ kind: "delete-session", session })} type="button">Delete</button>}
                </>;
              })()}
            </div>
          </section>
        </div>
      )}

      {dialog && (
        <div
          aria-labelledby="agent-catalog-dialog-title"
          aria-modal="true"
          className="agent-rail__dialog-backdrop"
          onMouseDown={(event) => {
            if (event.currentTarget === event.target && mutationRef.current === null) {
              closeDialog();
            }
          }}
          role="dialog"
        >
          <form
            className="agent-rail__dialog"
            onKeyDownCapture={trapModalFocus}
            onSubmit={(event) => { event.preventDefault(); void submitDialog(); }}
            tabIndex={-1}
          >
            <h2 id="agent-catalog-dialog-title">
              {dialog.kind === "create-project" ? "Create project"
                : dialog.kind === "rename-project" ? "Rename project"
                  : dialog.kind === "rename-session" ? "Rename chat"
                    : dialog.kind === "fork-session" ? "Fork chat"
                    : dialog.kind === "move-session" ? "Move chat"
                    : dialog.kind === "delete-project" ? "Delete project"
                      : "Delete chat"}
            </h2>
            {dialog.kind === "create-project" || dialog.kind === "rename-project" || dialog.kind === "rename-session" || dialog.kind === "fork-session" ? (
              <label>
                <span>{dialog.kind === "rename-session" || dialog.kind === "fork-session" ? "Chat name" : "Project name"}</span>
                <input autoFocus maxLength={120} onChange={(event) => setDialogValue(event.currentTarget.value)} value={dialogValue} />
              </label>
            ) : dialog.kind === "move-session" ? (
              moveDestinations === null ? (
                <p role="status">Loading active projects…</p>
              ) : moveDestinationError ? (
                <div className="agent-rail__error" role="alert">
                  <span>{moveDestinationError}</span>
                  <button onClick={() => setMoveDestinationNonce((value) => value + 1)} type="button">Retry projects</button>
                </div>
              ) : moveDestinations.length === 0 ? (
                <p role="status">There is no other active project. Create or restore a project before moving this chat.</p>
              ) : (
                <label>
                  <span>Destination project</span>
                  <select autoFocus onChange={(event) => setDialogValue(event.currentTarget.value)} value={dialogValue}>
                    {moveDestinations.map((project) => (
                      <option key={project.project_id} value={project.project_id}>{project.name}</option>
                    ))}
                  </select>
                </label>
              )
            ) : (
              <p>{dialog.kind === "delete-session" && dialog.session.retention_policy === "local_history"
                ? "This permanently deletes the selected chat record and its retained local conversation. Workspace files are not deleted."
                : "This removes only the selected navigation record. It does not delete workspace files."}</p>
            )}
            {dialog.kind === "fork-session" && (
              <p>
                Copies retained history through the latest completed turn. The branch starts inactive and receives no approvals, protected-action authority, staged attachments, or artifact ownership.
              </p>
            )}
            <div className="agent-rail__dialog-actions">
              <button className="button button--ghost" disabled={Boolean(busyKey)} onClick={() => closeDialog()} type="button">Cancel</button>
              <button className={dialog.kind.startsWith("delete") ? "button agent-rail__danger-button" : "button button--primary"} disabled={disabled || Boolean(busyKey) || ((dialog.kind === "create-project" || dialog.kind.startsWith("rename") || dialog.kind === "move-session" || dialog.kind === "fork-session") && !dialogValue.trim())} type="submit">
                {busyKey ? "Saving…" : dialog.kind.startsWith("delete") ? "Delete" : dialog.kind === "fork-session" ? "Create branch" : "Save"}
              </button>
            </div>
          </form>
        </div>
      )}
    </nav>
  );
}
