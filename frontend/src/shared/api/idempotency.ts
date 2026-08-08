export type IdempotentAction = "accept" | "reject" | "merge" | "split" | "analysis";

/** A content-free, collision-resistant key generated only for a local command. */
export function nextIdempotencyKey(action: IdempotentAction): string {
  return `dashboard-${action}-${globalThis.crypto.randomUUID()}`;
}
