# HMIP — Sprint 5 Status (Testing & Quality)

## Scope delivered

Per `10_Project_Backlog.md` Sprint 5 and `15_Acceptance_Criteria.md`
section 3 (Sprint 5) + `08_Testing_Standard.md`.

### Coverage enforcement

- Added `pytest-cov` to dev dependencies.
- `pyproject.toml` now runs every `pytest` invocation with coverage
  over `core`, `domains`, `knowledge`, `platform`, `shared`, branch
  coverage on, and **fails the run** if line coverage drops below 80%
  (`08_Testing_Standard.md` section 4's unit-coverage floor).

### Chaos / fault-injection tests (`tests/chaos/`)

One file per failure mode named in `08_Testing_Standard.md` section
11: `test_storage_failure.py`, `test_network_timeout.py`,
`test_disk_full.py`, `test_dependency_unavailable.py`,
`test_deadlock.py` (honest scope note in that file: this codebase is
single-threaded/synchronous, so a real cross-thread deadlock isn't
architecturally possible yet — the test instead proves `TaskRegistry`'s
`RLock` allows safe reentrant same-thread access).

**Two real gaps were found and fixed while writing these:**

1. `core/config.py::ConfigLoader._read_yaml` only caught
   `yaml.YAMLError`; an `OSError` from `Path.read_text()` would have
   propagated as a raw, untyped exception instead of the locked
   `ConfigValidationException`. Fixed.
2. `core/workflow_engine.py::WorkflowEngine.execute()` called
   `lineage_tracer.record_trace()` unguarded; a write failure would
   have propagated raw instead of `WorkflowExecutionException`. Fixed
   (mirrors the existing `EventDeliveryError` handling for event
   publishing).

### Workflow regression tests (`tests/workflow/test_prc_001_regression.py`)

Per section 7 ("Mỗi lỗi đã sửa phải có test riêng để không tái diễn"):
pins the Sprint 1 bootstrap bug's equivalent at the `WorkflowEngine`
level (a failing task must still produce a lineage record before the
run halts), pins that a finished execution's per-run `TaskRegistry`
always reaches a terminal state, and pins the Sprint 3 decision that
`collect`'s templates resolve from the caller's `context`, not a
hardcoded YAML literal.

### Prompt evaluation tests + golden datasets (`tests/prompt/`)

`golden/extract_price_golden.json` (versioned, 4 cases) and
`golden/decision_golden.json` (versioned, 8 cases covering
IGNORE/ALERT/ESCALATE around both thresholds plus the low-confidence
→ HUMAN_REVIEW override), each with a matching exact-match test file.
Both extraction and decisioning are currently deterministic, not
LLM-backed (see `SPRINT_3_PRC001_STATUS.md`), so these are exact-match
evaluations, not tolerance-based semantic scoring.

### Compensation orchestration (real STRICT-policy rollback)

You asked for this to be implemented now rather than deferred:

- `core/workflow_engine.py::WorkflowEngine._compensate()` — on task
  failure, if `WorkflowDefinition.compensation_policy == "STRICT"`,
  calls every previously-succeeded task's registered `"rollback"`
  callable, in **reverse execution order**. A rollback failing doesn't
  stop the rest — every failure is collected into
  `compensation.errors`, not just the first. Per-rollback lineage
  recording (`step_id = f"rollback:{task_id}"`) is best-effort: a
  logging failure there doesn't retroactively mark an already-
  succeeded rollback as failed.
- `execute()`'s returned record gained a `"compensation"` key:
  `{"triggered": bool, "completed": bool, "errors": [{"task_id",
  "error"}, ...]}`.
- `TaskRegistry`'s task-dict convention grew an optional `"rollback"`
  key (alongside `"name"`/`"handler"`) — a callable taking one
  `compensation_context: dict` (`{"task_id", "output",
  "execution_id"}`).
- All six PRC-001 tasks register a `"rollback"` — `extract`'s calls
  the real `ExtractPriceSkill.rollback()`; the other five are
  individually-documented no-ops, since none of PRC-001's current
  tasks have real external side effects to undo yet (see
  `SPRINT_3_PRC001_STATUS.md`) — but the orchestration **mechanism**
  is real, wired end-to-end, and tested.
- Tests: 5 new compensation tests in `tests/unit/test_workflow_engine.py`
  (reverse-order calling, skip-if-no-rollback, rollback-failure
  collection without halting the rest, no-compensation-on-success,
  per-rollback lineage) using the generic core fixture, plus
  `tests/workflow/test_prc_001_compensation.py` proving the same
  mechanism against PRC-001's real collect/extract/validate handlers
  (forces a `compare` failure so three real tasks get genuinely rolled
  back).

### Critical-workflow coverage gate (90%, separate from the 80% blended gate)

`coverage.py`/`pytest-cov` only support one `fail_under` per
invocation — no native way to enforce two different percentages in one
run's config. Rather than build new tooling for this (there's no CI
pipeline yet to hang a second stage off of — that's Sprint 6), this is
a **second, separate command**, using `-o addopts=""` to override
`pyproject.toml`'s default `addopts` just for this invocation:

```powershell
uv run pytest -o addopts="" --cov=core.workflow_engine --cov=domains.beer.pricing --cov-report=term-missing --cov-fail-under=90
```

Please run this alongside the main suite — not automated into
anything yet, so it only runs when explicitly invoked.

## Explicitly NOT done this sprint

- No CI pipeline wiring — no CI configuration file exists yet;
  deferred to Sprint 6 (Deployment & Operations) at the earliest.

## Open questions

Carried over, still unresolved, still not blocking: lineage
persistence default path (`SPRINT_4_STATUS.md`), placeholder
`runtime_version`/`kernel_version` strings, Python 3.14.5 vs
ADR-009's stated "3.12".

## Definition of Done — Sprint 5

Confirmed on the target machine on 2026-08-01, after compensation
orchestration was added:

```
uv run ruff check .    -> All checks passed!
uv run mypy .           -> Success: no issues found in 36 source files
uv run pytest -v        -> 233 passed, coverage 90.99% (>= 80% required)
uv run pytest -o addopts="" --cov=core.workflow_engine --cov=domains.beer.pricing --cov-fail-under=90
                        -> 233 passed, critical-path coverage 95.97% (>= 90% required)
```

- [x] Coverage threshold reached (blended 90.99% >= 80%).
- [x] Critical-workflow coverage reached (95.97% >= 90% for
      `core.workflow_engine` + `domains.beer.pricing`).
- [x] Failure paths tested.
- [x] Prompt outputs stable against golden dataset.
- [x] Chaos tests run successfully.
- [x] Compensation orchestration tests pass.

**Sprint 5 DoD is met.**

## Next (only after this Sprint's DoD is confirmed)

Sprint 6 per `10_Project_Backlog.md`: Deployment & Operations —
Dockerfile, deployment manifests, health/readiness endpoints,
bootstrap CLI command, observability integration, release checklist.
