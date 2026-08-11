# HMIP — Sprint 1 Status (Foundation)

## Scope delivered

Per `10_Project_Backlog.md` Sprint 1 and `11_Master_Prompt_Claude.md`
step 6.1 ("Repository skeleton"):

- Full repository skeleton per `01_System_Specification.md` §5 /
  `14_Repository_File_Mapping.md` §3, created directly at this
  directory's root (see Assumptions).
- `core/context.py` — `ExecutionContext` (frozen dataclass) +
  `ExecutionContextFactory` (`create`, `derive`).
- `core/models.py` — `TaskExecutionResult`, `BootstrapStepResult`,
  `BootstrapReport`, `DecisionResult`, decision constants.
- `core/registry.py` — `TaskRegistry` with the required state machine
  `READY -> FROZEN -> EXECUTING -> {COMPLETED, FAILED}`, thread-safe.
- `core/config.py` — `ConfigLoader` / `FrozenConfig` implementing the
  full pipeline shape: load -> deep merge -> expand variables ->
  resolve secrets (stub) -> validate -> fingerprint -> freeze.
  Single-use loader (raises on double `load()`), matching "config sau
  bootstrap phải immutable".
- `core/observability.py` — `structlog`-based structured JSON logging,
  `log_event()` helper carrying the spec's minimum field set.
- `core/bootstrap.py` — `BootstrapKernel` (runs the 8-step bootstrap
  order, fail-fast, produces `BootstrapReport`) + `BootstrapManager`
  facade.
- `platform/bootstrap.py` — CLI entrypoint (`python -m
  platform.bootstrap`), `platform/diagnostics.py` — Python version
  check.
- `shared/constants.py`, `shared/types.py`.
- `config/runtime.yaml`, `config/logging.yaml`.
- `tests/unit/test_context.py`, `test_registry.py`, `test_config.py`,
  `test_bootstrap.py` — cover context uniqueness/immutability,
  registry state machine (all transitions incl. invalid ones),
  config load/merge/expand/fingerprint/double-load, and end-to-end
  bootstrap success + fail-fast paths.
- `pyproject.toml` — Python 3.12, ruff, mypy strict, pytest, per
  ADR-009 / `06_Coding_Standard.md`.

## Definition of Done — Sprint 1 (`10_Project_Backlog.md`)

Confirmed on the target machine (Windows, `uv`, Python 3.14.5 — see
Assumption 6 below) on 2026-07-31:

- [x] Bootstrap runs successfully (`test_bootstrap_succeeds_and_freezes_registry`).
- [x] Registry state machine works (`test_registry.py`, full coverage
      of valid + invalid transitions).
- [x] Context is generated uniquely (`test_context.py`).
- [x] Unit tests exist for all foundation modules (context, registry,
      config, bootstrap).
- [x] `ruff check .` — all checks passed.
- [x] `mypy .` (strict) — no issues found in 14 source files.
- [x] `pytest -v` — 28 passed, 0 failed.

**Sprint 1 DoD is met.** One bug was found and fixed during this
verification round: `BootstrapKernel._step` originally raised on
failure before the failing step was appended to the report, so a
failed bootstrap produced an incomplete or empty `steps` list. Fixed
by making step execution always return a `BootstrapStepResult`
(never raise) and having `run()` stop at the first non-SUCCESS result
— see `core/bootstrap.py::BootstrapKernel._run_step`.

## Assumptions made

1. Repository root = this directory itself (no extra nested `HMIP/`
   folder), since this directory already serves as the project root
   containing the spec docs.
2. Secret resolution in `ConfigLoader` is a pass-through stub — no
   real secret provider yet. Deferred per ADR-006 (adapter pattern)
   until a domain/deployment sprint actually needs secrets.
3. No DI framework — dependency injection is done manually via
   constructor parameters (`BootstrapKernel(config_paths=..., env=...)`),
   per coding standard §11 ("không tạo abstraction không cần thiết").
4. `structlog` chosen for structured logging per coding standard §9
   recommendation.
5. Tests import the project via `tests/conftest.py` inserting the repo
   root onto `sys.path` — no editable install required for Sprint 1.
6. Target machine runs Python 3.14.5 via `uv`, above the `>=3.12`
   floor in `pyproject.toml` but above ADR-009's stated "Python 3.12"
   preference. Not blocking (nothing in Sprint 1 uses 3.13/3.14-only
   syntax), but flagged as an open question below since ADR-009 is an
   accepted ADR and shouldn't drift silently.

## Open questions (do not block Sprint 1, needed before Sprint 2/3)

1. Container/DI: keep manual constructor injection, or introduce a DI
   framework (e.g. `dependency-injector`) once `core/orchestrator.py`
   and the planner need to wire more services together?
2. Real secret provider target for production (Vault / AWS Secrets
   Manager / env-only)?
3. Does `platform/registry.py` need to exist separately from
   `core/registry.py`, or are platform-level registry helpers just
   thin wrappers calling into `core.registry`?
4. ADR-009 says "Python 3.12"; the dev machine runs 3.14.5 via `uv`.
   Keep `requires-python = ">=3.12"` (current, permissive) or pin to
   `>=3.12,<3.13` to match ADR-009 literally? Deferred — not a Sprint
   1 blocker.

## Known risk — flagging, not fixing unilaterally

`platform/` as a top-level importable package name **shadows Python's
standard library `platform` module**. Once anything does
`import platform` inside a process where this repo's `platform/`
package has already been imported (e.g. via `python -m
platform.bootstrap`), `sys.modules["platform"]` will resolve to this
project's package, not the stdlib one — this can silently break any
dependency that calls `platform.system()`, `platform.python_version()`,
etc. `14_Repository_File_Mapping.md` §7 names this folder `platform/`
verbatim, so it has not been renamed. If this becomes a real problem in
Sprint 2+, it needs an ADR to rename (e.g. `platform_/` or
`hmip_platform/`) rather than a silent implementation change.

## How to run (locally, on your machine — not run by Claude)

```bash
cd D:\AI_PROJECTS\HMIP_Hermes_Market_Intelligence_Platform
uv venv
uv pip install -e ".[dev]"
uv run ruff check .
uv run mypy .
uv run pytest -v
uv run python -m platform.bootstrap
```

## Next (Sprint 2 — Runtime Core, do not start until you confirm Sprint 1 passes)

Per `10_Project_Backlog.md`: `core/event_bus.py`, `core/planner.py`
(DAG + cycle detection), workflow loading contract, task execution
contract, retry policy skeleton, integration tests for orchestrator
flow.
