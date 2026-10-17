// node --test test/payout.test.mjs: the payout fee guard and the delivery check,
// on the shapes Studio Dev returned for a skipped internal transfer (demo claim
// 0x71e5cc09…) and a delivered external one (probe 0xc463d49e…).
import test from "node:test";
import assert from "node:assert/strict";
import { payoutFeesProblem, externalAllocation, manualAllocation, payoutDelivered, checkBalances, payoutFees, EXTERNAL } from "../tools/lib/payout.mjs";

const PAYEE = "0xF873CDD4bA6e2cA7BB1Ef5ACb38eB7Cd3e3F2515";
const ext = { messageType: 0, recipient: PAYEE.toLowerCase(), budget: 150000000000000n, feeParams: "0x", onAcceptance: false };
const fees = (allocs, total = 150000000000000n, value = 759792000010352n) =>
  ({ distribution: { totalMessageFees: total }, messageAllocations: allocs, feeValue: value });

test("an External allocation for the payee funds the payout", () => {
  assert.equal(payoutFeesProblem(fees([ext]), PAYEE), "");
  assert.equal(externalAllocation(fees([ext]), PAYEE.toLowerCase()), ext);
});

test("an Internal allocation (what emit_transfer used) does not", () => {
  assert.match(payoutFeesProblem(fees([{ ...ext, messageType: 1 }]), PAYEE), /no External/);
});

test("an allocation for someone else does not", () => {
  assert.match(payoutFeesProblem(fees([{ ...ext, recipient: "0x" + "1".repeat(40) }]), PAYEE), /no External/);
});

test("a zero budget or no allocations does not", () => {
  assert.match(payoutFeesProblem(fees([{ ...ext, budget: 0n }]), PAYEE), /no External/);
  assert.match(payoutFeesProblem(fees(undefined), PAYEE), /no External/);
});

test("the distribution must carry the budget", () => {
  assert.match(payoutFeesProblem(fees([ext], 1n), PAYEE), /totalMessageFees/);
  assert.match(payoutFeesProblem(fees([ext], 150000000000000n, 1n), PAYEE), /feeValue/);
});

test("manual allocation: Studio's default gas limit at the given price", () => {
  const a = manualAllocation(PAYEE, 300000000n);
  assert.equal(a.messageType, EXTERNAL);
  assert.equal(a.budget, 150000000000000n);
  assert.equal(a.feeParams.length, 2 + 128);
});

test("payoutFees falls back to a manual allocation, and refuses if still unfunded", async () => {
  const seen = [];
  const wallet = {
    estimateTransactionFeesForWrite: async () => ({ ...fees([{ ...ext, messageType: 1 }]), policy: { receiptGasPrice: 250000000n } }),
    estimateTransactionFees: async ({ messageAllocations }) => { seen.push(messageAllocations); return fees(messageAllocations); },
  };
  const f = await payoutFees(wallet, { address: "0x" + "2".repeat(40), payee: PAYEE });
  assert.equal(seen[0][0].budget, 150000000000000n);
  assert.equal(payoutFeesProblem(f, PAYEE), "");
  const broke = { ...wallet, estimateTransactionFees: async () => fees([]) };
  await assert.rejects(payoutFees(broke, { address: "0x" + "2".repeat(40), payee: PAYEE }), /payout not funded/);
});

const delivered = {
  statusName: "FINALIZED",
  messages: [{ messageType: "0", recipient: PAYEE, value: "10000000000000000", data: "" }],
  data: { fee_accounting: {
    message_value_effects: { k1: { phase: "finalized", value: "10000000000000000", include: true, declaredBudget: 0 } },
    message_effect_delivered: { k1: true }, paid_fee_value: "759792000010352", total_refunded: "508488000009529" } },
};
const skipped = {
  statusName: "FINALIZED",
  messages: [{ messageType: "0", recipient: PAYEE, value: "70000000000000000", data: "Bg==" }],
  data: { fee_accounting: {
    message_value_effects: { k2: { phase: "finalized", value: "70000000000000000", include: true, skipped: true, declaredBudget: 0, skippedRefunded: true } },
    message_effect_delivered: { k2: true } } },
};

test("a delivered external send passes, with the sender's net fee", () => {
  const r = payoutDelivered(delivered, PAYEE.toLowerCase(), 10n ** 16n);
  assert.equal(r.ok, true);
  assert.equal(r.netFee, 759792000010352n - 508488000009529n);
});

test("the external send's unused gas comes back to the sender and is not a fee", () => {
  const tx = structuredClone(delivered);
  tx.data.fee_accounting.external_message_fee_payouts = [{ amount: "125000000000000", source: "external-execution-remainder", recipient: PAYEE }];
  assert.equal(payoutDelivered(tx, PAYEE, 10n ** 16n).netFee, 759792000010352n - 508488000009529n - 125000000000000n);
  tx.data.fee_accounting.external_message_fee_payouts[0].recipient = "0x" + "4".repeat(40);
  assert.equal(payoutDelivered(tx, PAYEE, 10n ** 16n).netFee, 759792000010352n - 508488000009529n);
});

test("a skipped transfer fails even though 'delivered' is true", () => {
  const r = payoutDelivered(skipped, PAYEE, 7n * 10n ** 16n);
  assert.equal(r.ok, false);
  assert.match(r.why, /skipped/);
});

test("wrong amount, wrong payee or not finalized fails", () => {
  assert.equal(payoutDelivered(delivered, PAYEE, 1n).ok, false);
  assert.equal(payoutDelivered(delivered, "0x" + "3".repeat(40), 10n ** 16n).ok, false);
  assert.equal(payoutDelivered({ ...delivered, statusName: "ACCEPTED" }, PAYEE, 10n ** 16n).ok, false);
});

test("balances: contract loses the amount, payee gains it less its own fee", () => {
  const ok = { contractBefore: 100n, contractAfter: 90n, payeeBefore: 5n, payeeAfter: 13n, amount: 10n, netFee: 2n };
  assert.equal(checkBalances(ok), "");
  assert.match(checkBalances({ ...ok, contractAfter: 100n }), /contract balance/);
  assert.match(checkBalances({ ...ok, payeeAfter: 5n }), /payee balance/);
  assert.equal(checkBalances({ ...ok, payeeAfter: 15n, payeeSent: false }), "");
});
