// Reviewed synthetic-only browser probe. No native confirmation is manufactured.
import { chromium } from "playwright";
import { open, readdir, lstat } from "node:fs/promises";
import path from "node:path";

const ORIGINAL = "export const exampleValue = 1;\n";
const DRAFT = "export const exampleValue = 2;\n";
const CHANGED = "export const exampleValue = 3;\n";
const PROJECT = "Synthetic workspace review project";
const flags = ["browser_started", "browser_closed", "file_read", "diff_verified", "apply_disabled",
  "native_refused", "csrf_refused", "traversal_refused", "stale_refused", "discard_reopened",
  "file_unchanged_after_refusal", "fixture_restored", "readonly_session"];
const report = { contract: "packaged-agent-workspace-probe.v1", passed: false, error_code: null,
  file_response: null, traversal_response: null, stale_response: null,
  ...Object.fromEntries(flags.map(key => [key, false])), projects_created: 0, chats_created: 0,
  previews_created: 0, apply_attempts: 0, fixture_mutations: 0, forbidden_mutations: 0,
  external_requests: 0, page_errors: 0, server_failures: 0,
  project_requests: 0, session_requests: 0, preview_requests: 0, apply_requests: 0 };
let browser, file, fixturePath, phase = "invalid_environment", mutated = false;
const requireThat = condition => { if (!condition) throw new Error("probe_assertion"); };
async function fileText() {
  const info = await file.stat();
  requireThat(info.isFile() && info.size === Buffer.byteLength(ORIGINAL));
  const buffer = Buffer.alloc(info.size + 1);
  const { bytesRead } = await file.read(buffer, 0, buffer.length, 0);
  requireThat(bytesRead === info.size);
  return buffer.subarray(0, bytesRead).toString("utf8");
}
async function writeFixture(text) {
  // Production inspections intentionally refuse an existing writable handle.
  // Keep the identity pin read-only; close this short-lived writer before HTTP.
  const pinned = await file.stat();
  const before = await lstat(fixturePath);
  requireThat(before.isFile() && !before.isSymbolicLink() && before.nlink === 1
    && before.ino === pinned.ino && before.dev === pinned.dev);
  const writer = await open(fixturePath, "r+");
  try {
    const opened = await writer.stat();
    requireThat(opened.isFile() && opened.nlink === 1 && opened.ino === pinned.ino
      && opened.dev === pinned.dev && opened.size === Buffer.byteLength(ORIGINAL));
    const result = await writer.write(Buffer.from(text), 0, Buffer.byteLength(text), 0);
    requireThat(result.bytesWritten === Buffer.byteLength(text));
    await writer.sync();
    const after = await lstat(fixturePath);
    requireThat(after.ino === pinned.ino && after.dev === pinned.dev && !after.isSymbolicLink());
  } finally { await writer.close(); }
}
async function waitForOriginalEditor(page) {
  // The textarea exists while the file HTTP request is still in flight.
  // Visibility alone does not establish that React committed the loaded draft.
  await page.waitForFunction(expected => {
    const editor = document.querySelector('textarea[aria-label="Workspace file editor"]');
    return editor !== null && !editor.disabled && editor.value === expected;
  }, ORIGINAL, { timeout: 12000 });
}
try {
  const base = new URL(process.env.PE_PACKAGED_BASE_URL ?? "");
  const workspace = process.env.PE_PACKAGED_WORKSPACE;
  const executable = process.env.PE_PACKAGED_BROWSER_EXECUTABLE;
  requireThat(base.protocol === "http:" && base.hostname === "127.0.0.1"
    && Number(base.port) >= 1024 && ![8765, 8766].includes(Number(base.port))
    && base.pathname === "/" && !base.search && !base.hash && !base.username && !base.password
    && workspace && path.isAbsolute(workspace) && executable && path.isAbsolute(executable));
  const fixture = path.join(workspace, "example.ts");
  fixturePath = fixture;
  const before = await lstat(fixture);
  requireThat(before.isFile() && !before.isSymbolicLink() && before.nlink === 1);
  file = await open(fixture, "r");
  const opened = await file.stat();
  requireThat(before.ino !== 0 && before.ino === opened.ino && before.dev === opened.dev);
  requireThat(await fileText() === ORIGINAL);
  requireThat(JSON.stringify(await readdir(workspace)) === '["example.ts"]');
  phase = "browser_failed";
  browser = await chromium.launch({ executablePath: executable, headless: true });
  report.browser_started = true;
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 }, serviceWorkers: "block" });
  let applyPath = null, workspaceEndpoint = null;
  await context.route("**/*", async route => {
    const request = route.request(), url = new URL(request.url());
    if (url.origin !== base.origin) { report.external_requests++; return route.abort(); }
    let safePost = false;
    if (request.method() === "POST") {
      const slot = url.pathname === "/v1/agent/projects" ? ["project_requests", 1]
        : url.pathname === "/v1/agent/sessions" ? ["session_requests", 1]
        : workspaceEndpoint !== null && url.pathname === workspaceEndpoint + "/previews" ? ["preview_requests", 2]
        : applyPath !== null && url.pathname === applyPath ? ["apply_requests", 2] : null;
      if (slot !== null) { report[slot[0]]++; safePost = report[slot[0]] <= slot[1]; }
    }
    if (!["GET", "HEAD", "OPTIONS"].includes(request.method()) && !safePost) {
      report.forbidden_mutations++; return route.abort();
    }
    return route.continue();
  });
  const page = await context.newPage();
  page.setDefaultTimeout(12000);
  page.on("pageerror", () => report.page_errors++);
  page.on("response", response => {
    if (response.status() >= 500 && !(response.status() === 503
      && new URL(response.url()).pathname === applyPath)) report.server_failures++;
  });
  await page.goto(`${base.origin}/agent`, { waitUntil: "domcontentloaded" });
  const rail = page.getByRole("navigation", { name: "Agent projects and chats", exact: true });
  phase = "project_failed";
  await rail.getByRole("button", { name: "Create project", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Create project", exact: true });
  await dialog.getByLabel("Project name", { exact: true }).fill(PROJECT);
  const projectResponse = page.waitForResponse(r => r.request().method() === "POST"
    && new URL(r.url()).pathname === "/v1/agent/projects");
  await dialog.getByRole("button", { name: "Save", exact: true }).click();
  requireThat((await projectResponse).status() === 201); report.projects_created = 1;
  await rail.locator(".agent-rail__project-pick").filter({ hasText: PROJECT }).click();
  phase = "chat_failed";
  await rail.getByRole("button", { name: "New chat", exact: true }).click();
  const setup = page.getByRole("dialog", { name: "New session", exact: true });
  requireThat(await setup.getByLabel("Agent model", { exact: true }).inputValue() === "");
  await setup.getByLabel("Workspace folder", { exact: true }).fill(workspace);
  requireThat(await setup.getByRole("group", { name: "Protected actions", exact: true }).getAttribute("disabled") !== null);
  const sessionResponse = page.waitForResponse(r => r.request().method() === "POST"
    && new URL(r.url()).pathname === "/v1/agent/sessions");
  await setup.getByRole("button", { name: "Open read-only chat without model", exact: true }).click();
  const created = await sessionResponse;
  requireThat(created.status() === 201);
  const session = await created.json();
  requireThat(/^[0-9a-f]{32}$/u.test(session.session_id));
  requireThat(["allow_writes", "allow_commands", "allow_web"].every(key => session.settings?.[key] === false)
    && session.model_alias === null && session.running === false && session.pending_approval_id === null);
  report.readonly_session = true; report.chats_created = 1;
  const endpoint = `/v1/agent/sessions/${session.session_id}/workspace`;
  workspaceEndpoint = endpoint;
  async function request(method, suffix, body, csrf = true) {
    return page.evaluate(async ({ method, endpoint, suffix, body, csrf }) => {
      async function boundedJson(response) {
        const reader = response.body.getReader();
        const chunks = []; let total = 0;
        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            total += value.byteLength;
            if (total > 65536) throw new Error("response_bound");
            chunks.push(value);
          }
        } finally { await reader.cancel(); reader.releaseLock(); }
        const bytes = new Uint8Array(total); let offset = 0;
        for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
        return JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
      }
      const authResponse = await fetch("/auth/session", { signal: AbortSignal.timeout(5000) });
      if (authResponse.status !== 200) throw new Error("auth_failed");
      const auth = await boundedJson(authResponse);
      const headers = { "Accept": "application/json", "Content-Type": "application/json" };
      if (csrf) headers["X-Prompt-Enhancer-CSRF"] = auth.csrf_token;
      const response = await fetch(endpoint + suffix, { method, headers, signal: AbortSignal.timeout(5000),
        ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
      return { status: response.status, body: await boundedJson(response) };
    }, { method, endpoint, suffix, body, csrf });
  }
  phase = "file_read_failed";
  await page.getByRole("button", { name: "Files & review", exact: true }).click();
  const fileButton = page.locator(".agent-workspace__tree")
    .getByRole("button", { name: "example.ts", exact: true });
  const openedResponse = page.waitForResponse(r => r.request().method() === "GET"
    && new URL(r.url()).pathname === endpoint + "/file"
    && new URL(r.url()).searchParams.get("path") === "example.ts");
  await fileButton.click();
  phase = "file_response_failed";
  const openedFile = await openedResponse;
  report.file_response = { status: openedFile.status(), error_category: "invalid_json",
    content_present: false, content_string: false, content_matches: false };
  const openedBody = await openedFile.json();
  const fileErrors = new Set(["workspace_file_unavailable", "workspace_file_changed", "workspace_root_changed",
    "workspace_link_or_reparse_refused", "workspace_file_too_large", "workspace_binary_refused",
    "workspace_text_invalid", "workspace_line_endings_unsupported", "workspace_directory_unavailable",
    "path_invalid", "path_outside_workspace", "session_not_found", "session_closing", "workspace_revision_changed"]);
  const contentPresent = openedBody !== null && typeof openedBody === "object"
    && Object.hasOwn(openedBody, "content");
  report.file_response = { status: openedFile.status(),
    error_category: openedFile.status() === 200 ? null
      : fileErrors.has(openedBody?.detail?.code) ? openedBody.detail.code : "other",
    content_present: contentPresent,
    content_string: contentPresent && typeof openedBody.content === "string",
    content_matches: contentPresent && openedBody.content === ORIGINAL };
  requireThat(openedFile.status() === 200 && report.file_response.content_matches);
  phase = "editor_ready_failed";
  const editor = page.getByLabel("Workspace file editor", { exact: true });
  await waitForOriginalEditor(page);
  requireThat(await editor.inputValue() === ORIGINAL); report.file_read = true;
  phase = "preview_failed";
  await editor.fill(DRAFT);
  const previewResponse = page.waitForResponse(r => r.request().method() === "POST"
    && new URL(r.url()).pathname === endpoint + "/previews");
  await page.getByRole("button", { name: "Review diff", exact: true }).click();
  const response = await previewResponse;
  requireThat(response.status() === 201);
  const preview = await response.json(); report.previews_created = 1;
  const review = page.getByRole("region", { name: "Manual edit review", exact: true });
  await review.waitFor({ state: "visible" });
  requireThat(preview.diff.includes("-" + ORIGINAL.trim()) && preview.diff.includes("+" + DRAFT.trim()));
  requireThat((await review.innerText()).includes(ORIGINAL.trim()) && (await review.innerText()).includes(DRAFT.trim()));
  report.diff_verified = true;
  requireThat(await review.getByRole("button", { name: "Apply reviewed edit", exact: true }).isDisabled());
  report.apply_disabled = true;
  requireThat(/^[0-9a-f]{32}$/u.test(preview.preview_id));
  applyPath = `${endpoint}/previews/${preview.preview_id}/apply`;
  const body = { path: "example.ts", content: DRAFT, expected_revision: preview.expected_revision,
    proposed_revision: preview.proposed_revision, line_ending: preview.line_ending,
    confirmation: "apply_reviewed_workspace_edit" };
  phase = "refusal_failed";
  let result = await request("POST", `/previews/${preview.preview_id}/apply`, body, false);
  report.apply_attempts++;
  requireThat(result.status === 403); report.csrf_refused = true;
  result = await request("POST", `/previews/${preview.preview_id}/apply`, body);
  report.apply_attempts++;
  requireThat(result.status === 503 && result.body.detail === "user-presence confirmation is unavailable");
  report.native_refused = true;
  requireThat(await fileText() === ORIGINAL && JSON.stringify(await readdir(workspace)) === '["example.ts"]');
  report.file_unchanged_after_refusal = true;
  result = await request("GET", "/file?path=..%2Fexample.ts");
  report.traversal_response = { status: result.status,
    error_category: fileErrors.has(result.body?.detail?.code) ? result.body.detail.code : "other" };
  requireThat(result.status === 403 && result.body.detail?.code === "path_outside_workspace");
  report.traversal_refused = true;
  phase = "discard_failed";
  await page.getByRole("button", { name: "Discard draft", exact: true }).click();
  await page.getByRole("dialog", { name: "Discard workspace changes?", exact: true })
    .getByRole("button", { name: "Discard manual edit", exact: true }).click();
  const reopenedResponse = page.waitForResponse(r => r.request().method() === "GET"
    && new URL(r.url()).pathname === endpoint + "/file"
    && new URL(r.url()).searchParams.get("path") === "example.ts");
  await fileButton.click();
  const reopened = await reopenedResponse;
  requireThat(reopened.status() === 200 && (await reopened.json()).content === ORIGINAL);
  await waitForOriginalEditor(page);
  requireThat(await editor.inputValue() === ORIGINAL); report.discard_reopened = true;
  phase = "stale_failed";
  requireThat(await fileText() === ORIGINAL);
  mutated = true;
  await writeFixture(CHANGED); report.fixture_mutations = 1;
  result = await request("POST", "/previews", { path: "example.ts", content: DRAFT,
    expected_revision: preview.expected_revision, line_ending: preview.line_ending });
  report.stale_response = { status: result.status,
    error_category: fileErrors.has(result.body?.detail?.code) ? result.body.detail.code : "other" };
  requireThat(result.status === 409 && result.body.detail?.code === "workspace_revision_changed");
  requireThat(await fileText() === CHANGED); report.stale_refused = true;
} catch { report.error_code = phase; }
finally {
  if (file) {
    try {
      if (mutated) { requireThat(await fileText() === CHANGED); await writeFixture(ORIGINAL); }
      report.fixture_restored = await fileText() === ORIGINAL;
    } catch { report.error_code = "fixture_cleanup_failed"; }
    await file.close().catch(() => { report.error_code = "fixture_cleanup_failed"; });
  }
  if (browser) {
    try { await browser.close(); report.browser_closed = true; }
    catch { report.error_code = "browser_cleanup_failed"; }
  }
}
report.passed = report.error_code === null && flags.every(key => report[key])
  && ["forbidden_mutations", "external_requests", "page_errors", "server_failures"].every(key => report[key] === 0)
  && report.projects_created === 1 && report.chats_created === 1 && report.previews_created === 1
  && report.apply_attempts === 2 && report.fixture_mutations === 1
  && report.project_requests === 1 && report.session_requests === 1
  && report.preview_requests === 2 && report.apply_requests === 2;
if (!report.passed && report.error_code === null) report.error_code = "completion_failed";
process.stdout.write("PACKAGED_AGENT_WORKSPACE_PROBE=" + JSON.stringify(report) + "\n");
process.exitCode = report.passed ? 0 : 1;
