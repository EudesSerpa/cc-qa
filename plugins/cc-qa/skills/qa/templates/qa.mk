# TEMPLATE (/qa setup adapts it): COMPOSE/SERVICE come from the team Makefile (define them here if
# it has none), and QA_TEST_DB / the DB URL / the guard prefix match the project test database.
#
# /qa mutation testing (personal, git-excluded). Loaded next to the team Makefile:
#   make -f Makefile -f .qa/qa.mk qa-mutate paths="src/app/x.py" tests="tests/test_x.py" QA_TEST_DB=<project>_test_qa_mut
# mutmut needs fork, so it runs in the api container with a throwaway /tmp venv; the tools come
# from `uv run --with`, so pyproject.toml and uv.lock stay untouched.
QA_TEST_DB ?= <project>_test
QA_TOOLS = --with mutmut==3.8.1 --with "hypothesis>=6.170"
QA_ENV = -e UV_PROJECT_ENVIRONMENT=/tmp/qa-venv -e UV_CACHE_DIR=/tmp/qa-uv-cache \
	-e TEST_DATABASE_URL=postgresql+asyncpg://<user>:<password>@db:5432/$(QA_TEST_DB)

.PHONY: qa-mutate
qa-mutate:
	@test -n "$(paths)" && test -n "$(tests)" || (echo 'Usage: make -f Makefile -f .qa/qa.mk qa-mutate paths="src/app/x.py" tests="tests/test_x.py" [QA_TEST_DB=<project>_test_qa_mut]' && exit 1)
	@case "$(QA_TEST_DB)" in <project>_test*) ;; *) echo "QA_TEST_DB must start with <project>_test" && exit 1 ;; esac
	MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' $(COMPOSE) run --rm --entrypoint sh $(QA_ENV) $(SERVICE) -c \
		'uv sync --frozen --extra dev --no-install-project --quiet && uv run --no-sync $(QA_TOOLS) python .qa/qa_mutation.py --paths $(paths) --tests $(tests)'
