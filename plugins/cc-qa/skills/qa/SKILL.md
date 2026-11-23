---
name: qa
description: Adversarial QA for the current change. Routes the diff to specialized agents (mutation testing, property-based testing, API fuzzing, AI red teaming, adversarial review) and has a judge turn every accepted finding into a failing test. Never fixes code, never commits.
argument-hint: "[diff | <branch> | setup] [--paths <file>...] [--deep] [--review] [--only mutation|property|fuzz|redteam|review]"
disable-model-invocation: true
---

# /qa

Run the QA workflow for the change in front of you. The agents that write the code never judge it:
every QA agent starts in a fresh context, sees only the diff, the spec and the code, and tries to
break it. A judge reproduces each finding; only reproduced findings survive, and each one leaves a
failing (red) test behind. Nothing is fixed and nothing is committed.

Talk to the user in their language (the language of their message). Agent prompts are in English.

Everything project-specific (stacks, commands, test databases, routing, lenses, conventions) lives
in the project's **QA config**, `.claude/qa/` at the repo root. This skill and its agents are
generic and never assume a project.

## Arguments

| Argument             | Effect                                                                                                                                                    |
| -------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| _(none)_             | Same as `/qa <default base>` (`Default base` in `project.md`)                                                                                             |
| `<branch>`           | Scope = what a PR from the current branch into `<branch>` would contain (`<branch>...HEAD`, from the merge base) + working-tree changes + untracked files |
| `diff`               | Scope = only the uncommitted work: staged + unstaged changes vs `HEAD` + untracked files. Commits are ignored                                             |
| `setup`              | Create or refresh the QA config and tooling for this project ([setup.md](setup.md)), then stop                                                            |
| `--paths <file>...`  | Narrow the scope to these files (use it when other sessions have edits in the working tree)                                                               |
| `--deep`             | Use the deep run settings from `project.md` (more examples per property)                                                                                  |
| `--review`           | Force the adversarial review even for a Tier 4-only diff                                                                                                  |
| `--only <technique>` | Run a single technique (still followed by the judge)                                                                                                      |

## Step 0: QA config

Read `.claude/qa/project.md` and `.claude/qa/routing.md`. If either is missing, or `project.md`
lacks a section a technique in the plan needs, follow [setup.md](setup.md) first (it asks the user
before writing anything), then continue with the original arguments.

## Step 1: Scope

1. Resolve the mode from the first positional argument:
   - `diff` → **worktree mode**. No base ref.
   - anything else (default: `Default base` from `project.md`) → **branch mode** with `<branch>`
     as the target. Run `git fetch origin <branch> --quiet`, then use `origin/<branch>` as
     `<base>` if it exists, else the local `<branch>`. If neither resolves
     (`git rev-parse --verify`), stop and list close matches from
     `git branch -a --list "*<branch>*"`. If `<base>` is the current branch itself, say the PR
     diff is empty and suggest `/qa diff`.
   - Tests and mutation always run on the checked-out code, so `<branch>` is the PR target, never
     a branch to test without checking it out.
2. Collect changed files:
   - branch mode: `git diff --name-only <base>...HEAD`, `git diff --name-only HEAD`,
     `git ls-files --others --exclude-standard`;
   - worktree mode: `git diff --name-only HEAD`, `git ls-files --others --exclude-standard`.
     Nothing to report → say there are no uncommitted changes and stop.
     With `--paths`, keep only the listed files (in worktree mode, only those with uncommitted
     changes).
3. Other sessions or people may have edits in the working tree. In branch mode, if the working
   tree holds changes that do not belong to the branch's work (files you did not touch in this
   conversation and that the user did not mention), list them and ask the user whether to include
   them, unless `--paths` was given. In worktree mode the user asked for the whole working tree:
   include everything without asking, but list the files in the plan so foreign edits are
   visible. Never stash, reset or revert anything.
4. Drop deleted files and the generated files listed in `project.md` (lockfiles, generated
   contracts).

## Step 2: Route

Use `.claude/qa/routing.md`. For each file pick the first matching row and collect
`{technique → files}`. Then, for every source file that will be mutated, find the tests that cover
it with the `Test discovery` rules in `project.md`. Keep explicit files only, never folders. Cap
at the 6 most direct test files per source file.

Print the plan as one short table (file → techniques → test files) and continue without waiting,
unless Step 1 asked a question. Tier 4-only diff without `--review`: say there is nothing for
adversarial QA to check and stop.

## Step 3: Preflight

Run only the `Preflight` checks of `project.md` that the plan needs. Fix what the table says can be
fixed (installing the personal QA tooling); ask the user for anything else (starting Docker, a
database service).

Create the scratch root `<scratchpad>/qa/` (forward slashes). Every agent gets its own subfolder
for temporary files and test temp dirs.

## Step 3b: CRAP hotspots (before mutation)

Run it yourself (it takes seconds) when the plan has `mutation` files and `project.md` has a `CRAP`
section; otherwise skip it and say so in the report.

1. Produce coverage **only from the covering test files of Step 2**, with the commands in the `CRAP`
   section (never the whole suite, never the tool's default coverage run, which runs every test).
   Backend tests use the CRAP database from `Test isolation`.
2. Run crapper with `--use-existing-coverage` on the mutation files only.
3. Hotspots: every function with CRAP ≥ 10, or with complexity ≥ 5 and no coverage. CRAP ≥ 30 is
   high risk. Keep the table rows (function, file, CC, coverage, CRAP).
4. Clean up exactly what the `CRAP` section says the run leaves behind.

CRAP is a filter, not a verdict: 100% coverage gives a low score even when the tests assert
nothing. Only mutation says whether the tests check behavior, so a clean CRAP table never skips
mutation.

## Step 4: Dispatch (parallel)

Launch every needed agent in ONE message so they run concurrently. Agents are namespaced by the
plugin: `subagent_type` is `cc-qa:<agent>`. Each prompt must contain:

- the files in its scope and the covering test files from Step 2;
- the exact diff commands for the mode: branch mode `git diff <base>...HEAD -- <files>` and
  `git diff HEAD -- <files>`; worktree mode `git diff HEAD -- <files>` only. Untracked files have
  no diff: the agent reads them whole;
- the spec sources to read first (`Spec sources` in `project.md`, narrowed to the area), the
  docstrings/schemas of the changed code, and the change intent in one sentence (from the user or
  the commit messages; never from your own reasoning about the implementation);
- the sections of `project.md` that agent needs, pasted verbatim under a `## Project QA config`
  heading: always `Guardrails` and `Commands` of its stack, plus `Lens hints` for reviewers,
  `API contract` for the fuzzer, `AI pipeline` for the red team;
- its scratch folder and its isolated test resources (`Test isolation` in `project.md`): never a
  shared, dev or deployed database, and never the same one as another agent;
- the deep run settings when `--deep` was given;
- for `qa-mutation-tester`, the CRAP hotspot rows of its files (Step 3b).

| Technique  | Agent                     | Count                             |
| ---------- | ------------------------- | --------------------------------- |
| `review`   | `qa-adversarial-reviewer` | 2, one per lens (see routing.md)  |
| `mutation` | `qa-mutation-tester`      | 1 per stack with files            |
| `property` | `qa-property-tester`      | 1 per stack with files            |
| `fuzz`     | `qa-api-fuzzer`           | 1                                 |
| `redteam`  | `qa-ai-redteam`           | 1                                 |

Two mutation runs of the same stack never overlap: one `qa-mutation-tester` handles every file of
that stack in a single mutation command.

## Step 5: Judge

When every agent has reported, launch ONE `cc-qa:qa-judge` with:

- every finding verbatim (id, agent, file, claim, repro, evidence, severity, confidence);
- every test file the agents created or modified;
- the same scope, spec sources, project config sections, its own scratch folder and test
  resources.

The judge reproduces each finding, rejects what it cannot reproduce or what is intended behavior per
the spec, and leaves exactly one failing test per accepted bug. Do not judge findings yourself and do
not skip the judge, even when only one agent reported.

## Step 6: Report

Reply in the user's language with:

1. **Verdict**: one line (e.g. "2 confirmed bugs, 1 test gap, 4 rejected").
2. **Confirmed bugs**: table `severity | file:line | what fails | red test (path::name)`.
3. **Test gaps** (surviving mutants, functions without tests, new passing properties): table with
   the tests added to close them, or the mutants left as equivalent with the reason. List
   **dead code** separately (file:line + the callers searched), for a human to delete, and the
   tests the judge marked **hollow** and removed.
4. **Rejected**: one line each with the judge's reason.
5. **Mutation score** per file, before/after when the tester added tests.
6. **CRAP**: the hotspot table from Step 3b, and the same functions after re-running Step 3b once
   when the judge kept new tests (before → after). Functions still at CRAP ≥ 10 with full coverage
   are candidates to split (complexity), which is a refactor for a human, not a QA task.
7. **Files touched**: every test file created or changed (the user reviews them before
   committing). Mark the ones that import a tool the project does not declare (see
   `Personal tooling` in `project.md`): they cannot be committed until the project adopts that
   tool. No source file may appear here; if one does, flag it as a violation.
8. **Next step**: offer to fix the confirmed bugs test-first (the red tests already exist).

Then stop. Do not fix, do not commit, do not push.

## Guardrails for every agent prompt

Paste these into each prompt, followed by the project's own `Guardrails`:

- Never edit production code. Only test files (and test fixtures) may be created or changed.
- Never commit, stash, reset, checkout or revert. Other sessions may edit this repo concurrently.
- Run explicit test files only, never folders or whole suites. No end-to-end browser suites.
- Never point tests at a shared, dev or deployed database or service; use only the isolated
  resources the prompt gives you.
- Temporary files go in your scratch folder, never inside the repo.
- Every finding states: file:line, claim, exact repro command, the failing output line, severity
  (high/medium/low) and confidence (0-100).
