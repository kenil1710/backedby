import LABELS from "./labels.json";

const map = LABELS as unknown as Record<string, Record<string, string>>;

/** The pair's display name: an entry in labels.json, else the label stored on chain. */
export function displayLabel(registry: string, pairId: number, stored: string): string {
  return map[registry.toLowerCase()]?.[String(pairId)] ?? stored;
}

export function withDisplayLabel<T extends { pair_id: number; label: string }>(p: T, registry: string): T {
  return p && p.pair_id ? { ...p, label: displayLabel(registry, p.pair_id, p.label) } : p;
}
