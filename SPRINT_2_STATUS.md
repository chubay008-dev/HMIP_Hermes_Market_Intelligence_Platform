# HMIP — Sprint 2 Status (Runtime Core)

## Scope delivered

Per `10_Project_Backlog.md` Sprint 2:

- `core/workflow.py` — `WorkflowDefinition`, `TaskDefinition`,
  `RetryPolicy` (data contracts per `20_Sample_Schemas.md` §5) +
  `WorkflowLoader` (YAML -> `WorkflowDefinition`, validates unique
  task ids, known dependencies, allowed task types). Cycle detection
  is explicitly NOT here.
- `core/planner.py` — `Planner` / `ExecutionPlan`: builds a wave-based
  DAG execution order (Kahn's-algorithm style), raises `PlannerError`
  on any dependency cycle (including self-cycles). Deterministic:
  task ids within a wave are sorted.
- `core/event_bus.py` — `EventBus` / `Event`: synchronous, thread-safe,
  in-memory pub/sub. Handler exceptions are collected (not swallowed)
  and re-raised as `EventDeliveryError` after all handlers run.
- `core/executor.py` — `TaskHandler` protocol (calling convention every
  registered task handler must satisfy) + `TaskExecutor`: resolves a
  task's handler via `TaskRegistry`, applies its `RetryPolicy`, always
  returns a `TaskExecutionResult` (never raises for an ordinary task
  failure — same pattern as `BootstrapKernel._run_step`).
- `core/exceptions.py` — added `PlannerError`, `EventDeliveryError`.
- Tests:
  - `tests/unit/test_workflow.py` — RetryPolicy/TaskDefinition/
    WorkflowDefinition validation, WorkflowLoader YAML parsing.
  - `tests/unit/test_planner.py` — linear chain, diamond dependency
    (parallel wave), independent tasks, direct cycle, self-cycle.
  - `tests/unit/test_event_bus.py` — subscribe/publish/unsubscribe,
    subscription order, handler exception collection.
  - `tests/unit/test_executor.py` — success, retry-then-succeed,
    retry-exhausted failure, input passthrough.
  - `tests/integration/test_workflow_execution_flow.py` — full
    WorkflowLoader -> Planner -> TaskRegistry -> TaskExecutor ->
    EventBus flow using a generic linear fixture
    (`tests/integration/fixtures/generic_linear_workflow.yaml`)
    modeled after the PRC-001 step names in
    `19_Example_Workflows.md` (collect/extract/validate/compare/
    decide/alert) with no-op handlers — **not** real domain logic.

## Explicitly NOT built this sprint

- `core/orchestrator.py` does not exist yet. Backlog Sprint 2 lists
  event bus, planner, workflow loading contract, task execution
  contract, and retry policy skeleton — not the orchestrator itself.
  The integration test wires the pieces together manually to prove
  they compose; a dedicated orchestrator class is a later sprint's
  job (check `10_Project_Backlog.md` before assuming which one).
- `core/lineage.py`, `core/validator.py`, `core/feedback_loop.py` —
  still empty, per backlog ordering.
- Real backoff-strategy interpretation: `RetryPolicy.strategy` is
  stored but `TaskExecutor` only implements one linear
  `base_delay_ms * attempt` sleep regardless of the declared strategy
  string. "exponential_backoff" is accepted as a value but not yet
  given different math from any other non-"none" strategy.

## Assumptions made

1. Per `20_Sample_Schemas.md` §11, the sample doc suggests
   `WorkflowDefinition`/`TaskDefinition`/`WorkflowExecutionRecord` map
   to `core/workflow/models.py` (a subpackage). Sprint 1 already
   established a **flat** `core/*.py` layout per
   `14_Repository_File_Mapping.md`, so this sprint added a flat
   `core/workflow.py` instead of creating a `core/workflow/` package.
   Repository mapping doc is treated as authoritative for file
   *locations*; sample schema doc is treated as authoritative for
   field *shapes* only. Flagged as an open question below since this
   is an inferred precedence, not something either doc states
   explicitly.
2. `WorkflowExecutionRecord` (20_Sample_Schemas.md §4.4) was **not**
   implemented this sprint — nothing in Sprint 2 backlog scope needed
   it yet (no orchestrator to produce execution records). Deferred to
   whichever sprint adds the orchestrator.
3. `EventBus` is synchronous and in-process only, matching the
   "Sprint 2 scope" framing already used for Sprint 1's config/logging
   stubs — no message broker decision has been made (would need its
   own ADR).
4. Retry backoff math is intentionally minimal (linear
   `base_delay_ms * attempt`) — see "Explicitly NOT built" above.

## Open questions (do not block Sprint 2, flag before Sprint 3+)

1. Confirm `core/workflow.py` (flat) vs `core/workflow/` (package) —
   does a later doc (ADR or repository mapping revision) actually
   require the subpackage form, or was `20_Sample_Schemas.md` §11
   just an informal suggestion?
2. Should `RetryPolicy.strategy` values map to genuinely different
   backoff math (e.g. real exponential `base_delay_ms * 2**attempt`
   vs linear), or is the linear skeleton acceptable until a domain
   actually needs the distinction?
3. Same **Python 3.14.5 vs ADR-009 "3.12"** question carried over from
   `SPRINT_1_STATUS.md` — still unresolved, still not blocking.

## Definition of Done — Sprint 2 (`10_Project_Backlog.md`)

Confirmed on the target machine on 2026-07-31:

- [x] `ruff check .` — all checks passed.
- [x] `mypy .` (strict) — no issues found in 18 source files.
- [x] `pytest -v` — 57 passed, 0 failed (28 from Sprint 1 +
      29 new: workflow/planner/event_bus/executor unit tests +
      integration flow test).

**Sprint 2 DoD is met.**

## How to run (PowerShell)

```powershell
cd D:\AI_PROJECTS\HMIP_Hermes_Market_Intelligence_Platform
uv run ruff check .
uv run mypy .
uv run pytest -v
```

## Next (Sprint 3 — do not start until Sprint 2 DoD is confirmed)

Per `10_Project_Backlog.md`: first real domain vertical slice
(PRC-001, `domains/beer/pricing/`), including real adapters, extraction
prompt contract, schema validation against `12_Data_Contract.md`, and
the decision engine producing genuine `DecisionResult`s — replacing
this sprint's no-op integration-test handlers with actual business
logic.
