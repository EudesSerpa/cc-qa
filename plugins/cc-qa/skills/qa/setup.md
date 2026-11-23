# /qa setup: QA config and tooling for a project

Runs when `.claude/qa/` is missing or incomplete, or on `/qa setup`. The goal is a config that lets
the generic agents run in this project without touching anything the team shares.

## Principles

- **Personal by default.** Everything this setup creates is excluded through `.git/info/exclude`
  (local to this clone, never committed), not through `.gitignore`.
- **No edits to tracked files.** Do not change manifests, lockfiles, shared configs, CI, test
  setup files or the team's Makefile. Tools are installed in a way that leaves them untouched
  (see "Installing tools"). If a technique truly cannot run without editing a tracked file, say
  so, propose the edit, and only apply it when the user agrees.
- **Read before writing.** Build the config from what the repo actually does: its CLAUDE.md /
  AGENTS.md / CONTRIBUTING, docs, test configs, Makefile/scripts and CI. Never guess a command;
  run it once to confirm it works.
- Ask the user once, with the full proposal, before writing files.

## Step 1: Detect

For each stack in the repo (a folder with its own manifest: `package.json`, `pyproject.toml`,
`go.mod`, `Cargo.toml`, `pom.xml`, ...), record:

- language, package manager, test runner and the exact command to run ONE test file;
- whether tests need a database or service, how the test DB is configured (env var), and whether
  the test setup is destructive (drops/truncates). If it is, every agent needs its own database;
- the API framework and its error contract (status codes, error body shape) if there is an API;
- any LLM/AI pipeline (calls to a model provider, prompt files, parsers of model output);
- spec sources: CLAUDE.md files, docs folder, ADRs, schema files;
- conventions new tests must follow (naming, import style, test file location);
- generated files to drop from the diff (lockfiles, generated clients/contracts);
- the default base branch for PRs (CLAUDE.md, CONTRIBUTING, or `git remote show origin`).

## Step 2: Pick the tools per stack

| Stack                 | Mutation                                 | Property / fuzz                      |
| --------------------- | ---------------------------------------- | ------------------------------------ |
| JS/TS + Vitest        | StrykerJS 9.x + `@stryker-mutator/vitest-runner` | fast-check                   |
| JS/TS + Jest          | StrykerJS 9.x + `@stryker-mutator/jest-runner`   | fast-check                   |
| Python + pytest       | mutmut 3.x (needs `fork`: Linux/macOS/WSL or a container) | Hypothesis          |
| Go                    | gremlins / go-mutesting                  | `testing/quick`, rapid               |
| Rust                  | cargo-mutants                            | proptest                             |
| JVM                   | PIT                                      | jqwik                                |

CRAP hotspots, any stack above: [crapper](https://github.com/unclebob/crapper)
(Robert C. Martin; TS/JS, Python, Go, Rust, Java, Clojure). Install it once per machine outside
any repo (`git clone https://github.com/unclebob/crapper <tools dir>/crapper`, note the commit) and
run it as `PYTHONUTF8=1 uv run --project <tools dir>/crapper python -m crapper ...`.

Known gotchas (verified):

- **StrykerJS 10 on Windows** breaks with `ERR_PACKAGE_IMPORT_NOT_DEFINED "#identifier"` (Babel 8
  nests a path over 260 chars). Pin 9.x on Windows.
- **Stryker sandbox**: use an allowlist `ignorePatterns` (`"/*"` then `"!/src"`, ...). The default
  copies everything, including `.env*` files, and dies on lock files of other tools. Put
  `tempDirName` and the JSON report in the OS temp dir, so nothing lands in the repo and lint /
  format / typecheck never see the sandbox.
- **mutmut needs `fork`**: on Windows run it in the project's container (or WSL). Run it on a copy
  of the backend in `/tmp`, never on the bind-mounted tree, so `mutants/` and mutated sources
  never touch the working tree.
- **Hypothesis with function-scoped pytest fixtures** (async DB sessions, test clients): set
  `deadline=None` and suppress `HealthCheck.function_scoped_fixture` per test; each example must
  create its own rows.
- **crapper**: its `./crapper` script assumes `python3` and `.venv/bin` (broken on Windows; use
  `uv run --project`), and `--help` needs `PYTHONUTF8=1`. Its default run deletes coverage reports
  and runs the whole test suite (and installs `coverage`/`pytest`/`@vitest/coverage-v8` into the
  project): always produce scoped LCOV yourself and pass `--use-existing-coverage`. It reads
  `<root>/target/coverage/**/lcov.info` and `<root>/coverage/**/lcov.info` and writes
  `<root>/.metrics/crap.edn`: exclude `target/` and `.metrics/` locally unless the project already
  uses them, then remove them after the run. Python coverage: `pytest-cov` via `uv run --with`,
  `COVERAGE_FILE` in the scratch dir; Vitest: `@vitest/coverage-v8` matching the Vitest version,
  installed with `--no-save`.
- **Git Bash on Windows** rewrites leading-slash arguments to container commands: prefix them with
  `MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*'`.

## Step 3: Installing tools without touching tracked files

| Ecosystem | How                                                                                         |
| --------- | ------------------------------------------------------------------------------------------- |
| Bun       | `bun add --no-save <pkg>@<ver>...` (re-run in Preflight when the package is missing)        |
| npm       | `npm install --no-save <pkg>@<ver>...`                                                      |
| pnpm      | no reliable no-save: install into `.claude/qa/node_modules` or ask the user                  |
| uv        | `uv run --with "<pkg>>=<ver>" ...` on every command (ephemeral overlay env)                 |
| pip/venv  | a separate venv under the scratch dir, or ask the user                                      |
| Make      | a personal makefile loaded next to the team's: `make -f Makefile -f <dir>/qa.mk <target>`   |

Tests that import a tool the project does not declare cannot be committed until the team adopts
the tool. Record those tools under `Personal tooling` in `project.md`, so the report flags them.

## Step 4: Write the config

Create, then add each path to `.git/info/exclude` (check with `git check-ignore -v <path>`):

- `.claude/qa/project.md`: the sections below.
- `.claude/qa/routing.md`: tiered table from paths to techniques and reviewer lenses (format
  below).
- Tool configs and helper scripts, adapted from [templates/](templates/):
  - `stryker.config.mjs`: set the allowlist to the folders the test runner reads, the runner
    plugin and its config file;
  - `qa_mutation.py`: set `SOURCE_PREFIX`, `TEST_ROOTS` and `WORKSPACE_ENTRIES` to the project
    layout; keep the `/tmp` workspace copy;
  - `qa.mk`: set the compose command, service name, test DB URL and the DB-name guard prefix.
    Place scripts where the runtime can see them (for a container, inside the bind-mounted
    folder, e.g. `backend/.qa/`).

Run each mutation and property command once on one small file to prove it works, and paste the
score line in the setup summary.

### `project.md` sections

```markdown
# QA config: <project>

## Default base
<branch PRs target>

## Stacks
| Stack | Root | Source globs | Test globs | Runner |

## Spec sources
<docs, CLAUDE.md files, schemas, per area>

## Generated files
<files dropped from the scope>

## Test discovery
<how to find the tests that cover a source file, per stack (rg patterns)>

## Preflight
| Needed for | Check | If it fails |

## Test isolation
<test DB env var, URL form, one database name per agent (mutation, property, fuzz, judge), and
why (e.g. the suite drops the schema at start)>

## Commands
### <stack>
- run test files: ...
- mutation: ... (report path, how to read survivors)
- property tests: file naming, import, how `--deep` raises the examples
- fuzz tests (API stacks): file naming, client fixture, auth helper

## CRAP
<tools dir; per stack: scoped LCOV command for given test files → path crapper reads; the crapper
command; the isolated DB for backend coverage; what to clean up afterwards>

## Deep run
<env vars / settings for --deep>

## API contract
<error body shape, content type, error type prefix, auth/permission/tenant model, how to build an
access matrix>

## AI pipeline
<files that call the model or parse its output, the hermetic fake to use, the trust boundary, the
golden-set or eval command (manual only)>

## Lens hints
<project-specific risks per lens: money, concurrency, security, tenancy, correctness>

## Guardrails
<project rules every agent must follow: conventions for new tests, shell quirks, forbidden commands>

## Personal tooling
<tools installed only for /qa: packages, versions, how they are installed>
```

Leave out sections that do not apply (no API → no `API contract`; no model → no `AI pipeline`), and
drop the matching techniques from routing.

### `routing.md` format

```markdown
| Tier | Paths | Techniques | Reviewer lenses |
```

- Tier 1: money, auth/permissions, tenant isolation, security boundaries, AI trust boundary.
- Tier 2: API routes and schemas, domain services, state machines, shared utils/schemas.
- Tier 3: hooks, adapters, migrations.
- Tier 4: UI components, styles, docs, test files only: no techniques.

Rules to keep: first matching row wins; test files never trigger techniques on their own;
`review` runs once with at most two lenses; mutation is skipped (and reported as "no tests") for a
file without covering tests.
