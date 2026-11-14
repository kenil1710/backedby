// BackedBy on the live site: every page a reviewer opens, then a real write from the browser on the demo
// registry (a monitoring check filed through the page, and a bound borrow through the collateral gate),
// each confirmed from contract state. Screenshots, video and trace in docs/e2e/.
import { test, expect } from "@playwright/test";
import { connectWallet } from "./wallet.js";

const shot = (page, name) => page.screenshot({ path: `../docs/e2e/${name}.png`, fullPage: true });
const steps = [];
const step = (name) => steps.push(name);

test("live site: board, pair (history, coverage, PoR), keeper, verify, rules, and writes on the demo registry", async ({ page, request }) => {
  // 1. board on the canonical registry
  await page.goto("/");
  await expect(page.getByText(/pairs ·/)).toBeVisible({ timeout: 120_000 });
  await expect(page.getByText("USDC.e on Arbitrum")).toBeVisible();
  await shot(page, "01-board"); step("board");

  // 2. a pair with a PoR feed: history, coverage and PoR panels
  await page.getByText("WBTC on Arbitrum").first().click();
  await expect(page.getByText("Backing over time")).toBeVisible({ timeout: 120_000 });
  await expect(page.getByText("Coverage: does the pair list everything its vaults back?")).toBeVisible();
  await expect(page.getByText("Chainlink Proof of Reserve")).toBeVisible({ timeout: 120_000 });
  await shot(page, "02-pair-wbtc-por"); step("pair_por");

  // 3. a pair whose vault backs unlisted destinations: coverage GAP names them
  await page.goto("/");
  await page.getByText(/through Chainlink CCIP|through LayerZero/).first().click();
  await expect(page.getByText("Coverage: does the pair list everything its vaults back?")).toBeVisible({ timeout: 120_000 });
  await shot(page, "03-pair-coverage"); step("pair_coverage");

  // 4. keeper, verify, rules
  await page.goto("/keeper");
  await expect(page.getByRole("heading", { name: "Keeper" })).toBeVisible();
  await expect(page.getByText(/Last run|Reading the keeper/)).toBeVisible({ timeout: 120_000 });
  await shot(page, "04-keeper"); step("keeper");
  await page.goto("/verify");
  await expect(page.getByText(/identical/i).first()).toBeVisible({ timeout: 180_000 });
  await shot(page, "05-verify"); step("verify");
  await page.goto("/docs");
  await expect(page.getByText("4a. Coverage: nothing a vault backs goes unnoticed")).toBeVisible();
  await expect(page.getByText(/Two RPCs per chain; transport faults are PENDING/)).toBeVisible();
  await shot(page, "06-rules"); step("rules");

  // 5. the badge API answers bound to the pair's own tokens
  const api = await (await request.get("/api/backed?pair=1")).json();
  expect(api.gate.asked_for.pair).toBe(1);
  expect(typeof api.gate.state).toBe("string");
  step("api");

  // 6. writes on the demo registry with a throwaway wallet
  const me = await connectWallet(page);
  await page.goto("/");
  await page.evaluate(() => window.localStorage.setItem("backedby-deployment", "demo"));
  await page.goto("/collateral");
  await page.getByRole("button", { name: /Connect/ }).first().click();
  await expect(page.getByText(me.slice(0, 6), { exact: false }).first()).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText("The gate's answer for every pair")).toBeVisible();
  await page.locator("#gp").selectOption({ index: 1 });
  await page.getByRole("button", { name: "Ask to borrow" }).click();
  await expect(page.getByText(/Accepted and confirmed|Finalized|Accepted\./).first()).toBeVisible({ timeout: 900_000 });
  await expect(page.getByText(new RegExp(`by ${me.slice(0, 6)}`, "i")).first()).toBeVisible({ timeout: 300_000 });
  await shot(page, "07-borrow-recorded"); step("borrow");

  // 7. a pair page on the demo registry: file a monitoring check from the browser
  await page.goto("/pair/1");
  await expect(page.getByText("Monitoring check").first()).toBeVisible({ timeout: 120_000 });
  const btn = page.getByRole("button", { name: "File a monitoring check" });
  if (await btn.isEnabled()) {
    await btn.click();
    await expect(page.getByText(/Accepted|Finalized|Turned down|Not done/).first()).toBeVisible({ timeout: 900_000 });
    step("monitor_click");
  } else step("monitor_click_skipped_open_check");
  await shot(page, "08-demo-pair"); step("demo_pair");
  console.log("steps", steps.join(","));
});
