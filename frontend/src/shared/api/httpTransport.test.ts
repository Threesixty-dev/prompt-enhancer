import { describe, expect, it, vi } from "vitest";
import type {
  AnalysisJobState,
  AutomationGrantRecord,
  AutomationGrantScope,
  ModelCompatibilityCatalog,
  ModelRuntimeInventory,
  SessionQualityAnalysisPreview,
  SessionQualityAnalysisRequest,
} from "./contracts";
import {
  assertSameOriginRelativePath,
  createHttpTransport,
  parseAnalysisJobPage,
  parseAnalysisJobRecord,
  parseAutomationGrantList,
  parseAutomationGrantRecord,
  parseAutomationPollResult,
  parseMetricCoverageReport,
  parseProviderCapabilityReport,
  parseProviderCompatibilityStatus,
  parseRuntimeHealth,
  parseSessionAnalysisRunResponse,
  parseSessionMetricReadinessReport,
  parseSessionQualityAnalysisPreview,
  parseSessionTextAnalysisCapability,
  TransportError,
} from "./httpTransport";
import {
  SYNTHETIC_MODEL_LINK_EXPERIMENT,
  SYNTHETIC_MODEL_LINK_OUTCOME,
  SYNTHETIC_METRIC_COVERAGE,
  SYNTHETIC_PROVIDER_METRIC_CAPABILITIES,
  SYNTHETIC_SESSION_METRIC_READINESS,
  SYNTHETIC_SESSION_QUALITY_RUN,
} from "./syntheticFixtures";
import { SYNTHETIC_TEXT_ANALYSIS_RESEARCH } from "./syntheticResearchFixture";
import { createSyntheticTransport } from "./syntheticTransport";
import {
  deriveModelCompatibilityDisposition,
  FROZEN_MODEL_COMPATIBILITY_CONFIGURATIONS,
  ModelCompatibilityPayloadError,
  parseModelCompatibilityCatalog,
} from "./modelCompatibilityContract";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function privateJsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": "no-store, private",
      Pragma: "no-cache",
    },
  });
}

const AUTH_RESPONSE = { csrf_token: "synthetic-csrf-token", expires_in_seconds: 300 };
const CONTROL_PLANE_READINESS_RESPONSE = {
  contract_version: "control-plane-v2",
  delivery_guarantee: "at_least_once_with_monotonic_ack",
  gaps: [
    "backup_and_replica_erasure_not_implemented",
    "billing_not_implemented",
    "credential_lifecycle_incomplete",
    "disclosure_control_unreviewed",
    "durable_recipient_delivery_not_implemented",
    "governance_review_pending",
    "out_of_band_provisioning_only",
    "producer_pipeline_not_connected",
    "production_database_adapter_missing",
    "production_identity_provider_missing",
    "production_signature_algorithm_missing",
    "remote_transport_not_implemented",
  ],
  production_ready: false,
  profile: "development",
  remote_listening_enabled: false,
} as const;
const CONTENT_FREE_ANALYSIS_REQUEST: SessionQualityAnalysisRequest = {
  confirmation: "analyze_selected_redacted_text",
  preset_id: "coaching_profile_v1",
};

function qualityRunResponse() {
  return structuredClone(SYNTHETIC_SESSION_QUALITY_RUN);
}

function redactionPreview(
  sessionId = "5".repeat(64),
): SessionQualityAnalysisPreview {
  const text = "Synthetic redacted request for transport validation.";
  return {
    preview_id: "e".repeat(64),
    created_at: "2040-01-01T10:00:00Z",
    expires_at: "2040-01-01T10:10:00Z",
    binding: {
      provider: "codex",
      session_id: sessionId,
      analysis_window_fingerprint: "a".repeat(64),
      metric_keys: SYNTHETIC_SESSION_METRIC_READINESS.metrics.map(
        (metric) => metric.metric_key,
      ),
      destination: "local",
      exact_model: "none",
      estimator_plan_version: "example-plan-1",
      redactor_version: "example-redactor-1",
      retention_class: "local_ephemeral",
      message_count: 1,
      character_count: Array.from(text).length,
      cost_state: "not_applicable",
      estimated_cost_microunits: null,
      cost_currency: null,
    },
    messages: [{ role: "user", kind: "request", language: "en", text }],
  };
}

function analysisJobPayload(
  state: AnalysisJobState = "queued",
  overrides: Record<string, unknown> = {},
) {
  const terminal = ["completed", "partial", "failed", "cancelled", "superseded"]
    .includes(state);
  return {
    job_id: "1".repeat(64),
    identity: {
      kind: "session_quality",
      provider: "codex",
      project_id: "3".repeat(64),
      session_id: "4".repeat(64),
      input_fingerprint: "5".repeat(64),
      provenance_fingerprint: "6".repeat(64),
      metric_keys: ["logic.decomposition_coverage", "prompt.goal_definition"],
      estimator_plan_version: "example-plan-1",
      redactor_version: "example-redactor-1",
      provider_schema_version: "example-schema-1",
      automation_grant_id: null,
      local_only: true,
    },
    state,
    stage_number: state === "stage_n" ? 2 : null,
    progress_completed: state === "completed" ? 2 : 1,
    progress_total: 2,
    attempt_count: state === "preprocessing" || state === "stage_n" ? 1 : 0,
    max_attempts: 3,
    available_at: "2040-01-01T10:00:00Z",
    cancel_requested: false,
    last_error_code: null,
    terminal_reason_code: terminal ? state : null,
    created_at: "2040-01-01T09:00:00Z",
    updated_at: "2040-01-01T10:00:00Z",
    terminal_at: terminal ? "2040-01-01T10:00:00Z" : null,
    ...overrides,
  };
}

function automationScope(
  overrides: Partial<AutomationGrantScope> = {},
): AutomationGrantScope {
  return {
    provider: "codex",
    project_id: "3".repeat(64),
    metric_keys: ["logic.decomposition_coverage", "prompt.context_sufficiency"],
    newest_session_limit: 20,
    check_interval_seconds: 900,
    resource_policy: {
      route: "balanced",
      max_gpu_workers: 1,
      max_cpu_workers: 1,
      pause_on_battery: true,
      maximum_session_seconds: 1_800,
    },
    local_only: true,
    remote_requires_fresh_approval: true,
    ...overrides,
  };
}

function automationGrantPayload(
  state: AutomationGrantRecord["state"] = "active",
  overrides: Record<string, unknown> = {},
) {
  return {
    grant_id: "9".repeat(64),
    revision: 1,
    scope: automationScope(),
    state,
    created_at: "2040-01-01T09:00:00Z",
    renewed_at: "2040-01-01T09:00:00Z",
    expires_at: "2040-01-31T09:00:00Z",
    next_check_at: "2040-01-01T09:15:00Z",
    last_checked_at: null,
    revoked_at: state === "revoked" ? "2040-01-02T09:00:00Z" : null,
    last_error_code: null,
    ...overrides,
  };
}
const PROVIDER_COMPATIBILITY = {
  provider: "codex",
  capability: "session_text_analysis",
  state: "exact",
  capability_state: "supported",
  provider_family: "codex_app_server",
  provider_version: "1.2.3",
  adapter_family: "codex_app_server",
  adapter_version: "2.0.0",
  source_schema_family: "codex_thread",
  source_schema_version: "1",
  content_schema_family: "codex_thread_items",
  content_schema_version: "1",
  reason_code: "exact_match",
  checked_at: "2040-01-01T10:00:00Z",
  update_support: "unsupported",
  update_target: null,
} as const;

describe("same-origin HTTP transport", () => {
  it("strictly accepts canonical exact and legacy-unknown quality run scopes", () => {
    const exact = qualityRunResponse();
    expect(parseSessionAnalysisRunResponse(exact, {
      sessionId: exact.run.session_id,
      runId: exact.run.run_id,
    })).toEqual(exact);

    const legacy = qualityRunResponse();
    legacy.run.metric_scope_state = "legacy_unknown";
    legacy.run.selected_metric_keys = [];
    legacy.results = [];
    expect(parseSessionAnalysisRunResponse(legacy)).toEqual(legacy);

    const legacyMultiVersion = qualityRunResponse();
    legacyMultiVersion.run.metric_scope_state = "legacy_unknown";
    legacyMultiVersion.run.selected_metric_keys = [];
    legacyMultiVersion.results = [
      legacyMultiVersion.results[0],
      { ...legacyMultiVersion.results[0], version: 2 },
    ];
    expect(parseSessionAnalysisRunResponse(legacyMultiVersion)).toEqual(
      legacyMultiVersion,
    );
  });

  it("rejects unbound or noncanonical quality run scope responses", () => {
    const malformed: unknown[] = [
      (() => {
        const value = qualityRunResponse() as unknown as { run: Record<string, unknown> };
        delete value.run.metric_scope_state;
        return value;
      })(),
      (() => {
        const value = qualityRunResponse();
        value.run.selected_metric_keys = [...value.run.selected_metric_keys].reverse();
        return value;
      })(),
      (() => {
        const value = qualityRunResponse();
        value.run.selected_metric_keys = [
          value.run.selected_metric_keys[0],
          value.run.selected_metric_keys[0],
        ];
        return value;
      })(),
      (() => {
        const value = qualityRunResponse();
        value.run.selected_metric_keys = Array.from(
          { length: 101 },
          (_, index) => `metric.synthetic_${index.toString().padStart(3, "0")}`,
        );
        return value;
      })(),
      (() => {
        const value = qualityRunResponse();
        value.run.selected_metric_keys = ["private metric key"];
        return value;
      })(),
      (() => {
        const value = qualityRunResponse();
        value.results.pop();
        return value;
      })(),
      (() => {
        const value = qualityRunResponse();
        value.run.metric_scope_state = "legacy_unknown";
        value.run.selected_metric_keys = [];
        value.results = [value.results[0], structuredClone(value.results[0])];
        return value;
      })(),
      (() => {
        const value = qualityRunResponse();
        value.run.metric_scope_state = "legacy_unknown";
        return value;
      })(),
    ];

    malformed.forEach((value) => {
      expect(() => parseSessionAnalysisRunResponse(value)).toThrow(
        new TransportError("Quality analysis response was invalid", 200),
      );
    });
    const exact = qualityRunResponse();
    expect(() => parseSessionAnalysisRunResponse(exact, {
      sessionId: "f".repeat(64),
    })).toThrow(new TransportError("Quality analysis response was invalid", 200));
    expect(() => parseSessionAnalysisRunResponse(exact, {
      runId: "e".repeat(64),
    })).toThrow(new TransportError("Quality analysis response was invalid", 200));
  });

  it("checks the actual minimal health route without bootstrapping a session", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(
      jsonResponse({
        status: "ok",
        cost_mode: "offline_only",
        data_tier: "metadata",
      }),
    );
    const transport = createHttpTransport({
      fetch: fetchMock as unknown as typeof fetch,
      origin: "http://127.0.0.1:4173",
    });

    await expect(transport.getRuntimeHealth()).resolves.toEqual({
      status: "ok",
      costMode: "offline_only",
      dataTier: "metadata",
    });
    expect(transport.runtimeKind).toBe("local_loopback");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith(
      "/health",
      expect.objectContaining({
        method: "GET",
        credentials: "include",
        redirect: "error",
        referrerPolicy: "no-referrer",
        headers: { Accept: "application/json" },
      }),
    );
  });

  it("rejects non-minimal or non-local runtime health payloads", () => {
    expect(() =>
      parseRuntimeHealth({
        status: "ok",
        cost_mode: "offline_only",
        data_tier: "metadata",
        remote_approved: true,
      }),
    ).toThrow(/health response was invalid/i);
    expect(() =>
      parseRuntimeHealth({
        status: "ok",
        cost_mode: "metered",
        data_tier: "remote_redacted",
      }),
    ).toThrow(/health response was invalid/i);
  });

  it("fails the health check on an HTTP or content-type error", async () => {
    const unavailable = createHttpTransport({
      fetch: vi.fn().mockResolvedValueOnce(jsonResponse({}, 503)) as unknown as typeof fetch,
      origin: "http://127.0.0.1:4173",
    });
    const wrongType = createHttpTransport({
      fetch: vi.fn().mockResolvedValueOnce(
        new Response("ok", {
          status: 200,
          headers: { "Content-Type": "text/plain" },
        }),
      ) as unknown as typeof fetch,
      origin: "http://127.0.0.1:4173",
    });

    await expect(unavailable.getRuntimeHealth()).rejects.toMatchObject({
      status: 503,
    });
    await expect(wrongType.getRuntimeHealth()).rejects.toMatchObject({
      status: 200,
    });
  });

  it("runs, reads, and annotates the selected-session model experiment through exact local routes", async () => {
    const annotation = {
      link_id: "b".repeat(64),
      revision: 1,
      label: "relevant",
      annotated_at: "2040-01-03T09:02:00Z",
    } as const;
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(AUTH_RESPONSE))
      .mockResolvedValueOnce(jsonResponse(SYNTHETIC_MODEL_LINK_OUTCOME))
      .mockResolvedValueOnce(jsonResponse(SYNTHETIC_MODEL_LINK_EXPERIMENT))
      .mockResolvedValueOnce(jsonResponse(annotation));
    const transport = createHttpTransport({
      fetch: fetchMock as unknown as typeof fetch,
      origin: "http://127.0.0.1:4173",
    });
    const sessionId = "5".repeat(64);
    const runId = "a".repeat(64);
    const linkId = "b".repeat(64);

    await transport.startModelLinkExperiment(
      sessionId,
      {
        confirmation: "compare_selected_redacted_text_with_local_models",
        device: "auto",
      },
      "dashboard-model-link-experiment-example",
    );
    await transport.getLatestModelLinkExperiment(sessionId);
    await transport.annotateModelLink(runId, linkId, {
      label: "relevant",
      expected_revision: 0,
    });

    expect(fetchMock.mock.calls[1][0]).toBe(
      `/v1/sessions/${sessionId}/model-link-experiments`,
    );
    expect(fetchMock.mock.calls[1][1]).toEqual(
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          confirmation: "compare_selected_redacted_text_with_local_models",
          device: "auto",
        }),
        headers: expect.objectContaining({
          "Idempotency-Key": "dashboard-model-link-experiment-example",
          "X-Prompt-Enhancer-CSRF": AUTH_RESPONSE.csrf_token,
        }),
      }),
    );
    expect(fetchMock.mock.calls[2][0]).toBe(
      `/v1/sessions/${sessionId}/model-link-experiments/latest`,
    );
    expect(fetchMock.mock.calls[3][0]).toBe(
      `/v1/model-link-experiments/${runId}/links/${linkId}/annotations`,
    );
  });

  it("projects only allowlisted model-experiment failure codes", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(AUTH_RESPONSE))
      .mockResolvedValueOnce(
        jsonResponse(
          {
            detail: {
              code: "local_model_execution_failed",
              message: "SYNTHETIC_PRIVATE_CANARY",
            },
          },
          503,
        ),
      );
    const transport = createHttpTransport({
      fetch: fetchMock as unknown as typeof fetch,
      origin: "http://127.0.0.1:4173",
    });

    const error = await transport
      .startModelLinkExperiment(
        "5".repeat(64),
        {
          confirmation: "compare_selected_redacted_text_with_local_models",
          device: "auto",
        },
        "dashboard-model-link-experiment-example",
      )
      .catch((value: unknown) => value);

    expect(error).toMatchObject({
      status: 503,
      reasonCode: "local_model_execution_failed",
    });
    expect(String(error)).not.toContain("SYNTHETIC_PRIVATE_CANARY");
  });

  it("reads the content-free research catalog without a mutation", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(AUTH_RESPONSE))
      .mockResolvedValueOnce(jsonResponse(SYNTHETIC_TEXT_ANALYSIS_RESEARCH));
    const transport = createHttpTransport({
      fetch: fetchMock as unknown as typeof fetch,
      origin: "http://127.0.0.1:4173",
    });

    await expect(transport.getTextAnalysisResearch?.()).resolves.toEqual(
      SYNTHETIC_TEXT_ANALYSIS_RESEARCH,
    );
    expect(fetchMock.mock.calls[1][0]).toBe("/v1/research/text-analysis-methods");
    expect(fetchMock.mock.calls[1][1]).toEqual(
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("validates and reads the private model compatibility catalog with GET", async () => {
    const payload = await createSyntheticTransport().getTextModelCompatibility!();
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(AUTH_RESPONSE))
      .mockResolvedValueOnce(privateJsonResponse(payload));
    const transport = createHttpTransport({
      fetch: fetchMock as unknown as typeof fetch,
      origin: "http://127.0.0.1:4173",
    });

    await expect(transport.getTextModelCompatibility?.()).resolves.toEqual(payload);
    expect(payload.models.map((entry) => entry.configuration_key)).toEqual(
      FROZEN_MODEL_COMPATIBILITY_CONFIGURATIONS.map(
        (entry) => entry.configuration_key,
      ),
    );
    expect(Object.isFrozen(FROZEN_MODEL_COMPATIBILITY_CONFIGURATIONS)).toBe(true);
    expect(
      FROZEN_MODEL_COMPATIBILITY_CONFIGURATIONS.every(Object.isFrozen),
    ).toBe(true);
    expect(fetchMock.mock.calls[1][0]).toBe("/v1/research/text-model-compatibility");
    expect(fetchMock.mock.calls[1][1]).toEqual(expect.objectContaining({ method: "GET" }));
    expect(fetchMock.mock.calls[1][1]?.headers).not.toEqual(
      expect.objectContaining({ "X-Prompt-Enhancer-CSRF": expect.anything() }),
    );
  });

  it("fails closed on extra fields and contradictory compatibility inventory", async () => {
    const payload = await createSyntheticTransport().getTextModelCompatibility!();
    const extraField = {
      ...payload,
      inventory: {
        ...payload.inventory,
        hostname: "SYNTHETIC_PRIVATE_CANARY",
      },
    };
    const contradictory = {
      ...payload,
      inventory: {
        ...payload.inventory,
        preferred_device: "cpu",
        cuda_state: "unknown",
        cuda_available: false,
        cuda_vram_bucket: null,
        cuda_capability_bucket: null,
        discovery_reason_codes: ["cuda_inventory_unknown"],
      },
    };
    const falsifiedNf4Provenance = {
      ...payload,
      models: payload.models.map((entry) =>
        entry.quantization === "bitsandbytes_nf4"
          ? {
              ...entry,
              measurement_method: "not_measured",
              measurement_precision: "not_measured",
              observed_peak_gpu_allocation_mib: null,
              resource_measurement_state: "missing",
            }
          : entry,
      ),
    };

    for (const invalidPayload of [extraField, contradictory, falsifiedNf4Provenance]) {
      const fetchMock = vi.fn()
        .mockResolvedValueOnce(jsonResponse(AUTH_RESPONSE))
        .mockResolvedValueOnce(privateJsonResponse(invalidPayload));
      const transport = createHttpTransport({
        fetch: fetchMock as unknown as typeof fetch,
        origin: "http://127.0.0.1:4173",
      });
      const error = await transport.getTextModelCompatibility?.().catch((value: unknown) => value);

      expect(error).toBeInstanceOf(TransportError);
      expect(error).toMatchObject({ status: 200 });
      expect(String(error)).toBe("TransportError: Model compatibility response was invalid");
      expect(String(error)).not.toContain("SYNTHETIC_PRIVATE_CANARY");
    }
  });

  it("rejects every omission, swap, and immutable compatibility provenance change", async () => {
    const payload = await createSyntheticTransport().getTextModelCompatibility!();
    const fullPrecisionKey = "qwen3_4b_rubric_full_precision_cuda_screen_v1";
    const measuredSmallKey = "mdeberta_xnli_unquantized_cuda_screen_v1";

    const patchEntry = (
      key: string,
      patch: Record<string, unknown>,
    ): ModelCompatibilityCatalog => {
      const changed = structuredClone(payload);
      const index = changed.models.findIndex(
        (entry) => entry.configuration_key === key,
      );
      expect(index).toBeGreaterThanOrEqual(0);
      changed.models[index] = {
        ...changed.models[index],
        ...patch,
      } as typeof changed.models[number];
      return changed;
    };

    const omitted = structuredClone(payload);
    omitted.models.splice(3, 1);
    const duplicated = structuredClone(payload);
    duplicated.models[3] = structuredClone(duplicated.models[2]);
    const swapped = structuredClone(payload);
    [swapped.models[2], swapped.models[3]] = [
      swapped.models[3],
      swapped.models[2],
    ];

    const attacks: Array<[string, unknown]> = [
      ["omitted configuration", omitted],
      ["duplicate configuration", duplicated],
      ["reordered configurations", swapped],
      ["configuration identity", patchEntry(fullPrecisionKey, { configuration_key: "forged_configuration_v1" })],
      ["private extra field", patchEntry(fullPrecisionKey, { raw_model_path: "SYNTHETIC_PRIVATE_CANARY" })],
      ["model identity", patchEntry(fullPrecisionKey, { model_key: "forged_model" })],
      ["repository identity", patchEntry(fullPrecisionKey, { repository_id: "ExampleOrg/forged-model" })],
      ["revision", patchEntry(fullPrecisionKey, { revision: "b".repeat(40) })],
      ["task", patchEntry(fullPrecisionKey, { task: "requirement_action_retrieval" })],
      ["role", patchEntry(fullPrecisionKey, { role: "retrieval" })],
      ["language scope", patchEntry(fullPrecisionKey, { language_scope: "english" })],
      ["license", patchEntry(fullPrecisionKey, { license_spdx: "MIT" })],
      ["quantization", patchEntry(fullPrecisionKey, { quantization: "bitsandbytes_nf4" })],
      ["dtype", patchEntry(fullPrecisionKey, { dtype: "float32" })],
      ["runtime", patchEntry(fullPrecisionKey, { runtime: "forged_runtime" })],
      ["measurement source", patchEntry(fullPrecisionKey, { measurement_source: "forged_source" })],
      ["GPU measurement", patchEntry(measuredSmallKey, { observed_peak_gpu_allocation_mib: 1_121.561 })],
      ["benchmark identity", patchEntry(measuredSmallKey, { benchmark_key: "forged_benchmark" })],
      ["case count", patchEntry(measuredSmallKey, { synthetic_case_count: 19 })],
      ["trust boundary", patchEntry(fullPrecisionKey, { trust_remote_code: true })],
      ["product activation", patchEntry(fullPrecisionKey, { product_enabled: true })],
      ["activation permission", patchEntry(fullPrecisionKey, { activation_allowed: true })],
      ["download permission", patchEntry(fullPrecisionKey, { download_allowed: true })],
      ["status", patchEntry(measuredSmallKey, { status: "unavailable" })],
      ["reason", patchEntry(measuredSmallKey, { reason_codes: ["cuda_unavailable"] })],
      [
        "coherent but forged missing measurement",
        patchEntry(measuredSmallKey, {
          measurement_method: "not_measured",
          measurement_precision: "not_measured",
          resource_measurement_state: "missing",
          observed_peak_gpu_allocation_mib: null,
          benchmark_key: null,
          synthetic_case_count: null,
        }),
      ],
      [
        "coherent but forged complete measurement",
        patchEntry(measuredSmallKey, {
          resource_measurement_state: "complete",
          observed_peak_child_rss_mib: 512,
          status: "research_only",
          reason_codes: ["exploratory_resource_fit"],
        }),
      ],
    ];

    for (const [name, attack] of attacks) {
      expect(
        () => parseModelCompatibilityCatalog(attack),
        name,
      ).toThrow(ModelCompatibilityPayloadError);
    }
  });

  it("accepts status changes only when they are exactly derived from coherent inventory", async () => {
    const base = await createSyntheticTransport().getTextModelCompatibility!();
    const inventoryCases: Array<Partial<ModelRuntimeInventory>> = [
      {
        preferred_device: "cpu",
        cuda_state: "unknown",
        cuda_available: null,
        mps_available: false,
        cuda_vram_bucket: null,
        cuda_capability_bucket: null,
        discovery_reason_codes: ["cuda_inventory_unknown"],
      },
      {
        preferred_device: "cpu",
        cuda_state: "unavailable",
        cuda_available: false,
        mps_available: false,
        cuda_vram_bucket: null,
        cuda_capability_bucket: null,
        discovery_reason_codes: [],
      },
      { system_ram_bucket: "below_16_gib_class" },
      { cuda_vram_bucket: "below_8_gib_class" },
    ];

    for (const patch of inventoryCases) {
      const inventory = {
        ...base.inventory,
        ...patch,
      } satisfies ModelRuntimeInventory;
      const payload = {
        ...base,
        inventory,
        models: FROZEN_MODEL_COMPATIBILITY_CONFIGURATIONS.map(
          (configuration) => ({
            ...configuration,
            ...deriveModelCompatibilityDisposition(inventory, configuration),
          }),
        ),
      } satisfies ModelCompatibilityCatalog;

      expect(parseModelCompatibilityCatalog(payload)).toEqual(payload);
    }
  });

  it("starts only an explicit local synthetic model job with CSRF", async () => {
    const runtime = {
      preferred_device: "cuda",
      cuda_state: "available",
      cuda_available: true,
      mps_available: false,
      cpu_available: true,
      cpu_architecture_bucket: "x86_64",
      logical_core_bucket: "9_to_16",
      system_ram_bucket: "16_gib_class",
      cuda_vram_bucket: "16_gib_class",
      cuda_capability_bucket: "8_x",
      model_cache_free_disk_bucket: "10240_to_51199_mib",
      discovery_reason_codes: [],
      inventory_version: "bucketed-sensitive-hardware-inventory-v3",
      one_model_at_a_time: true,
      subprocess_isolation: true,
      raw_session_data_accepted: false,
      model_child_gpu_allocation_ceiling_mib: 6144,
      model_child_rss_ceiling_mib: 8192,
      model_downloads_started: false,
      model_activation_allowed: false,
      sensitivity: "sensitive_derived",
      local_only: true,
      persisted: false,
      synced: false,
    } as const;
    const job = {
      job_id: "a".repeat(32),
      status: "queued",
      candidate: {
        candidate: "all",
        device: "auto",
        mode: "full",
        allow_download: false,
      },
      created_at: "2040-01-01T00:00:00Z",
      started_at: null,
      completed_at: null,
      resolved_device: null,
      error_code: null,
      outcomes: [],
    } as const;
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(AUTH_RESPONSE))
      .mockResolvedValueOnce(jsonResponse(runtime))
      .mockResolvedValueOnce(jsonResponse(job, 202));
    const transport = createHttpTransport({
      fetch: fetchMock as unknown as typeof fetch,
      origin: "http://127.0.0.1:4173",
    });

    await expect(transport.getTextModelRuntime?.()).resolves.toEqual(runtime);
    await expect(transport.startTextModelEvaluation?.(job.candidate)).resolves.toEqual(job);
    expect(fetchMock.mock.calls[2][0]).toBe("/v1/research/text-model-evaluations");
    expect(fetchMock.mock.calls[2][1]).toEqual(expect.objectContaining({
      method: "POST",
      body: JSON.stringify(job.candidate),
      headers: expect.objectContaining({
        "Content-Type": "application/json",
        "X-Prompt-Enhancer-CSRF": AUTH_RESPONSE.csrf_token,
      }),
    }));
  });

  it.each([
    "https://outside.invalid/v1/discovery/candidates",
    "//outside.invalid/v1/discovery/candidates",
    "v1/discovery/candidates",
    "/v1\\discovery\\candidates",
  ])("rejects unexpected target %s", (target) => {
    expect(() => assertSameOriginRelativePath(target, "http://127.0.0.1:4173")).toThrow(
      TransportError,
    );
  });

  it("bootstraps browser auth and uses relative URLs with included credentials", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) =>
      input === "/auth/session"
        ? jsonResponse(AUTH_RESPONSE)
        : jsonResponse({ candidates: [], limit: 100, offset: 0 }),
    ) as unknown as typeof fetch;
    const transport = createHttpTransport({
      fetch: fetchMock,
      origin: "http://127.0.0.1:4173",
    });

    await transport.listCandidates("undecided");

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/auth/session",
      expect.objectContaining({
        credentials: "include",
        method: "GET",
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/v1/discovery/candidates?status=undecided",
      expect.objectContaining({
        credentials: "include",
        method: "GET",
        redirect: "error",
        referrerPolicy: "no-referrer",
      }),
    );
  });

  it("carries exact bounded pagination through each Task Flow index", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      if (input === "/auth/session") return jsonResponse(AUTH_RESPONSE);
      if (String(input).startsWith("/v1/discovery/candidates")) {
        return jsonResponse({ candidates: [], limit: 100, offset: 100 });
      }
      if (String(input).startsWith("/v1/task-revisions")) {
        return jsonResponse({ tasks: [], limit: 100, offset: 200 });
      }
      return jsonResponse({ runs: [], limit: 100, offset: 300 });
    });
    const transport = createHttpTransport({
      fetch: fetchMock as unknown as typeof fetch,
      origin: "http://127.0.0.1:4173",
    });
    const taskId = "a".repeat(64);

    await transport.listCandidates("all", undefined, { limit: 100, offset: 100 });
    await transport.listTaskRevisions(taskId, undefined, { limit: 100, offset: 200 });
    await transport.listAnalysisRuns(undefined, undefined, { limit: 100, offset: 300 });

    expect(fetchMock.mock.calls.slice(1).map((call) => call[0])).toEqual([
      "/v1/discovery/candidates?limit=100&offset=100",
      `/v1/task-revisions?task_id=${taskId}&limit=100&offset=200`,
      "/v1/analysis/runs?limit=100&offset=300",
    ]);
  });

  it("reads private loopback control-plane readiness without a data credential", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) =>
      input === "/auth/session"
        ? jsonResponse(AUTH_RESPONSE)
        : privateJsonResponse(CONTROL_PLANE_READINESS_RESPONSE),
    );
    const transport = createHttpTransport({
      fetch: fetchMock as unknown as typeof fetch,
      origin: "http://127.0.0.1:4173",
    });

    await expect(transport.getControlPlaneReadiness()).resolves.toEqual(
      CONTROL_PLANE_READINESS_RESPONSE,
    );

    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/v1/control-plane/readiness",
      expect.objectContaining({
        cache: "no-store",
        credentials: "include",
        method: "GET",
      }),
    );
    const headers = fetchMock.mock.calls[1][1]?.headers as Record<string, string>;
    expect(headers).not.toHaveProperty("X-Control-Plane-Credential");
    expect(headers).not.toHaveProperty("X-Prompt-Enhancer-CSRF");
  });

  it("rejects control-plane readiness without exact private cache headers", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(AUTH_RESPONSE))
      .mockResolvedValueOnce(jsonResponse(CONTROL_PLANE_READINESS_RESPONSE));
    const transport = createHttpTransport({
      fetch: fetchMock as unknown as typeof fetch,
      origin: "http://127.0.0.1:4173",
    });

    await expect(transport.getControlPlaneReadiness()).rejects.toMatchObject({
      status: 200,
    });
  });

  it("does not parse an unexpected response type", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(AUTH_RESPONSE))
      .mockResolvedValueOnce(
        new Response("not-json", {
          status: 200,
          headers: { "Content-Type": "text/plain" },
        }),
      ) as unknown as typeof fetch;
    const transport = createHttpTransport({
      fetch: fetchMock,
      origin: "http://127.0.0.1:4173",
    });

    await expect(transport.listCandidates()).rejects.toMatchObject({ status: 200 });
  });

  it("derives a content-free text-analysis capability only from coherent privacy fields", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(AUTH_RESPONSE))
      .mockResolvedValueOnce(
        jsonResponse({
          session_text_analysis: true,
          session_text_analysis_data_tier: "redacted_content",
          session_text_content_persistence: false,
          codex_local_source: true,
          network_inference: false,
          raw_transcripts: false,
          unrelated_server_field: "discarded",
        }),
      );
    const transport = createHttpTransport({
      fetch: fetchMock as unknown as typeof fetch,
      origin: "http://127.0.0.1:4173",
    });

    await expect(transport.getSessionTextAnalysisCapability()).resolves.toEqual({
      available: true,
      reason_code: "available",
      data_tier: "redacted_content",
      content_persistence: false,
      network_inference: false,
      raw_transcripts: false,
    });
    expect(fetchMock.mock.calls[1][0]).toBe("/v1/capabilities");
  });

  it("fails closed on malformed or contradictory text-analysis capabilities", () => {
    expect(() =>
      parseSessionTextAnalysisCapability({
        session_text_analysis: true,
        session_text_analysis_data_tier: null,
        session_text_content_persistence: false,
        codex_local_source: true,
        network_inference: false,
        raw_transcripts: false,
      }),
    ).toThrow(TransportError);
    expect(() =>
      parseSessionTextAnalysisCapability({
        session_text_analysis: false,
        session_text_analysis_data_tier: null,
        session_text_content_persistence: false,
        codex_local_source: false,
        network_inference: true,
        raw_transcripts: false,
      }),
    ).toThrow(TransportError);
  });

  it("parses only an exact coherent content-free provider compatibility DTO", () => {
    expect(parseProviderCompatibilityStatus(PROVIDER_COMPATIBILITY)).toEqual(
      PROVIDER_COMPATIBILITY,
    );
    expect(() =>
      parseProviderCompatibilityStatus(PROVIDER_COMPATIBILITY, "claude_code"),
    ).toThrow(TransportError);
    expect(() =>
      parseProviderCompatibilityStatus({
        ...PROVIDER_COMPATIBILITY,
        private_provider_detail: "PRIVATE-CANARY",
      }),
    ).toThrow(TransportError);
    expect(() =>
      parseProviderCompatibilityStatus({
        ...PROVIDER_COMPATIBILITY,
        capability_state: "unsupported",
      }),
    ).toThrow(TransportError);
    expect(() =>
      parseProviderCompatibilityStatus({
        ...PROVIDER_COMPATIBILITY,
        provider_family: "private-hostname",
      }),
    ).toThrow(TransportError);
    expect(() =>
      parseProviderCompatibilityStatus({
        ...PROVIDER_COMPATIBILITY,
        adapter_version: "C:/Users/example",
      }),
    ).toThrow(TransportError);
  });

  it("loads cached compatibility and checks it only through an explicit mutation", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(AUTH_RESPONSE))
      .mockResolvedValueOnce(jsonResponse(PROVIDER_COMPATIBILITY))
      .mockResolvedValueOnce(jsonResponse(PROVIDER_COMPATIBILITY));
    const transport = createHttpTransport({
      fetch: fetchMock as unknown as typeof fetch,
      origin: "http://127.0.0.1:4173",
    });

    await transport.getProviderCompatibility?.("codex");
    await transport.checkProviderCompatibility?.("codex");

    expect(fetchMock.mock.calls[1][0]).toBe(
      "/v1/providers/codex/compatibility",
    );
    expect(fetchMock.mock.calls[1][1]).toEqual(
      expect.objectContaining({ method: "GET" }),
    );
    expect(fetchMock.mock.calls[1][1]?.headers).not.toEqual(
      expect.objectContaining({ "X-Prompt-Enhancer-CSRF": expect.anything() }),
    );
    expect(fetchMock.mock.calls[2][0]).toBe(
      "/v1/providers/codex/compatibility/check",
    );
    expect(fetchMock.mock.calls[2][1]).toEqual(
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          "X-Prompt-Enhancer-CSRF": AUTH_RESPONSE.csrf_token,
        }),
      }),
    );
  });

  it("reads cached provider and session metric readiness through exact GET routes", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(AUTH_RESPONSE))
      .mockResolvedValueOnce(jsonResponse(SYNTHETIC_PROVIDER_METRIC_CAPABILITIES))
      .mockResolvedValueOnce(jsonResponse(SYNTHETIC_SESSION_METRIC_READINESS));
    const transport = createHttpTransport({
      fetch: fetchMock as unknown as typeof fetch,
      origin: "http://127.0.0.1:4173",
    });

    await expect(
      transport.getProviderMetricCapabilities("synthetic"),
    ).resolves.toEqual(SYNTHETIC_PROVIDER_METRIC_CAPABILITIES);
    await expect(
      transport.getSessionMetricReadiness(
        SYNTHETIC_SESSION_METRIC_READINESS.session_id,
      ),
    ).resolves.toEqual(SYNTHETIC_SESSION_METRIC_READINESS);

    expect(fetchMock.mock.calls[1][0]).toBe(
      "/v1/providers/synthetic/capabilities",
    );
    expect(fetchMock.mock.calls[2][0]).toBe(
      `/v1/sessions/${SYNTHETIC_SESSION_METRIC_READINESS.session_id}/metric-readiness?preset_id=coaching_profile_v1`,
    );
    for (const call of fetchMock.mock.calls.slice(1)) {
      expect(call[1]).toEqual(expect.objectContaining({ method: "GET" }));
      expect(call[1]?.headers).not.toEqual(
        expect.objectContaining({ "X-Prompt-Enhancer-CSRF": expect.anything() }),
      );
    }
  });

  it("accepts only the complete coherent content-free provider capability projection", () => {
    expect(
      parseProviderCapabilityReport(
        SYNTHETIC_PROVIDER_METRIC_CAPABILITIES,
        "synthetic",
      ),
    ).toEqual(SYNTHETIC_PROVIDER_METRIC_CAPABILITIES);

    expect(
      parseProviderCapabilityReport({
        ...SYNTHETIC_PROVIDER_METRIC_CAPABILITIES,
        provider_version: "synthetic/1:compatible",
      }),
    ).toMatchObject({ provider_version: "synthetic/1:compatible" });

    const duplicateCapability = structuredClone(
      SYNTHETIC_PROVIDER_METRIC_CAPABILITIES,
    );
    duplicateCapability.capabilities[6] = structuredClone(
      duplicateCapability.capabilities[0],
    );
    const incoherentState = structuredClone(
      SYNTHETIC_PROVIDER_METRIC_CAPABILITIES,
    );
    incoherentState.capabilities[0] = {
      ...incoherentState.capabilities[0],
      state: "unsupported",
    };
    const invalidCount = {
      ...SYNTHETIC_PROVIDER_METRIC_CAPABILITIES,
      structurally_attemptable_metric_count: 19,
    };

    expect(() =>
      parseProviderCapabilityReport({
        ...SYNTHETIC_PROVIDER_METRIC_CAPABILITIES,
        private_payload: "SYNTHETIC-PRIVATE-CANARY",
      }),
    ).toThrow(TransportError);
    expect(() => parseProviderCapabilityReport(duplicateCapability)).toThrow(
      TransportError,
    );
    expect(() => parseProviderCapabilityReport(incoherentState)).toThrow(
      TransportError,
    );
    expect(() => parseProviderCapabilityReport(invalidCount)).toThrow(
      TransportError,
    );
    expect(() =>
      parseProviderCapabilityReport(
        SYNTHETIC_PROVIDER_METRIC_CAPABILITIES,
        "codex",
      ),
    ).toThrow(TransportError);
  });

  it("reads provider and project metric coverage through private no-store routes", async () => {
    const projectId = "4".repeat(64);
    const projectCoverage = {
      ...structuredClone(SYNTHETIC_METRIC_COVERAGE),
      scope: "one_project" as const,
    };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(AUTH_RESPONSE))
      .mockResolvedValueOnce(privateJsonResponse(SYNTHETIC_METRIC_COVERAGE))
      .mockResolvedValueOnce(privateJsonResponse(projectCoverage));
    const transport = createHttpTransport({
      fetch: fetchMock as unknown as typeof fetch,
      origin: "http://127.0.0.1:4173",
    });

    await expect(transport.getMetricCoverage("synthetic")).resolves.toEqual(
      SYNTHETIC_METRIC_COVERAGE,
    );
    await expect(
      transport.getProjectMetricCoverage(projectId, "synthetic"),
    ).resolves.toEqual(projectCoverage);

    expect(fetchMock.mock.calls[1][0]).toBe(
      "/v1/metric-coverage?provider=synthetic",
    );
    expect(fetchMock.mock.calls[2][0]).toBe(
      `/v1/projects/${projectId}/metric-coverage?provider=synthetic`,
    );
    for (const call of fetchMock.mock.calls.slice(1)) {
      expect(call[1]).toEqual(expect.objectContaining({
        cache: "no-store",
        method: "GET",
      }));
    }
  });

  it("fails closed when metric coverage is not delivered as a private response", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(AUTH_RESPONSE))
      .mockResolvedValueOnce(jsonResponse(SYNTHETIC_METRIC_COVERAGE));
    const transport = createHttpTransport({
      fetch: fetchMock as unknown as typeof fetch,
      origin: "http://127.0.0.1:4173",
    });

    await expect(transport.getMetricCoverage("synthetic")).rejects.toThrow(
      "Private local response was not cache-safe",
    );
  });

  it("accepts only exact, identifier-free and internally preserved coverage", () => {
    expect(
      parseMetricCoverageReport(
        SYNTHETIC_METRIC_COVERAGE,
        "synthetic",
        "provider_catalog",
      ),
    ).toEqual(SYNTHETIC_METRIC_COVERAGE);

    const cases: unknown[] = [
      { ...SYNTHETIC_METRIC_COVERAGE, project_id: "4".repeat(64) },
      { ...SYNTHETIC_METRIC_COVERAGE, generated_at: "2040-02-31T09:13:00Z" },
      {
        ...SYNTHETIC_METRIC_COVERAGE,
        capability_report: {
          ...SYNTHETIC_METRIC_COVERAGE.capability_report,
          checked_at: "2040-02-31T09:13:00Z",
        },
      },
      { ...SYNTHETIC_METRIC_COVERAGE, provider: "codex" },
      {
        ...SYNTHETIC_METRIC_COVERAGE,
        latest_profile_runs: {
          completed: 0, running: 0, failed: 0, never_run: 1,
        },
      },
      (() => {
        const value = structuredClone(SYNTHETIC_METRIC_COVERAGE);
        value.metrics[0].contract_compatible_result_states.known = 2;
        return value;
      })(),
      (() => {
        const value = structuredClone(SYNTHETIC_METRIC_COVERAGE);
        value.metrics[0].display_name = "PRIVATE-COVERAGE-CANARY";
        return value;
      })(),
      (() => {
        const value = structuredClone(SYNTHETIC_METRIC_COVERAGE);
        value.metrics.reverse();
        return value;
      })(),
    ];

    for (const value of cases) {
      expect(() =>
        parseMetricCoverageReport(value, "synthetic", "provider_catalog"),
      ).toThrow(TransportError);
    }
  });

  it("accepts the backend readiness-token alphabet and rejects values outside its bounds", () => {
    const completeAlphabet = "A._+:/-readiness-v1";
    const maximumLength = `A${"x".repeat(127)}`;
    expect(
      parseProviderCapabilityReport({
        ...SYNTHETIC_PROVIDER_METRIC_CAPABILITIES,
        provider_version: completeAlphabet,
        decoder_key: maximumLength,
        decoder_version: completeAlphabet,
      }),
    ).toMatchObject({
      provider_version: completeAlphabet,
      decoder_key: maximumLength,
      decoder_version: completeAlphabet,
    });

    for (const invalidToken of [
      ".leading-punctuation",
      "contains whitespace",
      `A${"x".repeat(128)}`,
    ]) {
      expect(() => parseProviderCapabilityReport({
        ...SYNTHETIC_PROVIDER_METRIC_CAPABILITIES,
        provider_version: invalidToken,
      })).toThrow(TransportError);
    }
  });

  it("rejects readiness metadata that is incomplete, reordered, or contradicts its state", () => {
    expect(
      parseSessionMetricReadinessReport(
        SYNTHETIC_SESSION_METRIC_READINESS,
        SYNTHETIC_SESSION_METRIC_READINESS.session_id,
      ),
    ).toEqual(SYNTHETIC_SESSION_METRIC_READINESS);

    const reordered = structuredClone(SYNTHETIC_SESSION_METRIC_READINESS);
    reordered.metrics.reverse();
    const contradictoryAction = structuredClone(
      SYNTHETIC_SESSION_METRIC_READINESS,
    );
    contradictoryAction.metrics[0].next_actions = ["retry_analysis"];
    const privateDisplay = structuredClone(SYNTHETIC_SESSION_METRIC_READINESS);
    privateDisplay.metrics[0].display_name = "SYNTHETIC-PRIVATE-CANARY";
    const duplicateMetric = structuredClone(SYNTHETIC_SESSION_METRIC_READINESS);
    duplicateMetric.metrics[19] = structuredClone(duplicateMetric.metrics[0]);

    expect(() =>
      parseSessionMetricReadinessReport({
        ...SYNTHETIC_SESSION_METRIC_READINESS,
        raw_excerpt: "SYNTHETIC-PRIVATE-CANARY",
      }),
    ).toThrow(TransportError);
    expect(() => parseSessionMetricReadinessReport(reordered)).toThrow(
      TransportError,
    );
    expect(() => parseSessionMetricReadinessReport(contradictoryAction)).toThrow(
      TransportError,
    );
    expect(() => parseSessionMetricReadinessReport(privateDisplay)).toThrow(
      TransportError,
    );
    expect(() => parseSessionMetricReadinessReport(duplicateMetric)).toThrow(
      TransportError,
    );
    expect(() =>
      parseSessionMetricReadinessReport(
        SYNTHETIC_SESSION_METRIC_READINESS,
        "f".repeat(64),
      ),
    ).toThrow(TransportError);
  });

  it.each([
    "metric_not_selected",
    "metric_scope_unknown",
  ] as const)("accepts truthful %s readiness with an explicit selection action", (reason) => {
    const report = structuredClone(SYNTHETIC_SESSION_METRIC_READINESS);
    report.metrics[0].state = "unknown";
    report.metrics[0].reason_code = reason;
    report.metrics[0].next_actions = ["select_metric_for_analysis"];

    expect(parseSessionMetricReadinessReport(report).metrics[0]).toMatchObject({
      state: "unknown",
      reason_code: reason,
      next_actions: ["select_metric_for_analysis"],
      latest_run_id: SYNTHETIC_SESSION_METRIC_READINESS.metrics[0].latest_run_id,
    });
  });

  it.each([
    "queued", "preprocessing", "stage_n", "awaiting_approval", "completed",
    "partial", "failed", "cancelled", "superseded",
  ] as const)("accepts a coherent browser-safe %s job", (state) => {
    const parsed = parseAnalysisJobRecord(analysisJobPayload(state));
    expect(parsed.state).toBe(state);
    expect(parsed).not.toHaveProperty("dedupe_key");
    expect(parsed).not.toHaveProperty("lease_owner");
    expect(parsed).not.toHaveProperty("lease_token");
    expect(parsed).not.toHaveProperty("lease_expires_at");
  });

  it("rejects job payloads with private extras, remote execution, unsorted metrics, or incoherent runtime state", () => {
    const extra = {
      ...analysisJobPayload(),
      raw_error: "PRIVATE-JOB-ERROR-CANARY",
    };
    const remote = analysisJobPayload("queued");
    (remote.identity as Record<string, unknown>).local_only = false;
    const unsorted = analysisJobPayload("queued");
    (unsorted.identity as { metric_keys: string[] }).metric_keys.reverse();
    const leakedInternalFields = analysisJobPayload("queued", {
      dedupe_key: "2".repeat(64),
      lease_owner: "7".repeat(64),
      lease_token: "8".repeat(64),
      lease_expires_at: "2040-01-01T10:00:30Z",
    });
    const missingTerminal = analysisJobPayload("failed", {
      terminal_at: null,
      terminal_reason_code: null,
    });
    const wrongStage = analysisJobPayload("stage_n", { stage_number: null });

    for (const value of [
      extra,
      remote,
      unsorted,
      leakedInternalFields,
      missingTerminal,
      wrongStage,
    ]) {
      const error = (() => {
        try {
          parseAnalysisJobRecord(value);
          return null;
        } catch (caught) {
          return caught;
        }
      })();
      expect(error).toBeInstanceOf(TransportError);
      expect(String(error)).not.toContain("PRIVATE-JOB-ERROR-CANARY");
    }
  });

  it("validates filtered job pages and rejects duplicate or cross-state records", () => {
    const queued = analysisJobPayload("queued");
    expect(parseAnalysisJobPage(
      { jobs: [queued], limit: 25, offset: 0 },
      25,
      0,
      "queued",
    ).jobs).toHaveLength(1);
    expect(() => parseAnalysisJobPage(
      { jobs: [queued, queued], limit: 25, offset: 0 },
      25,
      0,
      "queued",
    )).toThrow(TransportError);
    expect(() => parseAnalysisJobPage(
      { jobs: [analysisJobPayload("failed")], limit: 25, offset: 0 },
      25,
      0,
      "queued",
    )).toThrow(TransportError);
  });

  it("lists, opens, resolves latest, and cancels content-free jobs on exact routes", async () => {
    const queued = analysisJobPayload("queued");
    const cancelled = analysisJobPayload("cancelled", {
      terminal_reason_code: "cancellation_requested",
    });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(AUTH_RESPONSE))
      .mockResolvedValueOnce(privateJsonResponse({ jobs: [queued], limit: 25, offset: 50 }))
      .mockResolvedValueOnce(privateJsonResponse(queued))
      .mockResolvedValueOnce(privateJsonResponse(queued))
      .mockResolvedValueOnce(privateJsonResponse(cancelled));
    const transport = createHttpTransport({
      fetch: fetchMock as unknown as typeof fetch,
      origin: "http://127.0.0.1:4173",
    });

    const page = await transport.listAnalysisJobs("queued", 25, 50);
    await transport.getAnalysisJob("1".repeat(64));
    await transport.getLatestSessionAnalysisJob("4".repeat(64));
    const result = await transport.cancelAnalysisJob("1".repeat(64));

    expect(page.jobs).toHaveLength(1);
    expect(result.state).toBe("cancelled");
    expect(fetchMock.mock.calls[1][0]).toBe(
      "/v1/analysis-jobs?limit=25&offset=50&state=queued",
    );
    expect(fetchMock.mock.calls[2][0]).toBe(`/v1/analysis-jobs/${"1".repeat(64)}`);
    expect(fetchMock.mock.calls[3][0]).toBe(
      `/v1/sessions/${"4".repeat(64)}/analysis-jobs/latest`,
    );
    expect(fetchMock.mock.calls[4][0]).toBe(
      `/v1/analysis-jobs/${"1".repeat(64)}/cancellation`,
    );
    expect(fetchMock.mock.calls[4][1]).toEqual(expect.objectContaining({
      cache: "no-store",
      method: "POST",
      credentials: "include",
    }));
    expect((fetchMock.mock.calls[4][1] as RequestInit).headers).toEqual(
      expect.objectContaining({
        "X-Prompt-Enhancer-CSRF": AUTH_RESPONSE.csrf_token,
      }),
    );
  });

  it("fails closed when the job API omits private no-store response headers", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(AUTH_RESPONSE))
      .mockResolvedValueOnce(jsonResponse({
        jobs: [analysisJobPayload("queued")],
        limit: 25,
        offset: 0,
      }));
    const transport = createHttpTransport({
      fetch: fetchMock as unknown as typeof fetch,
      origin: "http://127.0.0.1:4173",
    });

    await expect(transport.listAnalysisJobs("queued", 25, 0)).rejects.toThrow(
      "Private local response was not cache-safe",
    );
    expect(fetchMock.mock.calls[1][1]).toEqual(expect.objectContaining({
      cache: "no-store",
    }));
  });

  it.each(["active", "revoked", "expired"] as const)(
    "accepts a coherent %s automation grant with a fixed 30-day lifetime",
    (state) => {
      const record = parseAutomationGrantRecord(automationGrantPayload(state));
      expect(record.state).toBe(state);
      expect(record.scope.local_only).toBe(true);
      expect(record.scope.remote_requires_fresh_approval).toBe(true);
    },
  );

  it("rejects private extras, remote scope, identity drift, and incoherent automation grants", () => {
    const privateExtra = {
      ...automationGrantPayload(),
      prompt: "PRIVATE-AUTOMATION-CANARY",
    };
    const remote = automationGrantPayload();
    (remote.scope as AutomationGrantScope).local_only = false as true;
    const unsorted = automationGrantPayload();
    (unsorted.scope as AutomationGrantScope).metric_keys.reverse();
    const wrongLifetime = automationGrantPayload("active", {
      expires_at: "2040-02-01T09:00:00Z",
    });
    const missingRevocation = automationGrantPayload("revoked", {
      revoked_at: null,
    });
    const privatePolicy = automationGrantPayload();
    (privatePolicy.scope as AutomationGrantScope).resource_policy = {
      ...automationScope().resource_policy,
      max_gpu_workers: 2 as 1,
    };

    for (const value of [
      privateExtra,
      remote,
      unsorted,
      wrongLifetime,
      missingRevocation,
      privatePolicy,
    ]) {
      const error = (() => {
        try {
          parseAutomationGrantRecord(value);
          return null;
        } catch (caught) {
          return caught;
        }
      })();
      expect(error).toBeInstanceOf(TransportError);
      expect(String(error)).not.toContain("PRIVATE-AUTOMATION-CANARY");
    }
    expect(() => parseAutomationGrantRecord(
      automationGrantPayload(),
      "9".repeat(64),
      automationScope({ project_id: "8".repeat(64) }),
    )).toThrow(TransportError);
  });

  it("validates provider-bound automation lists and content-free poll counters", () => {
    const grant = automationGrantPayload();
    expect(parseAutomationGrantList([grant], "codex")).toHaveLength(1);
    expect(() => parseAutomationGrantList([grant, grant], "codex")).toThrow(
      TransportError,
    );
    expect(() => parseAutomationGrantList([grant], "claude_code")).toThrow(
      TransportError,
    );
    const poll = {
      grants_checked: 1,
      grants_revoked: 0,
      grants_power_paused: 0,
      grants_policy_unsupported: 0,
      power_external_observations: 1,
      power_battery_observations: 0,
      power_unknown_observations: 0,
      candidates_seen: 2,
      jobs_created: 1,
      jobs_reused: 1,
      jobs_superseded: 0,
      failures: 0,
      maximum_session_runtime_deadline_enforced: false as const,
      session_quality_result_publication_deadline_enforced: true as const,
      blocking_execution_preemption_enforced: false as const,
    };
    expect(parseAutomationPollResult(poll)).toEqual(poll);
    expect(() => parseAutomationPollResult({ ...poll, failures: -1 })).toThrow(
      TransportError,
    );
    expect(() => parseAutomationPollResult({ ...poll, raw_error: "private" })).toThrow(
      TransportError,
    );

    const incoherent = [
      { ...poll, grants_checked: 2 },
      { ...poll, grants_power_paused: 1 },
      { ...poll, grants_policy_unsupported: 1 },
      { ...poll, candidates_seen: 1 },
      { ...poll, jobs_superseded: 3 },
      { ...poll, maximum_session_runtime_deadline_enforced: true },
      { ...poll, session_quality_result_publication_deadline_enforced: false },
      { ...poll, blocking_execution_preemption_enforced: true },
    ];
    for (const value of incoherent) {
      expect(() => parseAutomationPollResult(value)).toThrow(TransportError);
    }
  });

  it.each([
    ["fast route", { route: "fast" }],
    ["two CPU workers", { max_cpu_workers: 2 }],
    ["battery continuation", { pause_on_battery: false }],
    ["different runtime budget", { maximum_session_seconds: 3_600 }],
  ])("rejects an unreviewed create profile (%s) before fetch", async (_label, update) => {
    const fetchMock = vi.fn();
    const transport = createHttpTransport({
      fetch: fetchMock as unknown as typeof fetch,
      origin: "http://127.0.0.1:4173",
    });
    const scope = automationScope();
    const request = {
      provider: scope.provider,
      project_id: scope.project_id,
      metric_keys: scope.metric_keys,
      newest_session_limit: scope.newest_session_limit,
      check_interval_seconds: scope.check_interval_seconds,
      resource_policy: {
        route: "balanced",
        max_gpu_workers: 1,
        max_cpu_workers: 1,
        pause_on_battery: true,
        maximum_session_seconds: 1_800,
        ...update,
      },
    };

    await expect(transport.createAutomationGrant(request as never)).rejects.toMatchObject({
      status: 400,
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("lists, creates, opens, renews, revokes, and polls automation on exact private routes", async () => {
    const scope = automationScope();
    const active = automationGrantPayload();
    const renewed = automationGrantPayload("active", {
      revision: 2,
      renewed_at: "2040-01-02T09:00:00Z",
      expires_at: "2040-02-01T09:00:00Z",
      next_check_at: "2040-01-02T09:00:00Z",
    });
    const revoked = { ...renewed, state: "revoked", revoked_at: "2040-01-02T10:00:00Z" };
    const poll = {
      grants_checked: 1,
      grants_revoked: 0,
      grants_power_paused: 0,
      grants_policy_unsupported: 0,
      power_external_observations: 1,
      power_battery_observations: 0,
      power_unknown_observations: 0,
      candidates_seen: 2,
      jobs_created: 1,
      jobs_reused: 1,
      jobs_superseded: 0,
      failures: 0,
      maximum_session_runtime_deadline_enforced: false as const,
      session_quality_result_publication_deadline_enforced: true as const,
      blocking_execution_preemption_enforced: false as const,
    };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(AUTH_RESPONSE))
      .mockResolvedValueOnce(privateJsonResponse([active]))
      .mockResolvedValueOnce(privateJsonResponse(active))
      .mockResolvedValueOnce(privateJsonResponse(active, 201))
      .mockResolvedValueOnce(privateJsonResponse(renewed))
      .mockResolvedValueOnce(privateJsonResponse(revoked))
      .mockResolvedValueOnce(privateJsonResponse(poll));
    const transport = createHttpTransport({
      fetch: fetchMock as unknown as typeof fetch,
      origin: "http://127.0.0.1:4173",
    });
    const createRequest = {
      provider: scope.provider,
      project_id: scope.project_id,
      metric_keys: scope.metric_keys,
      newest_session_limit: scope.newest_session_limit,
      check_interval_seconds: scope.check_interval_seconds,
      resource_policy: {
        route: "balanced" as const,
        max_gpu_workers: 1 as const,
        max_cpu_workers: 1 as const,
        pause_on_battery: true as const,
        maximum_session_seconds: 1_800 as const,
      },
    };

    await transport.listAutomationGrants("codex", false);
    await transport.getAutomationGrant("9".repeat(64), scope);
    await transport.createAutomationGrant(createRequest);
    await transport.renewAutomationGrant("9".repeat(64), scope);
    await transport.revokeAutomationGrant("9".repeat(64), scope);
    expect(await transport.pollAutomationGrants()).toEqual(poll);

    expect(fetchMock.mock.calls.slice(1).map((call) => call[0])).toEqual([
      "/v1/automation-grants?provider=codex&active_only=false",
      `/v1/automation-grants/${"9".repeat(64)}`,
      "/v1/automation-grants",
      `/v1/automation-grants/${"9".repeat(64)}/renewal`,
      `/v1/automation-grants/${"9".repeat(64)}/revocation`,
      "/v1/automation-grants/poll",
    ]);
    for (const [, request] of fetchMock.mock.calls.slice(1)) {
      expect(request).toEqual(expect.objectContaining({
        cache: "no-store",
        credentials: "include",
      }));
    }
    expect(JSON.parse((fetchMock.mock.calls[3][1] as RequestInit).body as string)).toEqual(
      createRequest,
    );
  });

  it("fails closed when automation responses are cacheable and preserves safe consent reasons", async () => {
    const cacheableFetch = vi.fn()
      .mockResolvedValueOnce(jsonResponse(AUTH_RESPONSE))
      .mockResolvedValueOnce(jsonResponse([automationGrantPayload()]));
    const cacheable = createHttpTransport({
      fetch: cacheableFetch as unknown as typeof fetch,
      origin: "http://127.0.0.1:4173",
    });
    await expect(cacheable.listAutomationGrants("codex")).rejects.toThrow(
      "Private local response was not cache-safe",
    );

    const deniedFetch = vi.fn()
      .mockResolvedValueOnce(jsonResponse(AUTH_RESPONSE))
      .mockResolvedValueOnce(privateJsonResponse({
        detail: { code: "automation_consent_required" },
      }, 403));
    const denied = createHttpTransport({
      fetch: deniedFetch as unknown as typeof fetch,
      origin: "http://127.0.0.1:4173",
    });
    await expect(denied.createAutomationGrant({
      provider: "codex",
      project_id: automationScope().project_id,
      metric_keys: automationScope().metric_keys,
      newest_session_limit: 20,
      check_interval_seconds: 900,
      resource_policy: {
        route: "balanced",
        max_gpu_workers: 1,
        max_cpu_workers: 1,
        pause_on_battery: true,
        maximum_session_seconds: 1_800,
      },
    })).rejects.toMatchObject({
      status: 403,
      reasonCode: "automation_consent_required",
    });
  });

  it("strictly validates a local preview and rejects remote, private-extra, drifted, or inconsistent shapes", () => {
    const sessionId = "5".repeat(64);
    const valid = redactionPreview(sessionId);
    expect(parseSessionQualityAnalysisPreview(valid, sessionId)).toEqual(valid);

    const remote = structuredClone(valid);
    remote.binding.destination = "remote" as "local";
    remote.binding.retention_class = "remote_30_day" as "local_ephemeral";
    remote.binding.cost_state = "unknown" as "not_applicable";
    const extra = { ...valid, raw_provider_path: "PRIVATE-PATH-CANARY" };
    const wrongSession = structuredClone(valid);
    wrongSession.binding.session_id = "6".repeat(64);
    const wrongCharacters = structuredClone(valid);
    wrongCharacters.binding.character_count += 1;
    const wrongTtl = structuredClone(valid);
    wrongTtl.expires_at = "2040-01-01T10:09:59Z";
    const incompleteMetrics = structuredClone(valid);
    incompleteMetrics.binding.metric_keys.pop();

    for (const value of [
      remote,
      extra,
      wrongSession,
      wrongCharacters,
      wrongTtl,
      incompleteMetrics,
    ]) {
      let error: unknown;
      try {
        parseSessionQualityAnalysisPreview(value, sessionId);
      } catch (caught) {
        error = caught;
      }
      expect(error).toBeInstanceOf(TransportError);
      expect(String(error)).not.toContain("PRIVATE-PATH-CANARY");
    }
  });

  it("prepares and approves an exact private preview with no-store transport policy", async () => {
    const sessionId = "5".repeat(64);
    const preview = redactionPreview(sessionId);
    const outcome = {
      run_id: "6".repeat(64),
      status: "completed",
      result_count: 20,
      applied: true,
      analysis_profile_key: "coaching_profile",
      analysis_profile_version: 1,
    };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(AUTH_RESPONSE))
      .mockResolvedValueOnce(privateJsonResponse(preview))
      .mockResolvedValueOnce(privateJsonResponse(outcome));
    const transport = createHttpTransport({
      fetch: fetchMock as unknown as typeof fetch,
      origin: "http://127.0.0.1:4173",
    });

    const prepared = await transport.prepareSessionQualityAnalysisPreview(
      sessionId,
      { preset_id: "coaching_profile_v1" },
    );
    const approved = await transport.approveSessionQualityAnalysisPreview(
      prepared.preview_id,
      {
        confirmation: "approve_exact_redacted_preview",
        expected_binding: prepared.binding,
      },
      "dashboard-quality-preview-approval-example",
    );

    expect(approved).toEqual(outcome);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls[1][0]).toBe(
      `/v1/sessions/${sessionId}/quality-analysis-previews`,
    );
    const preparation = fetchMock.mock.calls[1][1] as RequestInit;
    expect(preparation).toEqual(expect.objectContaining({
      method: "POST",
      cache: "no-store",
      credentials: "include",
      referrerPolicy: "no-referrer",
    }));
    expect(JSON.parse(preparation.body as string)).toEqual({
      preset_id: "coaching_profile_v1",
    });
    const approval = fetchMock.mock.calls[2][1] as RequestInit;
    expect(approval.cache).toBe("no-store");
    expect(approval.headers).toEqual(expect.objectContaining({
      "Idempotency-Key": "dashboard-quality-preview-approval-example",
      "X-Prompt-Enhancer-CSRF": AUTH_RESPONSE.csrf_token,
    }));
    expect(JSON.parse(approval.body as string)).toEqual({
      confirmation: "approve_exact_redacted_preview",
      expected_binding: preview.binding,
    });
  });

  it("fails closed if a secret-bearing success response lacks private no-store headers", async () => {
    const sessionId = "5".repeat(64);
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(AUTH_RESPONSE))
      .mockResolvedValueOnce(jsonResponse(redactionPreview(sessionId)));
    const transport = createHttpTransport({
      fetch: fetchMock as unknown as typeof fetch,
      origin: "http://127.0.0.1:4173",
    });

    await expect(
      transport.prepareSessionQualityAnalysisPreview(
        sessionId,
        { preset_id: "coaching_profile_v1" },
      ),
    ).rejects.toMatchObject({ status: 200, reasonCode: null });
  });

  it("extracts only an allowlisted preview failure code and discards server content", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(AUTH_RESPONSE))
      .mockResolvedValueOnce(privateJsonResponse({
        detail: {
          code: "redaction_preview_binding_mismatch",
          message: "PRIVATE-PREVIEW-ERROR-CANARY",
        },
      }, 409));
    const transport = createHttpTransport({
      fetch: fetchMock as unknown as typeof fetch,
      origin: "http://127.0.0.1:4173",
    });

    const error = await transport.approveSessionQualityAnalysisPreview(
      "e".repeat(64),
      {
        confirmation: "approve_exact_redacted_preview",
        expected_binding: redactionPreview().binding,
      },
      "dashboard-quality-preview-approval-mismatch",
    ).catch((value: unknown) => value);

    expect(error).toMatchObject({
      status: 409,
      reasonCode: "redaction_preview_binding_mismatch",
    });
    expect(String(error)).not.toContain("PRIVATE-PREVIEW-ERROR-CANARY");
  });

  it.each([
    "provider_unavailable",
    "no_analyzable_text",
    "provider_protocol_rejected",
    "provider_compatibility_blocked",
    "source_selection_limit",
    "source_provider_response_limit",
    "source_thread_structure_limit",
    "source_preview_window_limit",
    "source_resource_limit",
  ] as const)("extracts allowlisted detail code %s without forwarding server messages", async (code) => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(AUTH_RESPONSE))
      .mockResolvedValueOnce(
        jsonResponse(
          {
            detail: {
              code,
              message: "PRIVATE-SERVER-CONTENT-CANARY",
            },
            reason_code: "metric_execution_failed",
          },
          503,
        ),
      );
    const transport = createHttpTransport({
      fetch: fetchMock as unknown as typeof fetch,
      origin: "http://127.0.0.1:4173",
    });

    const error = await transport
      .startSessionQualityAnalysis(
        "5".repeat(64),
        CONTENT_FREE_ANALYSIS_REQUEST,
        `dashboard-quality-analysis-safe-error-${code}`,
      )
      .catch((value: unknown) => value);
    expect(error).toMatchObject({
      status: 503,
      reasonCode: code,
    });
    expect(String(error)).not.toContain("PRIVATE-SERVER-CONTENT-CANARY");
  });

  it("ignores unknown, top-level, and raw safe-looking error details", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(AUTH_RESPONSE))
      .mockResolvedValueOnce(
        jsonResponse(
          {
            detail: { code: "PRIVATE_UNKNOWN_CODE", message: "provider_unavailable" },
            reason_code: "provider_unavailable",
          },
          503,
        ),
      );
    const transport = createHttpTransport({
      fetch: fetchMock as unknown as typeof fetch,
      origin: "http://127.0.0.1:4173",
    });

    const error = await transport
      .startSessionQualityAnalysis(
        "5".repeat(64),
        CONTENT_FREE_ANALYSIS_REQUEST,
        "dashboard-quality-analysis-unknown-error",
      )
      .catch((value: unknown) => value);
    expect(error).toMatchObject({ status: 503, reasonCode: null });
  });

  it("loads a project-scoped bounded session page", async () => {
    const projectId = "4".repeat(64);
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(AUTH_RESPONSE))
      .mockResolvedValueOnce(
        jsonResponse({
          sessions: [],
          limit: 25,
          offset: 50,
          total: 75,
          has_more: false,
        }),
      );
    const transport = createHttpTransport({
      fetch: fetchMock as unknown as typeof fetch,
      origin: "http://127.0.0.1:4173",
    });

    const response = await transport.listProjectSessions(projectId, 25, 50);

    expect(response).toMatchObject({ total: 75, has_more: false });
    expect(fetchMock.mock.calls[1][0]).toBe(
      `/v1/projects/${projectId}/sessions?limit=25&offset=50`,
    );
    expect(fetchMock.mock.calls[1][1]).toEqual(
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("keeps CSRF in memory and attaches it only to mutations", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(AUTH_RESPONSE))
      .mockResolvedValueOnce(
        jsonResponse({
          consent_active: true,
          indexed_sessions: 0,
          indexed_projects: 0,
        }),
      );
    const transport = createHttpTransport({
      fetch: fetchMock as unknown as typeof fetch,
      origin: "http://127.0.0.1:4173",
    });

    await transport.grantCodexLocalHistoryConsent();

    const mutationInit = fetchMock.mock.calls[1][1] as RequestInit;
    expect(mutationInit).toEqual(
      expect.objectContaining({ credentials: "include", method: "POST" }),
    );
    expect(mutationInit.headers).toEqual(
      expect.objectContaining({
        "X-Prompt-Enhancer-CSRF": "synthetic-csrf-token",
      }),
    );
    expect(mutationInit.headers).not.toEqual(
      expect.objectContaining({ "X-Prompt-Enhancer-Token": expect.anything() }),
    );
  });

  it("shares one browser bootstrap across concurrent initial requests", async () => {
    let resolveBootstrap: ((response: Response) => void) | undefined;
    const pendingBootstrap = new Promise<Response>((resolve) => {
      resolveBootstrap = resolve;
    });
    const fetchMock = vi.fn((input: RequestInfo | URL) =>
      input === "/auth/session"
        ? pendingBootstrap
        : Promise.resolve(jsonResponse({ candidates: [], limit: 100, offset: 0 })),
    );
    const transport = createHttpTransport({
      fetch: fetchMock as unknown as typeof fetch,
      origin: "http://127.0.0.1:4173",
    });

    const first = transport.listCandidates();
    const second = transport.listCandidates();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    resolveBootstrap?.(jsonResponse(AUTH_RESPONSE));
    await Promise.all([first, second]);

    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(
      fetchMock.mock.calls.filter(([input]) => input === "/auth/session"),
    ).toHaveLength(1);
  });

  it("re-establishes in-memory browser auth once after a 401", async () => {
    const refreshedAuth = {
      csrf_token: "synthetic-refreshed-csrf-token",
      expires_in_seconds: 300,
    };
    const sourceStatus = {
      consent_active: true,
      indexed_sessions: 0,
      indexed_projects: 0,
    };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(AUTH_RESPONSE))
      .mockResolvedValueOnce(jsonResponse({ detail: "authentication required" }, 401))
      .mockResolvedValueOnce(jsonResponse(refreshedAuth))
      .mockResolvedValueOnce(jsonResponse(sourceStatus));
    const transport = createHttpTransport({
      fetch: fetchMock as unknown as typeof fetch,
      origin: "http://127.0.0.1:4173",
    });

    await transport.grantCodexLocalHistoryConsent();

    expect(fetchMock).toHaveBeenCalledTimes(4);
    expect(fetchMock.mock.calls[0][0]).toBe("/auth/session");
    expect(fetchMock.mock.calls[2][0]).toBe("/auth/session");
    const retriedMutation = fetchMock.mock.calls[3][1] as RequestInit;
    expect(retriedMutation.headers).toEqual(
      expect.objectContaining({
        "X-Prompt-Enhancer-CSRF": "synthetic-refreshed-csrf-token",
      }),
    );
  });

  it("reads latest and detail quality snapshots without initiating an analysis", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(AUTH_RESPONSE))
      .mockResolvedValueOnce(jsonResponse(SYNTHETIC_SESSION_QUALITY_RUN))
      .mockResolvedValueOnce(jsonResponse(SYNTHETIC_SESSION_QUALITY_RUN))
      .mockResolvedValueOnce(jsonResponse({ projection_key: "coaching.loop.current" }));
    const transport = createHttpTransport({
      fetch: fetchMock as unknown as typeof fetch,
      origin: "http://127.0.0.1:4173",
    });

    await transport.getLatestSessionQualityAnalysis("5".repeat(64));
    await transport.getSessionQualityAnalysisRun("6".repeat(64));
    await transport.getSessionCoachingSummary!("6".repeat(64));

    expect(fetchMock.mock.calls[1][0]).toBe(
      `/v1/sessions/${"5".repeat(64)}/quality-analysis-runs/latest`,
    );
    expect(fetchMock.mock.calls[2][0]).toBe(
      `/v1/quality-analysis/runs/${"6".repeat(64)}`,
    );
    expect(fetchMock.mock.calls[3][0]).toBe(
      `/v1/quality-analysis/runs/${"6".repeat(64)}/coaching-summary`,
    );
    expect(fetchMock.mock.calls[3][1]).toEqual(
      expect.objectContaining({ method: "GET" }),
    );
    expect(fetchMock.mock.calls[1][1]).toEqual(
      expect.objectContaining({ method: "GET" }),
    );
    expect(fetchMock.mock.calls[1][1]?.headers).not.toEqual(
      expect.objectContaining({ "Idempotency-Key": expect.anything() }),
    );
  });

  it("posts the exact reviewed quality request with in-memory CSRF and idempotency", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(AUTH_RESPONSE))
      .mockResolvedValueOnce(
        jsonResponse({
          run_id: "6".repeat(64),
          status: "completed",
          result_count: 20,
          applied: true,
          analysis_profile_key: "coaching_profile",
          analysis_profile_version: 1,
        }),
      );
    const transport = createHttpTransport({
      fetch: fetchMock as unknown as typeof fetch,
      origin: "http://127.0.0.1:4173",
    });
    const request: SessionQualityAnalysisRequest = {
      confirmation: "analyze_selected_redacted_text",
      preset_id: "coaching_profile_v1",
    };

    const outcome = await transport.startSessionQualityAnalysis(
      "5".repeat(64),
      request,
      "dashboard-quality-analysis-example",
    );

    expect(fetchMock.mock.calls[1][0]).toBe(
      `/v1/sessions/${"5".repeat(64)}/quality-analysis-runs`,
    );
    const mutation = fetchMock.mock.calls[1][1] as RequestInit;
    expect(mutation.method).toBe("POST");
    expect(mutation.headers).toEqual(
      expect.objectContaining({
        "Content-Type": "application/json",
        "Idempotency-Key": "dashboard-quality-analysis-example",
        "X-Prompt-Enhancer-CSRF": AUTH_RESPONSE.csrf_token,
      }),
    );
    expect(JSON.parse(mutation.body as string)).toEqual(request);
    expect(outcome).toMatchObject({
      analysis_profile_key: "coaching_profile",
      analysis_profile_version: 1,
    });
  });

  it("posts a content-free selected-session aggregate without an idempotency key", async () => {
    const sessionIds = ["5".repeat(64), "6".repeat(64)];
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(AUTH_RESPONSE))
      .mockResolvedValueOnce(jsonResponse({ selected_session_count: 2 }));
    const transport = createHttpTransport({
      fetch: fetchMock as unknown as typeof fetch,
      origin: "http://127.0.0.1:4173",
    });

    await transport.aggregateSessionQuality({ session_ids: sessionIds });

    expect(fetchMock.mock.calls[1][0]).toBe("/v1/quality-analysis/aggregate");
    const request = fetchMock.mock.calls[1][1] as RequestInit;
    expect(request.method).toBe("POST");
    expect(request.headers).toEqual(
      expect.objectContaining({
        "Content-Type": "application/json",
        "X-Prompt-Enhancer-CSRF": AUTH_RESPONSE.csrf_token,
      }),
    );
    expect(request.headers).not.toEqual(
      expect.objectContaining({ "Idempotency-Key": expect.anything() }),
    );
    expect(JSON.parse(request.body as string)).toEqual({ session_ids: sessionIds });
  });

  it("posts only the closed selected-project comparison scope", async () => {
    const projectIds = ["7".repeat(64), "8".repeat(64)];
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(AUTH_RESPONSE))
      .mockResolvedValueOnce(jsonResponse({ selected_project_count: 2 }));
    const transport = createHttpTransport({
      fetch: fetchMock as unknown as typeof fetch,
      origin: "http://127.0.0.1:4173",
    });

    await transport.aggregateProjectQuality({
      project_ids: projectIds,
      selection_mode: "all_analyzed_work",
    });

    expect(fetchMock.mock.calls[1][0]).toBe(
      "/v1/quality-analysis/aggregate-projects",
    );
    const request = fetchMock.mock.calls[1][1] as RequestInit;
    expect(request.method).toBe("POST");
    expect(request.headers).toEqual(
      expect.objectContaining({
        "Content-Type": "application/json",
        "X-Prompt-Enhancer-CSRF": AUTH_RESPONSE.csrf_token,
      }),
    );
    expect(request.headers).not.toEqual(
      expect.objectContaining({ "Idempotency-Key": expect.anything() }),
    );
    expect(JSON.parse(request.body as string)).toEqual({
      project_ids: projectIds,
      selection_mode: "all_analyzed_work",
    });
  });
});

describe("local agent event streaming transport", () => {
  it("consumes private same-origin SSE through the browser session", async () => {
    const sessionId = "a".repeat(32);
    const streamId = "b".repeat(32);
    const payload = {
      contract_version: "local-agent.v2",
      session_id: sessionId,
      events: [{
        seq: 1,
        at: "2026-08-20T01:00:00Z",
        kind: "assistant_delta",
        text: "Hello",
        reasoning: null,
        stream_id: streamId,
        stream_phase: "content",
        stream_status: null,
        tool: null,
        arguments: null,
        call_id: null,
        approval_id: null,
        ok: null,
        preview: null,
      }],
      running: false,
      pending_approval_id: null,
      last_seq: 1,
      first_seq: 1,
    };
    const encoded = new TextEncoder().encode(`data: ${JSON.stringify(payload)}\n\n`);
    const eventResponse = new Response(new ReadableStream({
      start(controller) {
        controller.enqueue(encoded.slice(0, 17));
        controller.enqueue(encoded.slice(17));
        controller.close();
      },
    }), {
      headers: {
        "Content-Type": "text/event-stream; charset=utf-8",
        "Cache-Control": "no-store, private",
        Pragma: "no-cache",
      },
    });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(AUTH_RESPONSE))
      .mockResolvedValueOnce(eventResponse);
    const transport = createHttpTransport({
      fetch: fetchMock as unknown as typeof fetch,
      origin: "http://127.0.0.1:4173",
    });
    const pages: unknown[] = [];

    await transport.streamAgentEvents(sessionId, 0, (page) => pages.push(page));

    expect(pages).toHaveLength(1);
    expect(fetchMock.mock.calls[1][0]).toBe(`/v1/agent/sessions/${sessionId}/events/stream?after=0&limit=8`);
    expect(fetchMock.mock.calls[1][1]).toEqual(expect.objectContaining({
      cache: "no-store",
      credentials: "include",
      redirect: "error",
      referrerPolicy: "no-referrer",
    }));
    expect(fetchMock.mock.calls[1][1]?.headers).toEqual({ Accept: "text/event-stream" });
  });
});

describe("local agent workspace transport", () => {
  it("uses relative session-bound routes and strict response parsing", async () => {
    const sessionId = "a".repeat(32);
    const base = "b".repeat(64);
    const proposed = "c".repeat(64);
    const previewId = "d".repeat(32);
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(AUTH_RESPONSE))
      .mockResolvedValueOnce(jsonResponse({
        contract_version: "local-agent-workspace.v1",
        session_id: sessionId,
        path: ".",
        entries: [{ path: "src", name: "src", kind: "directory", byte_size: null, editable_candidate: false }],
        complete: true,
      }))
      .mockResolvedValueOnce(jsonResponse({
        contract_version: "local-agent-workspace.v1",
        session_id: sessionId,
        path: "src/app.py",
        content: "one\ntwo\n",
        revision: base,
        byte_size: 8,
        line_ending: "lf",
        editable: true,
      }))
      .mockResolvedValueOnce(jsonResponse({
        contract_version: "local-agent-workspace.v1",
        session_id: sessionId,
        preview_id: previewId,
        path: "src/app.py",
        expected_revision: base,
        proposed_revision: proposed,
        line_ending: "lf",
        diff: "--- a/src/app.py\n+++ b/src/app.py\n@@ -1,2 +1,2 @@\n one\n-two\n+new",
        expires_at: "2026-08-20T20:00:00Z",
      }))
      .mockResolvedValueOnce(jsonResponse({
        contract_version: "local-agent-workspace.v1",
        session_id: sessionId,
        path: "src/app.py",
        revision: proposed,
        byte_size: 8,
        applied: true,
      }));
    const transport = createHttpTransport({
      fetch: fetchMock as unknown as typeof fetch,
      origin: "http://127.0.0.1:4173",
    });

    await expect(transport.getAgentWorkspaceTree(sessionId, ".")).resolves.toMatchObject({ path: "." });
    await expect(transport.getAgentWorkspaceFile(sessionId, "src/app.py")).resolves.toMatchObject({ revision: base });
    const previewRequest = { path: "src/app.py", content: "one\nnew\n", expected_revision: base, line_ending: "lf" as const };
    await expect(transport.previewAgentWorkspaceEdit(sessionId, previewRequest)).resolves.toMatchObject({ preview_id: previewId });
    await expect(transport.applyAgentWorkspaceEdit(sessionId, previewId, {
      path: "src/app.py",
      content: "one\nnew\n",
      expected_revision: base,
      proposed_revision: proposed,
      line_ending: "lf",
      confirmation: "apply_reviewed_workspace_edit",
    })).resolves.toMatchObject({ applied: true });

    expect(fetchMock.mock.calls[1][0]).toBe(`/v1/agent/sessions/${sessionId}/workspace/tree?path=.`);
    expect(fetchMock.mock.calls[2][0]).toBe(`/v1/agent/sessions/${sessionId}/workspace/file?path=src%2Fapp.py`);
    expect(fetchMock.mock.calls[3][0]).toBe(`/v1/agent/sessions/${sessionId}/workspace/previews`);
    expect(fetchMock.mock.calls[4][0]).toBe(`/v1/agent/sessions/${sessionId}/workspace/previews/${previewId}/apply`);
    const apply = fetchMock.mock.calls[4][1] as RequestInit;
    expect(apply.headers).toEqual(expect.objectContaining({
      "Content-Type": "application/json",
      "X-Prompt-Enhancer-CSRF": AUTH_RESPONSE.csrf_token,
    }));
  });

  it("rejects a workspace tree that returns an absolute local path", async () => {
    const sessionId = "a".repeat(32);
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(AUTH_RESPONSE))
      .mockResolvedValueOnce(jsonResponse({
        contract_version: "local-agent-workspace.v1",
        session_id: sessionId,
        path: ".",
        entries: [{ path: "C:/private.txt", name: "private.txt", kind: "file", byte_size: 1, editable_candidate: true }],
        complete: true,
      }));
    const transport = createHttpTransport({ fetch: fetchMock as unknown as typeof fetch, origin: "http://127.0.0.1:4173" });
    await expect(transport.getAgentWorkspaceTree(sessionId, ".")).rejects.toMatchObject({
      message: "Local agent workspace tree response was invalid",
      status: 200,
    });
  });
});
