import { afterEach, describe, expect, it, vi } from "vitest";
import {
  chooseNativeWorkspaceFolder,
  hasNativeUserPresenceBridge,
  hasNativeWorkspaceFolderPicker,
} from "./nativeDesktopBridge";

const originalPywebview = Object.getOwnPropertyDescriptor(globalThis, "pywebview");

function installBridge(api: Record<string, unknown>): void {
  Object.defineProperty(globalThis, "pywebview", {
    configurable: true,
    value: { api },
  });
}

afterEach(() => {
  vi.restoreAllMocks();
  if (originalPywebview) Object.defineProperty(globalThis, "pywebview", originalPywebview);
  else Reflect.deleteProperty(globalThis, "pywebview");
});

describe("native desktop bridge", () => {
  it("reports an absent bridge without invoking anything", async () => {
    Reflect.deleteProperty(globalThis, "pywebview");

    expect(hasNativeWorkspaceFolderPicker()).toBe(false);
    expect(hasNativeUserPresenceBridge()).toBe(false);
    await expect(chooseNativeWorkspaceFolder()).resolves.toEqual({ status: "unavailable" });
  });

  it("accepts only an exact selected absolute-path tuple", async () => {
    const choose = vi.fn().mockResolvedValue({
      version: "native-folder-picker-v1",
      status: "selected",
      path: "D:\\example\\workspace",
    });
    installBridge({ choose_workspace_folder: choose, confirm_user_presence: vi.fn() });

    expect(hasNativeWorkspaceFolderPicker()).toBe(true);
    expect(hasNativeUserPresenceBridge()).toBe(true);
    await expect(chooseNativeWorkspaceFolder()).resolves.toEqual({
      status: "selected",
      path: "D:\\example\\workspace",
    });
    expect(choose).toHaveBeenCalledOnce();
  });

  it.each(["cancelled", "unavailable"] as const)("accepts the exact %s tuple", async (status) => {
    installBridge({
      choose_workspace_folder: vi.fn().mockResolvedValue({
        version: "native-folder-picker-v1",
        status,
      }),
    });

    await expect(chooseNativeWorkspaceFolder()).resolves.toEqual({ status });
  });

  it.each([
    null,
    { version: "native-folder-picker-v2", status: "cancelled" },
    { version: "native-folder-picker-v1", status: "selected", path: "example\\workspace" },
    { version: "native-folder-picker-v1", status: "selected", path: "D:\\example", extra: true },
    { version: "native-folder-picker-v1", status: "cancelled", path: "D:\\example" },
  ])("rejects malformed or over-broad picker output", async (value) => {
    installBridge({ choose_workspace_folder: vi.fn().mockResolvedValue(value) });

    await expect(chooseNativeWorkspaceFolder()).rejects.toMatchObject({
      name: "NativeFolderPickerError",
      code: "invalid_response",
    });
  });

  it("collapses a native exception to a content-free bridge error", async () => {
    installBridge({ choose_workspace_folder: vi.fn().mockRejectedValue(new Error("private native detail")) });

    await expect(chooseNativeWorkspaceFolder()).rejects.toMatchObject({
      name: "NativeFolderPickerError",
      code: "bridge_failed",
    });
  });
});
