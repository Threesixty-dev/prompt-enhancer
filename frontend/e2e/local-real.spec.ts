import { expect, test, type Page, type Route } from "@playwright/test";

import {
  SYNTHETIC_CURRENT_SESSION_QUALITY_RUN,
  SYNTHETIC_QUALITY_PROJECT_ID,
  SYNTHETIC_QUALITY_SESSION_ID,
  SYNTHETIC_SESSION_METRIC_READINESS,
} from "../src/shared/api/syntheticFixtures";
import { createSyntheticTransport } from "../src/shared/api/syntheticTransport";

const PRIVATE_HEADERS = {
  "Cache-Control": "no-store, private",
  "Content-Type": "application/json",
  Pragma: "no-cache",
};

async function json(
  route: Route,
  body: unknown,
  status = 200,
): Promise<void> {
  await route.fulfill({
    body: JSON.stringify(body),
    headers: PRIVATE_HEADERS,
    status,
  });
}

function integer(value: string | null, fallback: number): number {
  if (value === null) return fallback;
  const parsed = Number.parseInt(value, 10);
  return Number.isSafeInteger(parsed) ? parsed : fallback;
}

function promptCheckFixture() {
  return {
    contract_version: "prompt-check.v1",
    check_id: "e".repeat(32),
    created_at: "2026-08-20T20:01:00Z",
    provider: "other",
    agent_model: null,
    metrics: [{
      key: "prompt.acceptance_testability",
      display_name: "Acceptance testability",
      description: "Checkable acceptance requirements",
      state: "known",
      value: 0.5,
      numerator: 1,
      denominator: 2,
      higher_is_better: true,
      explanation_code: "observed",
      cues: [],
    }],
    context: {
      task_type: "implement",
      language: "en",
      prompt_chars: 30,
      prompt_words: 5,
      sentence_count: 1,
      bullet_count: 0,
      question_count: 0,
      file_references: 1,
      code_identifiers: 0,
      urls: 0,
      prior_context_supplied: 0,
      depends_on_prior_context: false,
      verification_requested: false,
      missing_elements: ["a checkable pass condition"],
    },
    commentary: {
      state: "ok",
      model_alias: "example-local-model",
      prompt_version: "prompt-check-commentary-v1",
      findings: [{ aspect: "verification", severity: "high", why: "No check is named.", suggestion: "Name the focused test command." }],
      reformulated_prompt: "Update example.ts, run the focused test, and report the changed files and result.",
      reformulated_elements: [],
      notes: null,
      caveat: "Local-model suggestion; not measured evidence.",
    },
    summary: "The target is visible, but verification needs a concrete pass condition.",
    engine_version: "engine-v1",
    rubric_version: "rubric-v1",
    dashboard_path: `/prompt-checks/${"e".repeat(32)}`,
    other_metric_families_note: "Collaboration and outcome metrics require later session evidence.",
  };
}

const CODEX_UNSUPPORTED_METRICS = new Map<string, string>([
  ["collaboration.rework_candidate_rate", "feedback_text"],
  ["logic.hypothesis_test_linkage", "objective_verification"],
  ["logic.decision_rationale_coverage", "decision_evidence"],
  ["logic.requirement_action_traceability", "action_evidence"],
  ["outcome.agent_claim_grounding", "objective_verification"],
  ["outcome.first_pass_verification", "objective_verification"],
  ["outcome.verified_requirement_coverage", "objective_verification"],
]);

function codexReadinessFixture(): typeof SYNTHETIC_SESSION_METRIC_READINESS {
  const fixture = structuredClone(SYNTHETIC_SESSION_METRIC_READINESS);
  fixture.provider = "codex";
  fixture.capability_report.provider = "codex";
  fixture.capability_report.provider_version = "synthetic-codex-provider-1";
  fixture.capability_report.decoder_key = "codex.app-server.text-window";
  fixture.capability_report.structurally_attemptable_metric_count = 13;
  fixture.capability_report.structurally_unsupported_metric_count = 7;
  fixture.capability_report.capabilities = fixture.capability_report.capabilities.map(
    (capability) => ({
      ...capability,
      state: ["request_text", "response_text", "plan_text"].includes(capability.capability)
        ? "supported"
        : "unsupported",
      reason_code: ["request_text", "response_text", "plan_text"].includes(capability.capability)
        ? "verified_by_compatible_decoder"
        : "not_declared_by_decoder",
    }),
  );
  fixture.metrics = fixture.metrics.map((metric) => {
    const missing = CODEX_UNSUPPORTED_METRICS.get(metric.metric_key);
    if (missing === undefined) {
      return {
        ...metric,
        available_capabilities: metric.available_capabilities.filter((capability) =>
          ["request_text", "response_text", "plan_text"].includes(capability)
        ),
      };
    }
    const action = {
      action_evidence: "collect_action_evidence",
      decision_evidence: "collect_decision_evidence",
      feedback_text: "collect_feedback_evidence",
      objective_verification: "collect_objective_verification",
    }[missing];
    return {
      ...metric,
      state: "unsupported",
      reason_code: "provider_capability_missing",
      next_actions: [action],
      available_capabilities: metric.available_capabilities.filter((capability) =>
        ["request_text", "response_text", "plan_text"].includes(capability)
      ),
      missing_capabilities: [missing],
      latest_run_id: null,
    };
  });
  return fixture;
}

async function installLocalHttpFixture(page: Page): Promise<void> {
  const transport = createSyntheticTransport();
  const agentSessionId = "a".repeat(32);
  const initialAgentRevision = "b".repeat(64);
  const proposedAgentRevision = "c".repeat(64);
  const agentPreviewId = "d".repeat(32);
  let agentContent = "export const value = 1;\n";
  let agentRevision = initialAgentRevision;

  await page.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();

    if (!path.startsWith("/auth/") && path !== "/health" && !path.startsWith("/v1/")) {
      await route.continue();
      return;
    }

    if (path === "/health" && method === "GET") {
      await json(route, {
        status: "ok",
        cost_mode: "offline_only",
        data_tier: "metadata",
      });
      return;
    }
    if (path === "/auth/session" && method === "GET") {
      await json(route, {
        csrf_token: "synthetic-browser-csrf-token",
        expires_in_seconds: 300,
      });
      return;
    }
    if (path === "/v1/capabilities" && method === "GET") {
      await json(route, await transport.getSessionTextAnalysisCapability());
      return;
    }
    if (path === "/v1/research/text-analysis-methods" && method === "GET") {
      await json(route, await transport.getTextAnalysisResearch!());
      return;
    }
    if (path === "/v1/metric-contracts/v2/operability-catalog" && method === "GET") {
      await json(route, await transport.getMetricOperabilityCatalog!());
      return;
    }
    if (path === "/v1/local-sources/claude-code" && method === "GET") {
      await json(route, await transport.getClaudeLocalSourceStatus());
      return;
    }
    if (path === "/v1/local-sources/codex" && method === "GET") {
      await json(route, await transport.getCodexLocalSourceStatus());
      return;
    }
    if (path === "/v1/sessions" && method === "GET") {
      await json(
        route,
        await transport.listCodexSessions(
          integer(url.searchParams.get("limit"), 100),
          integer(url.searchParams.get("offset"), 0),
        ),
      );
      return;
    }
    if (path === "/v1/agent/sessions" && method === "GET") {
      await json(route, [{
        contract_version: "local-agent.v2",
        session_id: agentSessionId,
        settings: {
          workspace: "D:\\example\\workspace",
          model_alias: null,
          parameters: { temperature: 0.2, top_p: 0.95, max_tokens: 1400, enable_thinking: false },
          instructions: null,
          allow_writes: false,
          allow_commands: false,
          allow_web: false,
          max_steps: 10,
          command_timeout_seconds: 120,
          title: "Example workspace",
        },
        created_at: "2026-08-20T20:00:00Z",
        running: false,
        last_seq: 0,
        pending_approval_id: null,
        model_alias: null,
        turns: 0,
      }]);
      return;
    }
    if (path === "/v1/prompt-checks" && method === "POST") {
      await json(route, promptCheckFixture());
      return;
    }
    const agentTree = path.match(/^\/v1\/agent\/sessions\/([a-f0-9]{32})\/workspace\/tree$/);
    if (agentTree && method === "GET") {
      await json(route, {
        contract_version: "local-agent-workspace.v1",
        session_id: agentTree[1],
        path: url.searchParams.get("path") ?? ".",
        entries: [
          { path: "src", name: "src", kind: "directory", byte_size: null, editable_candidate: false },
          { path: "example.ts", name: "example.ts", kind: "file", byte_size: agentContent.length, editable_candidate: true },
        ],
        complete: true,
      });
      return;
    }
    const agentFile = path.match(/^\/v1\/agent\/sessions\/([a-f0-9]{32})\/workspace\/file$/);
    if (agentFile && method === "GET") {
      await json(route, {
        contract_version: "local-agent-workspace.v1",
        session_id: agentFile[1],
        path: url.searchParams.get("path"),
        content: agentContent,
        revision: agentRevision,
        byte_size: new TextEncoder().encode(agentContent).byteLength,
        line_ending: "lf",
        editable: true,
      });
      return;
    }
    const agentPreviews = path.match(/^\/v1\/agent\/sessions\/([a-f0-9]{32})\/workspace\/previews$/);
    if (agentPreviews && method === "POST") {
      const body = request.postDataJSON();
      await json(route, {
        contract_version: "local-agent-workspace.v1",
        session_id: agentPreviews[1],
        preview_id: agentPreviewId,
        path: body.path,
        expected_revision: body.expected_revision,
        proposed_revision: proposedAgentRevision,
        line_ending: body.line_ending,
        diff: "--- a/example.ts\n+++ b/example.ts\n@@ -1 +1 @@\n-export const value = 1;\n+export const value = 2;",
        expires_at: "2026-08-20T22:00:00Z",
      }, 201);
      return;
    }
    const agentApply = path.match(/^\/v1\/agent\/sessions\/([a-f0-9]{32})\/workspace\/previews\/([a-f0-9]{32})\/apply$/);
    if (agentApply && method === "POST") {
      const body = request.postDataJSON();
      agentContent = body.content;
      agentRevision = proposedAgentRevision;
      await json(route, {
        contract_version: "local-agent-workspace.v1",
        session_id: agentApply[1],
        path: body.path,
        revision: proposedAgentRevision,
        byte_size: new TextEncoder().encode(agentContent).byteLength,
        applied: true,
      });
      return;
    }
    const agentEvents = path.match(/^\/v1\/agent\/sessions\/([a-f0-9]{32})\/events\/stream$/);
    if (agentEvents && method === "GET") {
      await route.fulfill({
        body: `data: ${JSON.stringify({ contract_version: "local-agent.v2", session_id: agentEvents[1], events: [], running: false, pending_approval_id: null, last_seq: 0, first_seq: 0 })}\n\n`,
        headers: { "Cache-Control": "no-store, private", "Content-Type": "text/event-stream; charset=utf-8", Pragma: "no-cache" },
        status: 200,
      });
      return;
    }

    const projectSessions = path.match(/^\/v1\/projects\/([a-f0-9]{64})\/sessions$/);
    if (projectSessions && method === "GET") {
      const page = await transport.listProjectSessions(
        projectSessions[1],
        integer(url.searchParams.get("limit"), 100),
        integer(url.searchParams.get("offset"), 0),
      );
      await json(
        route,
        {
          ...page,
          sessions: page.sessions.map((session) => ({ ...session, provider: "codex" })),
        },
      );
      return;
    }

    const compatibility = path.match(/^\/v1\/providers\/([^/]+)\/compatibility$/);
    if (compatibility && method === "GET") {
      await json(route, await transport.getProviderCompatibility(compatibility[1] as "synthetic"));
      return;
    }
    const capabilities = path.match(/^\/v1\/providers\/([^/]+)\/capabilities$/);
    if (capabilities && method === "GET") {
      await json(route, await transport.getProviderMetricCapabilities(capabilities[1] as "synthetic"));
      return;
    }

    const readiness = path.match(/^\/v1\/sessions\/([a-f0-9]{64})\/metric-readiness$/);
    if (readiness && method === "GET") {
      await json(route, codexReadinessFixture());
      return;
    }
    const metrics = path.match(/^\/v1\/sessions\/([a-f0-9]{64})\/metrics$/);
    if (metrics && method === "GET") {
      await json(route, await transport.getSessionMetrics(metrics[1]));
      return;
    }
    const latestRun = path.match(
      /^\/v1\/sessions\/([a-f0-9]{64})\/quality-analysis-runs\/latest$/,
    );
    if (latestRun && method === "GET") {
      await json(route, await transport.getLatestSessionQualityAnalysis(latestRun[1]));
      return;
    }
    const run = path.match(/^\/v1\/quality-analysis\/runs\/([a-f0-9]{64})$/);
    if (run && method === "GET") {
      await json(route, await transport.getSessionQualityAnalysisRun(run[1]));
      return;
    }
    const coaching = path.match(
      /^\/v1\/quality-analysis\/runs\/([a-f0-9]{64})\/coaching-summary$/,
    );
    if (coaching && method === "GET") {
      await json(route, await transport.getSessionCoachingSummary(coaching[1]));
      return;
    }
    if (path === "/v1/quality-analysis/aggregate" && method === "POST") {
      await json(route, await transport.aggregateSessionQuality(request.postDataJSON()));
      return;
    }
    if (path === "/v1/quality-analysis/aggregate-projects" && method === "POST") {
      await json(route, await transport.aggregateProjectQuality(request.postDataJSON()));
      return;
    }
    if (path === "/v1/analysis-jobs" && method === "GET") {
      await json(route, {
        jobs: [],
        limit: integer(url.searchParams.get("limit"), 50),
        offset: integer(url.searchParams.get("offset"), 0),
      });
      return;
    }
    if (path === "/v1/automation-grants" && method === "GET") {
      await json(route, []);
      return;
    }
    if (path === "/v1/discovery/candidates" && method === "GET") {
      await json(route, await transport.listCandidates(
        (url.searchParams.get("status") ?? "all") as "all" | "undecided" | "decided",
        undefined,
        {
          limit: integer(url.searchParams.get("limit"), 100),
          offset: integer(url.searchParams.get("offset"), 0),
        },
      ));
      return;
    }
    if (path === "/v1/task-revisions" && method === "GET") {
      await json(route, await transport.listTaskRevisions(
        url.searchParams.get("task_id") ?? undefined,
        undefined,
        {
          limit: integer(url.searchParams.get("limit"), 100),
          offset: integer(url.searchParams.get("offset"), 0),
        },
      ));
      return;
    }
    if (path === "/v1/task-lifecycles" && method === "GET") {
      await json(route, {
        lifecycles: [],
        limit: integer(url.searchParams.get("limit"), 100),
        offset: integer(url.searchParams.get("offset"), 0),
      });
      return;
    }
    if (path === "/v1/analysis/runs" && method === "GET") {
      await json(route, await transport.listAnalysisRuns(
        url.searchParams.get("task_id") ?? undefined,
        undefined,
        {
          limit: integer(url.searchParams.get("limit"), 100),
          offset: integer(url.searchParams.get("offset"), 0),
        },
      ));
      return;
    }
    const decisions = path.match(/^\/v1\/discovery\/candidates\/([a-f0-9]{64})\/decisions$/);
    if (decisions && method === "GET") {
      await json(route, await transport.getCandidateDecisions(decisions[1]));
      return;
    }

    await json(
      route,
      { detail: { code: "synthetic_fixture_route_missing" } },
      501,
    );
  });
}

test.beforeEach(async ({ page }) => {
  await installLocalHttpFixture(page);
});

test("edits an existing workspace file beside the agent through a reviewed local diff", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 920 });
  await page.goto("/agent");

  await expect(page.getByRole("heading", { name: "Example workspace" })).toBeVisible();
  const workspace = page.getByRole("region", { name: "Files and reviewed changes" });
  const conversation = page.getByRole("region", { name: "Agent conversation" });
  await expect(workspace).toContainText("manual edits use browser confirmation");
  await page.getByRole("button", { name: /example\.ts/u }).click();
  const editor = page.getByRole("textbox", { name: "Workspace file editor" });
  await expect(editor).toHaveValue("export const value = 1;\n");
  await editor.fill("export const value = 2;\n");
  await page.getByRole("button", { name: "Review diff" }).click();
  await expect(page.getByRole("region", { name: "Manual edit review" })).toContainText("+export const value = 2;");
  await page.getByRole("button", { name: "Apply reviewed edit" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Applied the reviewed edit" })).toBeVisible();
  await expect(editor).toHaveValue("export const value = 2;\n");

  const [workspaceBox, conversationBox] = await Promise.all([workspace.boundingBox(), conversation.boundingBox()]);
  expect(workspaceBox).not.toBeNull();
  expect(conversationBox).not.toBeNull();
  expect(workspaceBox!.x).toBeLessThan(conversationBox!.x);

  await page.setViewportSize({ width: 420, height: 820 });
  const dimensions = await page.evaluate(() => ({
    document: document.documentElement.scrollWidth,
    viewport: document.documentElement.clientWidth,
  }));
  expect(dimensions.document).toBeLessThanOrEqual(dimensions.viewport);
  await expect(editor).toBeVisible();
});

test("checks and improves an agent draft through the local Prompt Check endpoint without sending it", async ({ page }) => {
  await page.setViewportSize({ width: 420, height: 820 });
  await page.goto("/agent");

  const draft = page.getByRole("textbox", { name: "Message to the agent" });
  await draft.fill("Update example.ts");
  await page.getByRole("button", { name: "Check & improve" }).click();

  await expect(page.getByRole("heading", { name: "Before the agent acts" })).toBeVisible();
  await expect(page.getByText("a checkable pass condition")).toBeVisible();
  await expect(page.getByText(/Name the focused test command/)).toBeVisible();
  await expect(page.getByText(/model output, not measured evidence/)).toBeVisible();

  await page.getByRole("button", { name: "Use suggested prompt" }).click();
  await expect(draft).toHaveValue("Update example.ts, run the focused test, and report the changed files and result.");
  await expect(page.getByRole("heading", { name: "Before the agent acts" })).toHaveCount(0);
  await expect(page.getByText(/Check it again to validate/)).toBeVisible();
  await expect(page.getByText("Update example.ts", { exact: true })).toHaveCount(0);

  const dimensions = await page.evaluate(() => ({
    document: document.documentElement.scrollWidth,
    viewport: document.documentElement.clientWidth,
  }));
  expect(dimensions.document).toBeLessThanOrEqual(dimensions.viewport);
});

test("keeps the canonical metric workspace truthful when the bounded source is unavailable", async ({ page }) => {
  await page.goto(
    `/projects/${SYNTHETIC_QUALITY_PROJECT_ID}/sessions/${SYNTHETIC_QUALITY_SESSION_ID}/metrics/prompt-quality`,
  );

  await expect(
    page.getByLabel("Runtime status: Local loopback service available"),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", {
      name: "Measure the analyzed window, then estimate every eligible axis locally",
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("status").filter({
      hasText: "This installation cannot read the selected session through the bounded adapter.",
    }),
  ).toBeVisible();
  await expect(page.getByRole("img", { name: /metric radar/i })).toHaveCount(0);
  await expect(page.getByText(SYNTHETIC_CURRENT_SESSION_QUALITY_RUN.run.run_id)).toHaveCount(0);
});

test("keeps local job state truthful and responsive", async ({ page }) => {
  await page.setViewportSize({ width: 600, height: 820 });
  await page.goto("/analysis-jobs");

  await expect(page.getByRole("heading", { name: "Analysis Job Centre" })).toBeVisible();
  await expect(
    page.getByText("No durable jobs match this filter. Missing jobs are not treated as completed work."),
  ).toBeVisible();
  await expect(page.getByText(/Local real .* SQLite queue .* one local worker/)).toBeVisible();

  const dimensions = await page.evaluate(() => ({
    document: document.documentElement.scrollWidth,
    viewport: document.documentElement.clientWidth,
  }));
  expect(dimensions.document).toBeLessThanOrEqual(dimensions.viewport);
});

test("fails the social hub closed with exact zero local-real state", async ({ page }) => {
  await page.setViewportSize({ width: 600, height: 820 });
  await page.goto("/social");

  await expect(page.getByRole("heading", { name: "Social hub" })).toBeVisible();
  await expect(page.getByRole("status").filter({ hasText: "Social features are not served in this runtime" })).toContainText(
    "0 friends · 0 relationships · 0 requests · 0 conversations · 0 messages · 0 file offers · presence not shared",
  );
  await expect(page.getByRole("note", { name: "Fictional synthetic demo" })).toHaveCount(0);
  await expect(page.getByRole("form", { name: /Message|Offer a file/ })).toHaveCount(0);
  await expect(page.locator("input[type='file']")).toHaveCount(0);
});

test("keeps local task records local-only without inferring work lifecycle", async ({ page }) => {
  await page.setViewportSize({ width: 620, height: 900 });
  await page.goto("/tasks/flow");

  await expect(page.getByRole("heading", { name: "Task flow" })).toBeVisible();
  const summary = page.getByRole("region", { name: "Task flow compact summary" });
  await expect(summary.getByText("Work state Unknown", { exact: true }).locator(".."))
    .toContainText("0");
  await expect(summary.getByText("Backlog", { exact: true }).locator(".."))
    .toContainText("0");
  await expect(summary.getByText("In progress", { exact: true }).locator(".."))
    .toContainText("0");
  await expect(summary.getByText("Done", { exact: true }).locator(".."))
    .toContainText("0");
  await expect(summary.getByText("Historical / unreconciled", { exact: true }).locator(".."))
    .toContainText("0 / 1");
  await expect(summary).toContainText("0 team-sourced records · 0 remote-synced records");
  await expect(page.getByText("Local · this installation only")).toBeVisible();
  await expect(page.getByRole("note", { name: "Fictional synthetic demo" })).toHaveCount(0);
  const unreconciled = page.getByRole("region", { name: "State not reconciled" });
  await expect(unreconciled).toContainText("No backlog, in-progress, or done state is fabricated");
  await expect(unreconciled.getByText("Unknown", { exact: true })).toHaveCount(2);
});

test("renders the server-bound all-twenty operability gate without a session read", async ({ page }) => {
  await page.setViewportSize({ width: 600, height: 900 });
  await page.goto("/research/methods");

  await expect(page.getByLabel("Runtime status: Local loopback service available")).toHaveAttribute(
    "data-service-state",
    "available",
  );
  await expect(page.getByRole("heading", {
    name: "What can produce measured evidence today",
  })).toBeVisible();
  const summary = page.getByLabel("Metric operability summary");
  await expect(summary.getByText("Measured paths shipped").locator("..")).toContainText("12");
  await expect(summary.getByText("Need project profile").locator("..")).toContainText("3");
  await expect(summary.getByText("Need source adapter").locator("..")).toContainText("5");
  await expect(summary.getByText("Model-authored metrics").locator("..")).toContainText("0");
  await expect(page.locator("[data-operability-state]")).toHaveCount(20);
});

test("requires an exact local project grant before background scheduling", async ({ page }) => {
  await page.setViewportSize({ width: 600, height: 900 });
  await page.goto(`/projects/${SYNTHETIC_QUALITY_PROJECT_ID}/automation`);

  await expect(page.getByRole("heading", { name: "Project automation" })).toBeVisible();
  await expect(page.getByText("Remote execution is never unattended")).toBeVisible();
  await expect(page.getByText("Consent active", { exact: true })).toBeVisible();
  await expect(page.getByText("Project indexed", { exact: true })).toBeVisible();
  await expect(page.getByText("Readiness verified", { exact: true })).toBeVisible();
  await expect(page.getByText("No grant exists for this project")).toBeVisible();

  const create = page.getByRole("button", { name: "Create 30-day local grant" });
  await expect(create).toBeDisabled();
  await page.getByRole("button", { name: "Select attemptable" }).click();
  await page.getByRole("checkbox", {
    name: /I authorize this local service to schedule selected metrics/,
  }).check();
  await expect(create).toBeEnabled();
  await expect(page.getByText("Every 15 minutes while the service runs")).toBeVisible();
  await expect(page.getByText("30 days, then renew explicitly")).toBeVisible();

  const dimensions = await page.evaluate(() => ({
    document: document.documentElement.scrollWidth,
    viewport: document.documentElement.clientWidth,
  }));
  expect(dimensions.document).toBeLessThanOrEqual(dimensions.viewport);
});
