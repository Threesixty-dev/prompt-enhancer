export type RuntimeDataMode = "synthetic" | "local";

export function resolveRuntimeDataMode({
  development,
  viteMode,
}: {
  development: boolean;
  viteMode: string;
}): RuntimeDataMode {
  if (development && viteMode !== "real") return "synthetic";
  return "local";
}
