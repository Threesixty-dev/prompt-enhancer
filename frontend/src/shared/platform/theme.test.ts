import { describe, expect, it } from "vitest";
import { DEFAULT_THEME, THEME_STORAGE_KEY, applyTheme, persistTheme, readStoredTheme } from "./theme";

function memoryStorage(initial: Record<string, string> = {}) {
  const store = new Map(Object.entries(initial));
  return {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => { store.set(key, value); },
    store,
  };
}

describe("theme", () => {
  it("defaults to dark and only accepts known names", () => {
    expect(DEFAULT_THEME).toBe("dark");
    expect(readStoredTheme(memoryStorage())).toBe("dark");
    expect(readStoredTheme(memoryStorage({ [THEME_STORAGE_KEY]: "light" }))).toBe("light");
    expect(readStoredTheme(memoryStorage({ [THEME_STORAGE_KEY]: "neon" }))).toBe("dark");
    expect(readStoredTheme(null)).toBe("dark");
  });

  it("stamps the root element and persists the choice", () => {
    const root = document.createElement("html");
    applyTheme("light", root);
    expect(root.getAttribute("data-theme")).toBe("light");
    expect(root.style.colorScheme).toBe("light");
    applyTheme("dark", root);
    expect(root.getAttribute("data-theme")).toBe("dark");
    const storage = memoryStorage();
    persistTheme("light", storage);
    expect(storage.store.get(THEME_STORAGE_KEY)).toBe("light");
    expect(() => persistTheme("dark", { setItem: () => { throw new Error("full"); } })).not.toThrow();
  });
});
