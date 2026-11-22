// TEMPLATE (/qa setup adapts it): runner plugin, its config file and the allowlist below.
// StrykerJS + Vitest for /qa (personal, git-excluded). Run from the repo root:
//   node_modules/.bin/stryker run .claude/qa/stryker.config.mjs --mutate <file>[,<file>...]
// Sandbox and report live in the OS temp dir, so nothing lands in the repo.
import os from "node:os";
import path from "node:path";

const out = path.join(os.tmpdir(), "cc-qa", path.basename(process.cwd()));

/** @type {import("@stryker-mutator/api/core").PartialStrykerOptions} */
const config = {
  testRunner: "vitest",
  plugins: ["@stryker-mutator/vitest-runner"],
  vitest: { configFile: "vitest.config.mts", related: true },
  coverageAnalysis: "perTest",
  reporters: ["clear-text", "progress", "json"],
  jsonReporter: { fileName: path.join(out, "mutation", "frontend.json") },
  clearTextReporter: { allowColor: false, logTests: false, reportScoreTable: true },
  tempDirName: path.join(out, "stryker-tmp"),
  cleanTempDir: "always",
  // Allowlist: the sandbox copies only what the Vitest suite reads (never `.env*` or backend/).
  ignorePatterns: [
    "/*",
    "!/src",
    "!/public",
    "!/contracts",
    "!/package.json",
    "!/tsconfig.json",
    "!/next.config.ts",
    "!/vitest.config.mts",
    "!/vitest.setup.ts",
    "!/vitest.setup.dom.ts",
  ],
  concurrency: 4,
  timeoutMS: 10000,
  thresholds: { high: 90, low: 75, break: null },
};

export default config;
