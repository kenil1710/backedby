"use client";

import useSWR from "swr";
import { getConfig, getGateConfig, getReaderConfig } from "@/lib/contract";
import { ADDR } from "@/lib/deployments";
import { CHAIN_NAME, KIND_NAME } from "@/lib/chains";
import { durationText, formatGen } from "@/lib/format";
import { Ext, Panel } from "@/components/ui";

const H = ({ children }: { children: React.ReactNode }) => <h2 className="wide mt-10 text-[21px] font-semibold tracking-tight">{children}</h2>;
const P = ({ children }: { children: React.ReactNode }) => <p className="mt-3 max-w-3xl text-[15px] leading-relaxed text-ink-2">{children}</p>;
const Code = ({ children }: { children: React.ReactNode }) => <code className="num rounded bg-plate-2 px-1.5 py-0.5 text-[13px] text-ink">{children}</code>;

export default function Docs() {
  const canon = useSWR(["cfg", ADDR.registry], () => getConfig(ADDR.registry)).data;
  const demo = useSWR(["cfg", ADDR.registryDemo], () => getConfig(ADDR.registryDemo)).data;
  const reader = useSWR("reader-cfg", () => getReaderConfig()).data as undefined | { chains: Record<string, { chain_id: number; rpcs: string[] }>; arbitrum_escrow_gateways: Record<string, string> };
  const gate = useSWR(["gcfg", ADDR.gate], () => getGateConfig(ADDR.gate)).data;
  const gateDemo = useSWR(["gcfg", ADDR.gateDemo], () => getGateConfig(ADDR.gateDemo)).data;
  const rows: [string, (c: NonNullable<typeof canon>) => string][] = [
    ["Contest window", (c) => durationText(c.window_s)],
    ["Read deadline after filing", (c) => durationText(c.read_timeout_s)],
    ["Re-read deadline after a contest", (c) => durationText(c.contest_timeout_s)],
    ["Unbond delay", (c) => durationText(c.unbond_delay_s)],
    ["Ruled monitoring checks, at most one per pair per", (c) => durationText(c.monitor_interval_s)],
    ["Minimum stake (challenge, contest)", (c) => `${formatGen(c.min_stake, 3)} GEN`],
    ["Minimum bond", (c) => `${formatGen(c.min_bond, 3)} GEN`],
    ["Max gap between pinned blocks", (c) => `${c.max_gap_s} s (Polygon ${c.kind_max_gap_s.polygon} s, fast bridges ${c.fast_gap_s} s)`],
    ["Max tolerance a pair can freeze", (c) => `${c.max_tolerance_bps} bps`],
    ["Challenger's share of a slash", (c) => `${c.bounty_bps / 100}% (rest to the treasury)`],
    ["Authentication must be fresher than", (c) => durationText(c.auth_max_age_s)],
  ];
  return (
    <div className="pt-10 pb-10">
      <h1 className="wide text-[30px] font-semibold tracking-tight">The rules, as the code runs them</h1>
      <P>Every number below is read live from the deployed contracts&apos; <Code>get_config</Code>. No model is asked anything, at any step:
        validators read chain data over JSON-RPC and must agree on it, and the contract does the arithmetic.</P>

      <Panel className="mt-6" title="Parameters" aside="canonical and demo registries">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[30rem] text-[14px]">
            <thead><tr className="text-left text-ink-3"><th className="py-1.5 font-normal">Rule</th><th className="font-normal">Canonical</th><th className="font-normal">Demo</th></tr></thead>
            <tbody>
              {rows.map(([k, f]) => (
                <tr key={k} className="border-t border-seam/60"><td className="py-2 pr-4 text-ink-2">{k}</td>
                  <td className="num pr-4">{canon ? f(canon) : "-"}</td><td className="num">{demo ? f(demo) : "-"}</td></tr>
              ))}
              <tr className="border-t border-seam/60"><td className="py-2 pr-4 text-ink-2">CollateralGate max age / max tolerance</td>
                <td className="num pr-4">{gate ? `${durationText(gate.max_age_s)} / ${gate.max_tolerance_bps} bps` : "-"}</td>
                <td className="num">{gateDemo ? `${durationText(gateDemo.max_age_s)} / ${gateDemo.max_tolerance_bps} bps` : "-"}</td></tr>
            </tbody>
          </table>
        </div>
      </Panel>

      <H>1. A pair exists only if the bridge says so</H>
      <P>A pair is one source token on Ethereum, the vaults there that hold it (their balances are summed), and the destination
        tokens minted against them (their supplies are summed). ChainReader proves every vault and every destination from the
        bridge&apos;s own mapping, read on both chains from both RPCs, before anything is recorded. Anything else is refused.</P>
      <ul className="mt-3 max-w-3xl list-disc space-y-1.5 pl-5 text-[14.5px] text-ink-2">
        <li><b className="text-ink">{KIND_NAME.arbitrum}</b>: L1GatewayRouter <Code>getGateway</Code> and <Code>calculateL2TokenAddress</Code>, and the L2 router must agree; the gateway must be one of the escrow gateways{reader ? ` (${Object.values(reader.arbitrum_escrow_gateways).join(", ")})` : ""}; the vault is the gateway, or its <Code>l1Escrow()</Code>.</li>
        <li><b className="text-ink">{KIND_NAME.optimism}, {KIND_NAME.base}</b>: the L2 token&apos;s <Code>remoteToken()</Code> is the source token and its <Code>bridge()</Code> is <Code>0x4200…0010</Code>; the vault is that chain&apos;s L1StandardBridge. It counts as the larger of its supply and the bridge&apos;s own ledger <Code>deposits(l1, l2)</Code>, so neither unpaid withdrawals nor tokens minted outside the bridge can hide.</li>
        <li><b className="text-ink">{KIND_NAME.op_dai}</b>: the L1 and L2 DAI bridges name the same tokens and each other; the vault is <Code>escrow()</Code>.</li>
        <li><b className="text-ink">{KIND_NAME.polygon}</b>: RootChainManager <Code>rootToChildToken</Code>, ChildChainManager <Code>childToRootToken</Code> pointing back, type ERC20; the vault is the ERC20 predicate.</li>
        <li><b className="text-ink">LayerZero OFT</b> (for example USDT0): the destination token&apos;s <Code>oftContract()</Code> has the Ethereum adapter as its peer and the adapter&apos;s <Code>token()</Code> is the source token, its peer for that chain is the same OFT, both on the LayerZero endpoint. The vault is that adapter, derived from the token, never supplied.</li>
        <li><b className="text-ink">{KIND_NAME.nomad}</b>: the Moonbeam TokenRegistry maps the representation to the Ethereum token both ways, the Moonbeam router&apos;s remote for Ethereum is the Ethereum BridgeRouter (the vault), and the token is local on Ethereum.</li>
      </ul>
      <P>Anyone can add a destination or a vault a pair is missing, with the same proof, so an operator cannot hide supply by leaving
        a token out, and a token with a second mint path (Polygon&apos;s USDT, minted by the PoS bridge and by USDT0) is judged against
        every vault that backs it. A check uses the vaults and destinations the pair had when it was filed.
        Each authentication also records its mapping calls and answers; every check re-reads them at its own blocks, and any change is
        INCONCLUSIVE rather than a slash. Tolerance is frozen per pair at registration and is part of the pair&apos;s identity, so anyone
        can register a stricter variant.</P>

      <H>2. One finalized block per chain, source last</H>
      <P>A check pins a block on Ethereum and on each destination chain. Both must be at or below the finalized block on both RPCs.
        The Ethereum (locked) block&apos;s timestamp must be at or after every destination block&apos;s, and at most the pair&apos;s max gap later
        than the oldest (120 s once a pair holds a fast-bridge vault). With that order, a deposit is always locked before it is minted, so one in flight shows up on the locked side
        only; a withdrawal is burned before it is released, and every supported bridge takes longer than the gap to release, so one in
        flight shows up as removed from supply only. In-flight transfers can only ever look over-backed, never under.</P>

      <H>3. Two RPCs per chain, or INCONCLUSIVE</H>
      <P>Every value is read from both RPCs of its chain, and the fields used must be identical. A disagreement, an error, a missing
        block, a decimals value different from the one frozen at registration, or a changed bridge mapping makes the check INCONCLUSIVE:
        every stake is refunded and nobody is slashed.</P>
      {reader && (
        <ul className="mt-3 grid max-w-3xl gap-1 text-[13.5px] text-ink-2 sm:grid-cols-2">
          {Object.entries(reader.chains).map(([c, v]) => (
            <li key={c}><span className="text-ink">{CHAIN_NAME[c] ?? c}</span>: <span className="num">{v.rpcs.map((u) => u.replace("https://", "")).join(" + ")}</span></li>
          ))}
        </ul>
      )}

      <H>4. The verdict is arithmetic</H>
      <P>Both sides are scaled to the larger of their decimals, exactly, in integers. <Code>BACKED</Code> if
        <Code>locked × 10000 ≥ supply × (10000 − tolerance_bps)</Code>, otherwise <Code>UNDER_BACKED</Code>.</P>

      <H>5. Bonds and challenges</H>
      <P>An operator bonds that a pair stays BACKED from the moment of bonding until they request to unbond. Anyone (not the operator)
        challenges with a stake at blocks inside that span. Final UNDER_BACKED: the whole bond is slashed, the challenger gets the
        stake back plus half of it, the treasury the other half. Final BACKED: the stake goes into the operator&apos;s bond.
        INCONCLUSIVE: refunded. Only one check is open on a pair at a time; a challenge replaces an open monitoring check. A bond
        cannot be withdrawn while a check on it is open, and payouts are claimed, never pushed.</P>

      <H>6. Provisional, contestable, final</H>
      <P>A ruling is PROVISIONAL when made and contestable for the window. A contest stakes the minimum and has the same pinned
        blocks read again: the same verdict makes it FINAL and the contest stake goes to the side the ruling favoured; a different one
        makes it INCONCLUSIVE and refunds everyone. With no contest, anyone finalizes once the window passes. Every open state has a
        deadline and a public exit: an unread check expires as INCONCLUSIVE, an unread contest leaves the first ruling standing.</P>

      <H>7. Monitoring and the gate</H>
      <P>Monitoring checks cost no stake and are rate limited: one ruled check per pair per interval. The patrol bot files one for each
        canonical pair every six hours, reads and rules any check it finds open, and finalizes expired windows. CollateralGate says yes
        only for a pair whose latest ruling is FINAL and BACKED, pinned within its max age, with no other ruling inside that age, and a
        tolerance within its limit.</P>
      <P>Source: <Ext href="https://github.com/kenil1710/backedby/tree/main/contracts">contracts/</Ext> and{" "}
        <Ext href="https://github.com/kenil1710/backedby/blob/main/docs/RULES.md">docs/RULES.md</Ext>.</P>
    </div>
  );
}
