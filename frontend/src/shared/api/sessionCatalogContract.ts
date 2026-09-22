import { isLocalProvider, type CodexSession } from "./contracts";
import { isPseudonym } from "../platform/platform";

export const SESSION_CATALOG_PAGE_SIZE = 100;

const SESSION_KEYS = [
  "adapter_version",
  "ended_at",
  "events_complete",
  "installation_id",
  "project_display_name",
  "project_display_name_origin",
  "project_id",
  "project_manual_label_revision",
  "provider",
  "provider_version",
  "session_display_name",
  "session_display_name_origin",
  "session_id",
  "session_manual_label_revision",
  "source_schema_version",
  "started_at",
  "terminal_state",
] as const;
const SAFE_VERSION = /^[A-Za-z0-9][A-Za-z0-9._+:/-]{0,127}$/;
const RFC3339_DATE_TIME =
  /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(Z|[+-](\d{2}):(\d{2}))$/;
const SESSION_STATES = new Set([
  "completed",
  "interrupted",
  "failed",
  "blocked",
  "abandoned",
  "unknown",
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasExactKeys(value: Record<string, unknown>, keys: readonly string[]) {
  const actual = Object.keys(value);
  return actual.length === keys.length && keys.every((key) => actual.includes(key));
}

function safeNullableLabel(value: unknown, maxLength: number): value is string | null {
  return value === null || (
    typeof value === "string" &&
    value.length >= 1 &&
    value.length <= maxLength &&
    !/[\u0000-\u001f\u007f]/.test(value)
  );
}

function safeNullableVersion(value: unknown): value is string | null {
  return value === null || (typeof value === "string" && SAFE_VERSION.test(value));
}

function safeDate(value: unknown, nullable = false): boolean {
  if (nullable && value === null) return true;
  if (typeof value !== "string") return false;
  const match = RFC3339_DATE_TIME.exec(value);
  if (match === null) return false;
  const [, yearText, monthText, dayText, hourText, minuteText, secondText, zone, offsetHourText, offsetMinuteText] = match;
  const year = Number(yearText);
  const month = Number(monthText);
  const day = Number(dayText);
  const hour = Number(hourText);
  const minute = Number(minuteText);
  const second = Number(secondText);
  const offsetHour = zone === "Z" ? 0 : Number(offsetHourText);
  const offsetMinute = zone === "Z" ? 0 : Number(offsetMinuteText);
  const maxDay = year >= 1 && month >= 1 && month <= 12
    ? new Date(Date.UTC(year, month, 0)).getUTCDate()
    : 0;
  return day >= 1 && day <= maxDay && hour <= 23 && minute <= 59 && second <= 59 &&
    offsetHour <= 23 && offsetMinute <= 59 && !Number.isNaN(new Date(value).valueOf());
}

/** Fail closed: catalog rows contain only exact content-free provenance. */
export function safeSessionCatalogRow(value: unknown): value is CodexSession {
  if (!isRecord(value) || !hasExactKeys(value, SESSION_KEYS)) return false;
  const origins = new Set(["provider", "manual", "unknown"]);
  return (
    isLocalProvider(value.provider) &&
    typeof value.installation_id === "string" && isPseudonym(value.installation_id) &&
    typeof value.project_id === "string" && isPseudonym(value.project_id) &&
    typeof value.session_id === "string" && isPseudonym(value.session_id) &&
    safeNullableLabel(value.project_display_name, 120) &&
    safeNullableLabel(value.session_display_name, 160) &&
    origins.has(value.project_display_name_origin as string) &&
    origins.has(value.session_display_name_origin as string) &&
    Number.isSafeInteger(value.project_manual_label_revision) &&
    (value.project_manual_label_revision as number) >= 0 &&
    Number.isSafeInteger(value.session_manual_label_revision) &&
    (value.session_manual_label_revision as number) >= 0 &&
    safeNullableVersion(value.provider_version) &&
    typeof value.adapter_version === "string" && SAFE_VERSION.test(value.adapter_version) &&
    safeNullableVersion(value.source_schema_version) &&
    safeDate(value.started_at) && safeDate(value.ended_at, true) &&
    (value.terminal_state === null || SESSION_STATES.has(value.terminal_state as string)) &&
    typeof value.events_complete === "boolean"
  );
}

export function parseSessionCatalogPage(value: unknown, expectedOffset: number): CodexSession[] | null {
  if (
    !isRecord(value) || !hasExactKeys(value, ["sessions", "limit", "offset"]) ||
    value.limit !== SESSION_CATALOG_PAGE_SIZE || value.offset !== expectedOffset ||
    !Array.isArray(value.sessions) || value.sessions.length > SESSION_CATALOG_PAGE_SIZE ||
    !value.sessions.every(safeSessionCatalogRow)
  ) return null;
  return value.sessions;
}
