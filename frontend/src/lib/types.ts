// Shapes returned by the BackedBy contracts' views (see contracts/*.py).
export type Verdict = "BACKED" | "UNDER_BACKED" | "INCONCLUSIVE";
export type CheckStatus = "OPEN" | "PROVISIONAL" | "CONTESTED" | "FINAL" | "INCONCLUSIVE";

export interface Dest { chain: string; token: string; decimals: number; kind?: string; deposits_vault?: string; vault?: string; remote?: string; auth_id: number; added_by: string; added_at: number }
export interface Vault { vault: string; kind: string; family?: string; remotes?: string[]; auth_id: number; added_by: string; added_at: number }

export interface Coverage {
  state: "COMPLETE" | "GAP" | "UNREAD" | "OPEN";
  unlisted: { vault: string; id: string }[];
  by_vault: { vault: string; family: string; state: string; unlisted: string[] }[];
}
export interface PorCompare {
  status: "MATCH" | "DIFF" | "STALE" | "UNREAD"; por_ratio_bps: number; delta_bps: number; explain: string; age_s?: number;
  feed?: string; reserves?: string; reserves_decimals?: number; supply?: string; supply_decimals?: number;
}
export interface HistoryPoint {
  check_id: number; purpose: string; source_time: number; final_at: number; verdict: Verdict; ratio_bps: number;
  locked_norm: string; supply_norm: string; scale_decimals: number; alert: string; coverage: string; unlisted: number;
  por: string; por_ratio_bps: number; blocks: Record<string, number>;
}
export type Anchor = [string, string, string, string];

export interface Ruling {
  verdict: Verdict; reason: string; cls: string; source_time: number; locked_norm: string; supply_norm: string;
  ratio_bps: number; scale_decimals: number; counted: string[];
  ledgers?: Record<string, { ledger_norm: string; listed_norm: string; counted_norm: string }>;
  coverage?: Coverage | null; alert?: string; por?: PorCompare | null;
}

export interface Check {
  found?: boolean; check_id: number; pair_id: number; purpose: "CHALLENGE" | "MONITOR"; bond_id: number; filer: string;
  stake: string; blocks: Record<string, number>; vaults: string[]; max_gap_s: number;
  dests: { chain: string; token: string; decimals: number }[];
  filed_at: number; read_deadline: number; status: CheckStatus; round: number; verdict1: string; ruling1: Ruling | null;
  ruled_at: number; contest_deadline: number; contester: string; contest_stake: string; contested_at: number;
  contest_read_deadline: number; ruling2: Ruling | null; verdict: string; reason: string; how: string; final_at: number;
  source_time: number; payouts: Record<string, string> | null;
}

export interface Pair {
  found?: boolean; pair_id: number; key: string; kind: string; source_chain: string; vault: string; vaults: Vault[]; source_token: string;
  source_decimals: number; tolerance_bps: number; max_gap_s: number; label: string; dests: Dest[]; anchors: Anchor[];
  registered_by: string; registered_at: number; last_bad_time: number; open_check: number; latest_check: number;
  latest_time: number; last_monitor_at: number; checks: number[]; bonds: number[]; history_points?: number;
  latest?: Check | null; open?: Check | null;
}

export interface Bond {
  found?: boolean; bond_id: number; pair_id: number; operator: string; amount: string; deposited: string; won: string;
  slashed: string; since: number; unbond_at: number; withdrawable_at: number; status: string; open_check: number;
  closed_at: number;
}

export interface Reading {
  found: boolean; key?: string; round?: number; request_sha?: string; status?: string; reason?: string; read_at?: number;
  reader?: string;
  reading?: {
    status: string; reason: string; locked_by_vault: string[]; source_decimals: number; anchors: string[];
    blocks: Record<string, { number: number; hash: string; timestamp: number }>;
    dests: { chain: string; token: string; supply: string; decimals: number; deposits: string }[];
    ledgers?: Record<string, string>;
    coverage?: { vault: string; family: string; ids: number[]; error: string }[];
    por?: Record<string, unknown> | null;
  };
}

export interface Ledger {
  received: string; bonds: string; open_stakes: string; claimable: string; claimed: string; held_now: string;
  invariant_holds: boolean; bonds_recomputed_match: boolean; open_recomputed_match: boolean; slashed: string;
  bounties: string; on_chain_balance: string;
}

export interface RegistryConfig {
  version: string; mode: string; reader: string; treasury: string; window_s: number; read_timeout_s: number;
  contest_timeout_s: number; unbond_delay_s: number; monitor_interval_s: number; min_stake: string; min_bond: string;
  auth_max_age_s: number; max_gap_s: number; fast_gap_s: number; kind_max_gap_s: Record<string, number>; max_tolerance_bps: number;
  bounty_bps: number; kinds: Record<string, string>; deposit_kinds: string[]; data_reasons: string[];
  alert_margin_bps?: number; por_max_age_s?: number; por_match_bps?: number; families?: Record<string, string>;
}

export interface Stats { pairs: number; bonds: number; checks: number; counts: Record<string, number> }

export interface GateAnswer {
  backed: boolean; state: string; reason: string; check_id?: number; verdict?: string; source_time?: number; age_s?: number;
  ratio_bps?: number; alert?: string; coverage?: string; unlisted?: number; por?: string; pair_id?: number;
  max_age_s: number; max_tolerance_bps: number;
}

export type TxPhase = "signing" | "submitted" | "accepted" | "finalized" | "failed" | "rejected";
export interface TxProgress { phase: TxPhase; hash: string | null; message: string }
export type WriteResult<T> =
  | { kind: "ok"; hash: string; data: T }
  | { kind: "rejected"; hash: string; reason: string }
  | { kind: "failed"; hash: string | null; error: string };
