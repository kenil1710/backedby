import { defineConfig } from "@playwright/test";

// The live site, driven in the installed Chrome with a throwaway wallet (wallet.js) on the demo registry.
// Everything it records lands in docs/e2e/.
export default defineConfig({
  testDir: ".",
  testMatch: /.*\.e2e\.js/,
  timeout: 3 * 3600 * 1000,
  expect: { timeout: 60_000 },
  workers: 1,
  outputDir: "../docs/e2e/artifacts",
  reporter: [["list"], ["json", { outputFile: "../docs/e2e/results.json" }]],
  use: {
    baseURL: process.env.SITE ?? "https://backedby-ledger.vercel.app",
    channel: "chrome",
    headless: true,
    viewport: { width: 1280, height: 900 },
    video: "on",
    trace: "on",
    screenshot: "on",
  },
});
