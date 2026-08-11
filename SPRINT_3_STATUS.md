# HMIP — Interface Contract Alignment (post Sprint 1/2 retrofit)

This is **not** Sprint 3 itself (no domain code for PRC-001 exists
yet). It documents a full retrofit of Sprint 1/2's core runtime to
match `05_Interface_Contract.md` and `12_Data_Contract.md` exactly,
done in two approved rounds before Sprint 3 begins — because Sprint 3
(the PRC-001 vertical slice) needs `BaseAdapter`/`BaseSkill`/
`DecisionEngine` built directly against these contracts, and building
domain code on a misaligned foundation would have compounded the
problem.

## Why this happened

Sprint 1 (`core/context.py`, `core/models.py`) was built after reading
`01/02/03/06/07/10/11/14` but **not** `04_API_Contract.md` or
`05_Interface_Contract.md` — a real process gap, not a judgment call.
Sprint 2 (`core/workflow.py`, `core/planner.py`, `core/event_bus.py`,
`core/executor.py`) inherited the same gap. Once `05` was read in full
before starting Sprint 3, the divergence turned out to be large enough
that it needed two separate user decisions (see below) rather than one
silent fix.

## Round 1 — data contracts (approved, done)

`ExecutionContext`, `TaskExecutionResult`, `BootstrapReport`,
`DecisionResult` shapes rewritten to match 05_Interface_Contract.md
section 5 / 12_Data_Contract.md exactly:

- `ExecutionContext`: dropped `tenant_id`/`actor_id`/`request_id`/
  `parent_trace_id`/`policy_version` (not in the locked 6-field shape).
  `ExecutionContextFactory.derive()` now carries parent linkage via
  `metadata["parent_trace_id"]` instead of a dedicated field.
- `TaskExecutionResult`: `task_name`/`status`/`duration_ms`/`error`
  only — dropped `task_id`/`output`/`error_code`/`error_message`.
  Output payload propagation moved to `TaskExecutor.execute()`'s
  optional `outputs: dict[str, Any]` side-channel parameter, keyed by
  task id, since the locked result shape has no field for it.
- `BootstrapReport`: `execution_id`/`status`/`task_results`/
  `runtime_version`/`kernel_version` — `BootstrapStepResult` merged
  into `TaskExecutionResult` (bootstrap steps and workflow tasks now
  share one result type). Added a read-only `.success` property
  (not a stored field) for ergonomic access.
- `TaskStatus` enum values corrected: `FAILURE` -> `FAILED`, added
  `RETRYING`/`CANCELLED` (declared, not yet produced by the executor).
- `DecisionResult`: `recommended_action` replaces the earlier
  `metadata` field; added `__post_init__` validation (confidence
  0.0-1.0, decision in the allowed set, non-empty reason).
- `runtime_version`/`kernel_version` default to `"1.6.1"`/`"RC2.1"` —
  **literal placeholder strings copied from the spec's own examples**;
  no ADR defines what these should really be tied to (pyproject
  version? git tag? separate kernel release train?). See open
  questions below.

## Round 2 — protocol shapes + exception names (approved, done)

`Registry`/`EventBus`/`ConfigLoader`/`Planner` rebuilt to the literal
dict-based method signatures in `05_Interface_Contract.md` section 4,
and exception class names renamed per section 6:

| Component | Contract shape now implemented |
|---|---|
| `TaskRegistry` (`core/registry.py`) | `register(task: dict)`, `get_task(name) -> dict \| None`, `list_tasks() -> list[dict]`, `state -> str`, `transition_to(state: str)`, `freeze()` kept as its own method (contract lists it separately) |
| `EventBus` (`core/event_bus.py`) | `publish(event: dict)` (reads `event["event_type"]` for routing — no separate type param), `subscribe`/`unsubscribe(event_type, handler)`. The `Event` dataclass is gone. |
| `ConfigLoader` (`core/config.py`) | `load() -> dict` (no validate/freeze inside it anymore), `merge(*configs) -> dict`, `validate(config) -> None`, `freeze(config) -> FrozenConfig`. No longer single-use — `load()` can be called any number of times. |
| `Planner` (`core/planner.py`) | `plan(workflow: dict) -> dict` (`{"workflow_id", "waves"}`), `detect_cycles(workflow: dict) -> bool`. Internally still parses through `WorkflowLoader.loads()` and a private `_build_waves()` — `WorkflowDefinition`/`ExecutionPlan` are implementation details now, not part of `Planner`'s public surface. |

Exception renames (`core/exceptions.py`) — **exact class only, no
subclasses**, per explicit project decision (see Round 3 below):

- `RegistryError` -> `RegistryStateException` (raised directly for every
  registry failure — `DuplicateTaskError`/`InvalidRegistryTransitionError`
  do not exist; distinguish via `.code`). `TaskNotFoundError` was removed
  entirely, since `get_task()` returns `None` instead of raising.
- `ConfigError` -> `ConfigValidationException`.
- `ValidationError` (workflow-specific usages) -> `WorkflowParseException`
  (raised directly for cycle detection too — no `PlannerError` subclass;
  distinguish via `.code == "PLANNER_CYCLE_DETECTED"`).
- `ValidationError` (DecisionResult usages) -> `DecisionEngineException`.
- `WorkflowExecutionException` added but **not yet raised anywhere** —
  reserved for a future `WorkflowEngine`; `TaskExecutor` still returns a
  FAILED result instead of raising, by design (mirrors
  `BootstrapKernel`).
- `EventDeliveryError`, `BootstrapError` kept as-is (not named in
  section 6's list).
- `ValidationError` itself was deleted — nothing uses it anymore.

Callers updated accordingly: `core/executor.py` (looks up handlers via
`get_task()` + `outputs` side-channel), `core/bootstrap.py`
(`_resolve_config` now calls `load()` -> `validate()` -> `freeze()`
explicitly; registry steps use string state instead of the
`RegistryState` enum at the boundary), `platform/bootstrap.py`
(dict-based task registration), and all affected tests.

## Explicitly NOT done in this retrofit

- `BaseAdapter`, `BaseSkill`, `WorkflowEngine`, `DecisionEngine`,
  `LineageTracer` protocols (05_Interface_Contract.md section 4) —
  none of these exist yet. They're genuinely new for Sprint 3, not a
  retrofit of something already built, so building them now would be
  starting Sprint 3 early without it being asked for.
- No orchestrator ties `Planner` + `TaskRegistry` + `TaskExecutor` +
  `EventBus` together automatically — the integration test still wires
  them by hand.

## Round 3 — exact-class exception decision (approved, done)

User decision: exceptions must raise the **exact** locked class, never
a subclass. `DuplicateTaskError`, `InvalidRegistryTransitionError`, and
`PlannerError` were removed; `core/registry.py` now raises
`RegistryStateException` directly for every failure case, and
`core/planner.py` raises `WorkflowParseException` directly for cycle
detection. All specific-failure distinctions moved to the `.code`
attribute (e.g. `REGISTRY_DUPLICATE_TASK`, `REGISTRY_NOT_READY`,
`REGISTRY_INVALID_TRANSITION`, `REGISTRY_UNKNOWN_STATE`,
`REGISTRY_INVALID_TASK_SCHEMA`, `PLANNER_CYCLE_DETECTED`). Tests in
`test_registry.py`/`test_planner.py` updated to assert on `.code`
instead of exception subtype. This resolves open question 2 below —
removed from the open list.

## Assumptions made during this retrofit

1. `RegistryState`/`BootstrapStatus`/`TaskStatus` remain internal
   `StrEnum`s even though the contract types their corresponding
   fields as plain `str` — a `StrEnum` member *is* a `str`
   (`isinstance(x, str) is True`), so this satisfies the contract's
   type while keeping internal type safety. `TaskRegistry.state`
   explicitly returns `.value` (a plain `str`) at the public boundary
   so callers never need to import `RegistryState`.
2. `PlannerError`/cycle-detection failures are classified as
   `WorkflowParseException` (structural/pre-execution), not
   `WorkflowExecutionException` (runtime) — planning happens before
   any task runs, so this reads as parse-time validation. Flagged as
   an interpretation, not a documented rule.
3. `TaskRegistry`'s task-dict convention (`"name"` + `"handler"` keys)
   is this codebase's own convention layered on top of the contract's
   bare `dict[str, Any]` — the Protocol itself doesn't mandate any
   specific keys.
4. `Planner.plan()`'s dict input/output shape (`{"id", "tasks": [...]}`
   in, `{"workflow_id", "waves": [[...]]}` out) is inferred from
   `WorkflowDefinition`'s own field names and from `12_Data_Contract.md`
   section 5 — section 4.4 itself only says `dict[str, Any]`, not the
   exact keys. If a later doc defines the exact wave/plan dict shape
   differently, this will need to change again.

## Open questions carried forward

1. `runtime_version`/`kernel_version` placeholder strings (see Round 1)
   — what should these actually be wired to?
2. Same Python 3.14.5-vs-ADR-009-"3.12" question from
   `SPRINT_1_STATUS.md` — still unresolved, still not blocking.

## Definition of Done

Round 1/2/3 all confirmed on the target machine (last confirmed
2026-08-01):

- [x] `ruff check .` — all checks passed.
- [x] `mypy .` (strict) — no issues found in 18 source files.
- [x] `pytest -v` — 95 passed, 0 failed.

**This retrofit's DoD is met, including the exact-class exception
decision.** Interface contract alignment for Registry/EventBus/
ConfigLoader/Planner + exception renames is fully done.

## Next (only after this retrofit's DoD is confirmed)

Sprint 3 proper: `domains/beer/pricing/` vertical slice (PRC-001) —
real `BaseAdapter`/`BaseSkill`/`DecisionEngine` implementations against
the now-aligned contracts, schema validation against
`12_Data_Contract.md`, and the first genuine `DecisionResult`s.
