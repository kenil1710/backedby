"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { useWallet } from "./WalletProvider";
import { getDeployment, setDeployment, type Deployment } from "@/lib/genlayer";
import { formatGen, shortAddress } from "@/lib/format";

const NAV = [
  { href: "/", label: "Board" },
  { href: "/collateral", label: "Collateral" },
  { href: "/bond", label: "Bond" },
  { href: "/challenge", label: "Challenge" },
  { href: "/verify", label: "Verify" },
  { href: "/docs", label: "Rules" },
];

/** Two pylons and a deck: the mark is the board's own graphic. */
export function Mark({ className = "h-6 w-9" }: { className?: string }) {
  return (
    <svg viewBox="0 0 36 24" className={className} aria-hidden="true">
      <rect x="2" y="4" width="4" height="18" rx="1" fill="var(--color-steel)" />
      <rect x="30" y="4" width="4" height="18" rx="1" fill="var(--color-steel)" />
      <rect x="2" y="9" width="32" height="4" rx="1" fill="var(--color-steel-deep)" />
      <rect x="2" y="9" width="24" height="4" rx="1" fill="var(--color-backed)" />
      <rect x="25.5" y="6" width="1.5" height="10" fill="var(--color-ink)" />
    </svg>
  );
}

export function Header() {
  const path = usePathname();
  const w = useWallet();
  const [dep, setDep] = useState<Deployment>("canonical");
  const [open, setOpen] = useState(false);
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => setDep(getDeployment()), []);
  const flip = () => { setDeployment(dep === "demo" ? "canonical" : "demo"); window.location.reload(); };
  return (
    <header className="border-b border-seam bg-ground/95 backdrop-blur supports-[backdrop-filter]:bg-ground/80 sticky top-0 z-40">
      <div className="mx-auto flex max-w-6xl items-center gap-4 px-4 py-3 sm:px-6">
        <Link href="/" className="flex items-center gap-2.5" aria-label="BackedBy home">
          <Mark />
          <span className="wide hidden text-[17px] font-semibold tracking-tight min-[360px]:inline">BackedBy</span>
        </Link>
        <nav className="ml-4 hidden gap-1 md:flex" aria-label="Main">
          {NAV.map((n) => {
            const on = n.href === "/" ? path === "/" : path.startsWith(n.href);
            return (
              <Link key={n.href} href={n.href}
                className={`rounded px-2.5 py-1.5 text-[14px] ${on ? "bg-plate-2 text-ink" : "text-ink-2 hover:text-ink"}`}>{n.label}</Link>
            );
          })}
        </nav>
        <div className="ml-auto flex min-w-0 items-center gap-2">
          <button type="button" onClick={flip} title="Switch between the canonical registry (6 h contest window, real seeds) and the demo registry (90 s)"
            className={`hidden rounded border px-2.5 py-1.5 text-[13px] sm:inline-block ${dep === "demo" ? "border-inconc/60 text-inconc" : "border-seam text-ink-2 hover:text-ink"}`}>
            {dep === "demo" ? "Demo registry" : "Canonical"}
          </button>
          {w.account ? (
            <button type="button" onClick={w.disconnect} className="num rounded border border-seam px-2.5 py-1.5 text-[12.5px] text-ink-2 hover:text-ink"
              title="Disconnect">
              {shortAddress(w.account)}{w.balance !== null ? ` · ${formatGen(w.balance, 2)} GEN` : ""}
            </button>
          ) : (
            <button type="button" onClick={() => void w.connect()} disabled={w.connecting}
              className="rounded bg-steel px-3 py-1.5 text-[13px] font-medium text-ground hover:bg-ink disabled:opacity-60">
              {w.connecting ? "Connecting" : <>Connect<span className="hidden sm:inline"> wallet</span></>}
            </button>
          )}
          <button type="button" className="rounded border border-seam px-2 py-1.5 text-[13px] text-ink-2 md:hidden" aria-expanded={open}
            aria-controls="mobile-nav" onClick={() => setOpen(!open)}>Menu</button>
        </div>
      </div>
      {w.onWrongNetwork && (
        <div className="border-t border-inconc/40 bg-inconc/10 px-4 py-2 text-center text-[13px] text-inconc">
          Your wallet is on another network. <button className="underline" onClick={() => void w.switchNetwork()}>Switch to GenLayer Studio Dev</button>
        </div>
      )}
      {open && (
        <nav id="mobile-nav" className="border-t border-seam px-4 py-2 md:hidden" aria-label="Main">
          {NAV.map((n) => (
            <Link key={n.href} href={n.href} onClick={() => setOpen(false)} className="block py-2 text-[15px] text-ink-2 hover:text-ink">{n.label}</Link>
          ))}
          <button type="button" onClick={flip} className="block py-2 text-left text-[15px] text-ink-2 hover:text-ink">
            Switch to the {dep === "demo" ? "canonical" : "demo"} registry
          </button>
        </nav>
      )}
    </header>
  );
}
