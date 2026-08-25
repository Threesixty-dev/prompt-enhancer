export const NATIVE_FOLDER_PICKER_VERSION = "native-folder-picker-v1" as const;

type NativeDesktopApi = {
  choose_workspace_folder?: () => Promise<unknown>;
  confirm_user_presence?: (request: unknown) => Promise<unknown>;
};

type NativeDesktopHost = typeof globalThis & {
  pywebview?: {
    api?: NativeDesktopApi;
  };
};

export type NativeWorkspaceFolderPick =
  | { status: "selected"; path: string }
  | { status: "cancelled" }
  | { status: "unavailable" };

export class NativeFolderPickerError extends Error {
  readonly code: "bridge_failed" | "invalid_response";

  constructor(code: "bridge_failed" | "invalid_response") {
    super(code === "bridge_failed"
      ? "Native folder picker failed"
      : "Native folder picker response was invalid");
    this.name = "NativeFolderPickerError";
    this.code = code;
  }
}

function nativeDesktopApi(): NativeDesktopApi | undefined {
  return (globalThis as NativeDesktopHost).pywebview?.api;
}

function hasExactKeys(value: Record<string, unknown>, keys: readonly string[]): boolean {
  return Object.keys(value).sort().join(",") === [...keys].sort().join(",");
}

function isAbsoluteWorkspacePath(value: string): boolean {
  if (value.length === 0 || value.length > 1024 || value !== value.trim() || /[\u0000-\u001f\u007f]/u.test(value)) {
    return false;
  }
  return /^[A-Za-z]:[\\/]/u.test(value)
    || /^\\\\[^\\/]+[\\/][^\\/]+/u.test(value)
    || /^\/(?!\/)/u.test(value);
}

export function hasNativeWorkspaceFolderPicker(): boolean {
  return typeof nativeDesktopApi()?.choose_workspace_folder === "function";
}

export function hasNativeUserPresenceBridge(): boolean {
  return typeof nativeDesktopApi()?.confirm_user_presence === "function";
}

/**
 * Ask the owned native host for one directory path. The bridge returns no file
 * contents or directory listing; every response is parsed as one exact tuple.
 */
export async function chooseNativeWorkspaceFolder(): Promise<NativeWorkspaceFolderPick> {
  const api = nativeDesktopApi();
  const choose = api?.choose_workspace_folder;
  if (typeof choose !== "function") return { status: "unavailable" };

  let value: unknown;
  try {
    value = await choose.call(api);
  } catch {
    throw new NativeFolderPickerError("bridge_failed");
  }

  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new NativeFolderPickerError("invalid_response");
  }
  const record = value as Record<string, unknown>;
  if (record.version !== NATIVE_FOLDER_PICKER_VERSION || typeof record.status !== "string") {
    throw new NativeFolderPickerError("invalid_response");
  }
  if (record.status === "selected") {
    if (
      !hasExactKeys(record, ["path", "status", "version"])
      || typeof record.path !== "string"
      || !isAbsoluteWorkspacePath(record.path)
    ) {
      throw new NativeFolderPickerError("invalid_response");
    }
    return { status: "selected", path: record.path };
  }
  if (
    (record.status === "cancelled" || record.status === "unavailable")
    && hasExactKeys(record, ["status", "version"])
  ) {
    return { status: record.status };
  }
  throw new NativeFolderPickerError("invalid_response");
}
