"""Scoped mutation testing for a Python backend (mutmut), run by `/qa` (personal, git-excluded).

TEMPLATE: `/qa setup` copies this next to the backend (e.g. `backend/.qa/`) and adapts
SOURCE_PREFIX, TEST_ROOTS and WORKSPACE_ENTRIES to the project layout.

mutmut needs `fork`, so this runs inside the `api` container:
`make -f Makefile -f .qa/qa.mk qa-mutate paths="src/app/x.py" tests="tests/test_x.py"`.
The run happens in a throwaway copy of the backend under /tmp: neither mutmut's `mutants/` tree
nor any mutated source ever touches the bind-mounted working tree. The report lands in
`backend/.qa/mutation/`.

When the test suite is destructive (e.g. its session fixture drops the test schema), mutants run
one at a time and only the explicit test files passed in `--tests` are selected.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPORT_DIR = BACKEND / ".qa" / "mutation"
SOURCE_PREFIX = "src/app/"
TEST_ROOTS = ("tests/", "config_tests/", "contract_tests/", "tenancy_tests/")
COPY_IGNORE = shutil.ignore_patterns(
    "__pycache__",
    ".pytest_cache",
    ".hypothesis",
    ".venv",
    ".cache",
    ".qa",
    "mutants",
    "uploads",
    "*.pyc",
)
WORKSPACE_ENTRIES = (
    "src",
    "tests",
    "config_tests",
    "contract_tests",
    "tenancy_tests",
    "alembic",
    "contracts",
    "public",
    "scripts",
    "alembic.ini",
    "pyproject.toml",
)


def _split(values: list[str]) -> list[str]:
    return [item for value in values for item in value.replace(",", " ").split() if item]


def _validate(paths: list[str], tests: list[str]) -> None:
    if not paths or not tests:
        raise SystemExit("qa_mutation: pass at least one --paths file and one --tests file.")
    for path in paths:
        if not path.startswith(SOURCE_PREFIX) or not path.endswith(".py"):
            raise SystemExit(f"qa_mutation: {path!r} is not a .py file under {SOURCE_PREFIX}.")
        if not (BACKEND / path).is_file():
            raise SystemExit(f"qa_mutation: {path!r} does not exist.")
    for test in tests:
        file_part = test.split("::", 1)[0]
        if not file_part.startswith(TEST_ROOTS) or not file_part.endswith(".py"):
            raise SystemExit(
                f"qa_mutation: {test!r} must be an explicit test file (folders are not allowed)."
            )
        if not (BACKEND / file_part).is_file():
            raise SystemExit(f"qa_mutation: {test!r} does not exist.")


def _toml_list(items: list[str]) -> str:
    return "[" + ", ".join(json.dumps(item) for item in items) + "]"


def _build_workspace(paths: list[str], tests: list[str], basetemp: Path) -> Path:
    workspace = Path(tempfile.mkdtemp(prefix="qa-mutation-"))
    for entry in WORKSPACE_ENTRIES:
        source = BACKEND / entry
        if source.is_dir():
            shutil.copytree(source, workspace / entry, ignore=COPY_IGNORE)
        elif source.is_file():
            shutil.copy2(source, workspace / entry)

    also_copy = [
        entry + ("/" if (BACKEND / entry).is_dir() else "")
        for entry in WORKSPACE_ENTRIES
        if entry not in ("src", "tests") and (BACKEND / entry).exists()
    ]
    config = "\n".join(
        [
            "",
            "[tool.mutmut]",
            'source_paths = ["src/"]',
            f"only_mutate = {_toml_list(paths)}",
            f"also_copy = {_toml_list(also_copy)}",
            f"pytest_add_cli_args_test_selection = {_toml_list(tests)}",
            "pytest_add_cli_args = "
            + _toml_list(["-q", "-p", "no:cacheprovider", "--basetemp", str(basetemp)]),
            'process_isolation = "forkserver"',
            "use_git_change_detection = false",
            "",
        ]
    )
    with (workspace / "pyproject.toml").open("a", encoding="utf-8") as handle:
        handle.write(config)
    return workspace


def _mutmut(workspace: Path, *args: str, check: bool = False) -> subprocess.CompletedProcess:
    executable = shutil.which("mutmut")
    if executable is None:
        raise SystemExit("qa_mutation: mutmut is not installed (run through .qa/qa.mk).")
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    return subprocess.run(  # noqa: S603 - fixed executable, arguments built by this script
        [executable, *args],
        cwd=workspace,
        env=env,
        check=check,
        text=True,
        capture_output=args[0] != "run",
    )


def _survivors(workspace: Path) -> list[dict[str, str]]:
    listing = _mutmut(workspace, "results")
    survivors = []
    for line in listing.stdout.splitlines():
        name, _, status = line.strip().partition(":")
        if not status or "survived" not in status and "no tests" not in status:
            continue
        diff = _mutmut(workspace, "show", name.strip()).stdout
        survivors.append({"mutant": name.strip(), "status": status.strip(), "diff": diff})
    return survivors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paths", nargs="+", required=True, help="source files to mutate")
    parser.add_argument("--tests", nargs="+", required=True, help="explicit test files to run")
    parser.add_argument("--max-children", default="1", help="parallel mutants (default 1)")
    args = parser.parse_args()

    if not hasattr(os, "fork"):
        raise SystemExit("qa_mutation: mutmut needs fork; run the qa-mutate target of .qa/qa.mk.")

    paths, tests = _split(args.paths), _split(args.tests)
    _validate(paths, tests)

    basetemp = Path(tempfile.mkdtemp(prefix="qa-mutation-pytest-"))
    workspace = _build_workspace(paths, tests, basetemp)
    try:
        run = _mutmut(workspace, "run", "--max-children", args.max_children)
        _mutmut(workspace, "export-cicd-stats")
        stats_file = workspace / "mutants" / "mutmut-cicd-stats.json"
        stats = json.loads(stats_file.read_text()) if stats_file.is_file() else {}
        survivors = _survivors(workspace)
    finally:
        shutil.rmtree(basetemp, ignore_errors=True)
        shutil.rmtree(workspace, ignore_errors=True)

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "paths": paths,
        "tests": tests,
        "exit_code": run.returncode,
        "stats": stats,
        "survivors": survivors,
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_file = REPORT_DIR / "backend.json"
    report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"\nqa_mutation: stats {json.dumps(stats)}")
    print(f"qa_mutation: {len(survivors)} surviving mutant(s); report at .qa/mutation/backend.json")
    for survivor in survivors:
        print(f"\n--- {survivor['mutant']} ({survivor['status']})\n{survivor['diff']}")
    return run.returncode


if __name__ == "__main__":
    sys.exit(main())
