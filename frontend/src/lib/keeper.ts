// The keeper's status (status.json on the keeper-state branch), read through
// the site's cached /api/keeper.
import useSWR from "swr";

export interface KeeperAction { key: string; kind: string; pair_id?: number; status: string; result: string; tx: string; attempts: number; last_error: string }
export interface KeeperContract {
  address: string;
  last_run: Record<string, number | string | string[] | null>;
  totals: { actions: number; done: number; queued: number; pending: number; retry: number; failed: number; by_kind: Record<string, number> };
  pairs: Record<string, { label?: string; waiting?: string }>;
  unmatched: Record<string, Record<string, { remote: string; why: string; at: number }>>;
  unprocessed: { key: string; why: string }[];
  actions: KeeperAction[];
}
export interface KeeperStatus {
  keeper: string; started_at: string; finished_at: string; trigger: string; run_url: string;
  contracts: Record<string, KeeperContract>;
  history: { started_at: string; finished_at: string; trigger: string; run_url: string; runs: Record<string, { submitted: number; done: number; pages: number; pages_failed: number }> }[];
}

export function useKeeper() {
  const { data } = useSWR("keeper-status", async () => {
    const r = await fetch("/api/keeper");
    const j = await r.json();
    if (!r.ok || j.error) throw new Error(j.error ?? "keeper status unreadable");
    return j as KeeperStatus;
  }, { refreshInterval: 120_000, shouldRetryOnError: true, errorRetryInterval: 30_000 });
  if (!data) return null;
  return {
    status: data,
    unmatchedFor(registry: string, pairId: number) {
      const c = Object.values(data.contracts).find((x) => x.address.toLowerCase() === registry.toLowerCase());
      return c?.unmatched?.[String(pairId)];
    },
  };
}
