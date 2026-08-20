import { useCallback, useEffect, useState } from "react";
import type { PeerLink, PromptEnhancerTransport, SharedFolder } from "../../shared/api/contracts";
import { TransportError } from "../../shared/api/httpTransport";
import "./TeamFoldersPanel.css";

type TransportSlice = Partial<
  Pick<
    PromptEnhancerTransport,
    "shareFolder" | "listSharedFolders" | "revokeSharedFolder" | "joinSharedFolder" | "listPeerLinks" | "leavePeerLink" | "pullPeerLink" | "pushPeerLink"
  >
>;

/**
 * Team folders (ADR 0018): share one folder with a token, or join a teammate's
 * folder and work in your local copy - a live-folder collaboration mode beside
 * git. The joined copy is an ordinary agent workspace.
 */
export function TeamFoldersPanel({ transport, onUseAsWorkspace }: { transport: TransportSlice; onUseAsWorkspace?: (path: string) => void }) {
  const [shares, setShares] = useState<SharedFolder[] | null>(null);
  const [links, setLinks] = useState<PeerLink[] | null>(null);
  const [freshToken, setFreshToken] = useState<{ shareId: string; token: string } | null>(null);
  const [sharePath, setSharePath] = useState("");
  const [shareName, setShareName] = useState("");
  const [joinUrl, setJoinUrl] = useState("");
  const [joinShareId, setJoinShareId] = useState("");
  const [joinToken, setJoinToken] = useState("");
  const [joinTarget, setJoinTarget] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const available = Boolean(transport.listSharedFolders);

  const refresh = useCallback(async (signal?: AbortSignal) => {
    if (!transport.listSharedFolders || !transport.listPeerLinks) return;
    try {
      const [shareList, linkList] = await Promise.all([transport.listSharedFolders(signal), transport.listPeerLinks(signal)]);
      if (signal?.aborted) return;
      setShares(shareList.shares.filter((s) => !s.revoked_at));
      setLinks([...linkList.links]);
    } catch {
      if (!signal?.aborted) {
        setShares([]);
        setLinks([]);
      }
    }
  }, [transport]);

  useEffect(() => {
    if (!available) return;
    const controller = new AbortController();
    void refresh(controller.signal);
    return () => controller.abort();
  }, [available, refresh]);

  if (!available) return null;

  const fail = (caught: unknown, fallback: string) => {
    const status = caught instanceof TransportError ? caught.status : null;
    setMessage(
      status === 401 ? "The share token was not accepted (revoked or mistyped)."
        : status === 403 ? "That folder cannot be shared."
          : status === 422 ? "Check the folder path / URL - something in the form is not valid."
            : status === 502 ? "The peer could not be reached."
              : fallback,
    );
  };

  const share = async () => {
    if (!transport.shareFolder || !sharePath.trim() || !shareName.trim()) return;
    setBusy(true);
    setMessage("");
    try {
      const created = await transport.shareFolder(sharePath.trim(), shareName.trim());
      setFreshToken(created.share_token ? { shareId: created.share_id, token: created.share_token } : null);
      setSharePath("");
      setShareName("");
      await refresh();
    } catch (caught) {
      fail(caught, "The folder could not be shared.");
    } finally {
      setBusy(false);
    }
  };

  const revoke = async (shareId: string) => {
    if (!transport.revokeSharedFolder) return;
    try {
      await transport.revokeSharedFolder(shareId);
      if (freshToken?.shareId === shareId) setFreshToken(null);
      await refresh();
    } catch (caught) {
      fail(caught, "The share could not be revoked.");
    }
  };

  const join = async () => {
    if (!transport.joinSharedFolder || !joinUrl.trim() || !joinShareId.trim() || !joinToken.trim() || !joinTarget.trim()) return;
    setBusy(true);
    setMessage("");
    try {
      await transport.joinSharedFolder(joinUrl.trim(), joinShareId.trim(), joinToken.trim(), joinTarget.trim());
      setJoinUrl("");
      setJoinShareId("");
      setJoinToken("");
      setJoinTarget("");
      setMessage("Joined. Pull to mirror the folder, then use the local copy as an agent workspace.");
      await refresh();
    } catch (caught) {
      fail(caught, "The folder could not be joined.");
    } finally {
      setBusy(false);
    }
  };

  const sync = async (linkId: string, direction: "pull" | "push") => {
    const call = direction === "pull" ? transport.pullPeerLink : undefined;
    setBusy(true);
    setMessage("");
    try {
      const report = direction === "pull"
        ? await call?.(linkId)
        : await transport.pushPeerLink?.(linkId, "me");
      if (report) {
        setMessage(
          direction === "pull"
            ? `Pulled ${report.pulled} file${report.pulled === 1 ? "" : "s"} (${report.skipped} unchanged).`
            : `Pushed ${report.pushed} file${report.pushed === 1 ? "" : "s"}${report.conflicts ? `, ${report.conflicts} kept as conflict copies on the other side` : ""} (${report.skipped} unchanged).`,
        );
      }
    } catch (caught) {
      fail(caught, "The sync did not complete.");
    } finally {
      setBusy(false);
    }
  };

  const leave = async (linkId: string) => {
    if (!transport.leavePeerLink) return;
    try {
      await transport.leavePeerLink(linkId);
      await refresh();
    } catch (caught) {
      fail(caught, "The link could not be removed.");
    }
  };

  return (
    <section aria-labelledby="team-folders-title" className="team-folders">
      <h2 id="team-folders-title">Team folders</h2>
      <p className="team-folders__note">
        Share one folder (a token is shown once - hand it to your teammate), or join theirs.
        Agents on both sides work in their local copy; simultaneous edits survive as conflict copies. A collaboration mode beside git.
      </p>

      <form className="team-folders__form" onSubmit={(e) => { e.preventDefault(); void share(); }}>
        <h3>Share a folder</h3>
        <input aria-label="Folder to share" onChange={(e) => setSharePath(e.currentTarget.value)} placeholder="D:\team\docs (absolute path)" type="text" value={sharePath} />
        <input aria-label="Share name" onChange={(e) => setShareName(e.currentTarget.value)} placeholder="Name, e.g. team-docs" type="text" value={shareName} />
        <button className="button button--ghost" disabled={busy || !sharePath.trim() || !shareName.trim()} type="submit">Share</button>
      </form>
      {freshToken && (
        <p className="team-folders__token" role="alert">
          Share token (shown once): <code>{freshToken.token}</code>
          <br />Share id: <code>{freshToken.shareId}</code> - give both to your teammate together with this machine&apos;s address.
        </p>
      )}
      {shares && shares.length > 0 && (
        <ul className="team-folders__list">
          {shares.map((s) => (
            <li key={s.share_id}>
              <span><strong>{s.name}</strong> <code>{s.path}</code></span>
              <button className="button button--ghost" onClick={() => void revoke(s.share_id)} type="button">Stop sharing</button>
            </li>
          ))}
        </ul>
      )}

      <form className="team-folders__form" onSubmit={(e) => { e.preventDefault(); void join(); }}>
        <h3>Join a teammate&apos;s folder</h3>
        <input aria-label="Peer URL" onChange={(e) => setJoinUrl(e.currentTarget.value)} placeholder="http://192.168.1.20:8765" type="text" value={joinUrl} />
        <input aria-label="Share id" onChange={(e) => setJoinShareId(e.currentTarget.value)} placeholder="Share id from your teammate" type="text" value={joinShareId} />
        <input aria-label="Share token" onChange={(e) => setJoinToken(e.currentTarget.value)} placeholder="Share token" type="password" value={joinToken} />
        <input aria-label="Local target folder" onChange={(e) => setJoinTarget(e.currentTarget.value)} placeholder="D:\team\docs-copy (local folder for your copy)" type="text" value={joinTarget} />
        <button className="button button--ghost" disabled={busy || !joinUrl.trim() || !joinShareId.trim() || !joinToken.trim() || !joinTarget.trim()} type="submit">Join</button>
      </form>
      {links && links.length > 0 && (
        <ul className="team-folders__list">
          {links.map((l) => (
            <li key={l.link_id}>
              <span><strong>{l.name ?? "folder"}</strong> <code>{l.target}</code></span>
              <span className="team-folders__actions">
                <button className="button button--ghost" disabled={busy} onClick={() => void sync(l.link_id, "pull")} type="button">Pull</button>
                <button className="button button--ghost" disabled={busy} onClick={() => void sync(l.link_id, "push")} type="button">Push</button>
                {onUseAsWorkspace && <button className="button button--ghost" onClick={() => onUseAsWorkspace(l.target)} type="button">Use as workspace</button>}
                <button className="button button--ghost" onClick={() => void leave(l.link_id)} type="button">Leave</button>
              </span>
            </li>
          ))}
        </ul>
      )}
      {message && <p className="team-folders__message" aria-live="polite">{message}</p>}
    </section>
  );
}
