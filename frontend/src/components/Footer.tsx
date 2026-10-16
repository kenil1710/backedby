import Link from "next/link";
import { COMMIT } from "@/lib/deployments";

export function Footer() {
  return (
    <footer className="border-t border-seam">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-6 text-[13px] text-ink-3 sm:px-6">
        <span>BackedBy on GenLayer Studio Dev. Every number on this site is read from the contracts.</span>
        <Link href="/verify" className="hover:text-ink-2">Source <span className="num">{COMMIT.slice(0, 7)}</span></Link>
        <a href="https://github.com/kenil1710/backedby" className="hover:text-ink-2">GitHub</a>
        <Link href="/api/backed?pair=1" className="hover:text-ink-2">JSON API</Link>
      </div>
    </footer>
  );
}
