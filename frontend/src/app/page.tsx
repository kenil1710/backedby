import { Board } from "@/components/Board";

export default function Home() {
  return (
    <>
      <section className="pt-12 pb-8 sm:pt-16">
        <h1 className="wide max-w-3xl text-[34px] font-semibold leading-[1.08] tracking-tight sm:text-[46px]">
          Locked on Ethereum, minted elsewhere. Does one still cover the other?
        </h1>
        <p className="mt-4 max-w-2xl text-[16px] leading-relaxed text-ink-2">
          For each bridge below, every validator reads the vault&apos;s balance and the destination token&apos;s supply at the
          same pinned, finalized blocks, from two independent RPCs per chain, and they must agree. The contract does the
          arithmetic and gives the verdict. Operators can bond that a pair stays backed; anyone can challenge them.
        </p>
      </section>
      <Board />
    </>
  );
}
