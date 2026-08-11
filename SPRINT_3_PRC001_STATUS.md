# HMIP — Sprint 3 Status (PRC-001 Vertical Slice)

This is the actual Sprint 3 (see `SPRINT_3_STATUS.md` for the
interface-contract retrofit that preceded it and made this possible).

## Scope delivered

### New core/ infrastructure (generic, not domain-specific)

- `core/lineage.py` — `LineageRecord` (12_Data_Contract.md section
  8.1) + `InMemoryLineageTracer` conforming to
  `05_Interface_Contract.md` section 4.8's `LineageTracer` protocol.
  **Pulled forward from its planned Sprint 4 slot** because
  `15_Acceptance_Criteria.md` section 3's Sprint 3 criteria explicitly
  require "Lineage được ghi nhận" for PRC-001. In-memory only —
  persistence is still Sprint 4 scope.
- `core/workflow_engine.py` — `WorkflowEngine` conforming to section
  4.3's protocol (`load`/`execute`/`cancel`), composing
  `WorkflowLoader` + `Planner` + `TaskRegistry` + `TaskExecutor` +
  `EventBus` + `InMemoryLineageTracer`. **Also not originally scoped
  for Sprint 3 by name**, but required for "Workflow PRC-001 chạy
  end-to-end" (the acceptance criterion literally needs something that
  runs an entire workflow, and no other class does that). `cancel()`
  is honestly a best-effort stub — see its docstring for why real
  mid-flight cancellation isn't possible without an async execution
  model that doesn't exist yet.
- `core/executor.py` gained template resolution:
  `task.input` values shaped exactly `"${task_id.output}"` or
  `"${key}"` are now resolved against an `outputs` accumulator before
  the handler is called (`"${collect.output}"` → `outputs["collect"]`,
  `"${product_id}"` → `outputs["product_id"]`). This was missing
  before — without it, downstream tasks had no way to read upstream
  tasks' outputs, and `12_Data_Contract.md` section 5.2's own example
  (`"output": "${collect.output}"`) would have been unimplementable.

### Domain code (`domains/beer/pricing/`)

All required artifacts from `03_Domain_Specification.md` section 6:

- `workflows/WF-PRC-001.yaml`
- `prompts/extract_price.md`
- `schemas/schema.json`
- `skills/collect_price.py`
- `decision_engine.py`

Plus (not individually named as required artifacts, but necessary for
"Required runtime behavior" — collect/extract/validate/compare/
decide/alert all actually running):

- `models.py` — `BeerPrice` (12_Data_Contract.md section 6.1).
- `skills/extract_price.py`, `skills/validate_price.py`,
  `skills/compare_price.py`, `skills/alert_price.py`.
- `registrar.py` — `register_prc_001_tasks()`, the `task_registrar`
  callback wiring all six handlers into a `TaskRegistry` (mirrors
  `core.bootstrap.BootstrapKernel`'s constructor-injection pattern).
- `tests/` — `test_models.py`, `test_decision_engine.py`,
  `test_skills.py` (co-located per `03_Domain_Specification.md`
  section 3: "Mỗi domain pack nên có: ... tests").
- `tests/workflow/test_prc_001_end_to_end.py` (root-level, not
  domain-local) — the one test allowed to depend on both
  `core.workflow_engine` and the domain pack; exercises the full
  IGNORE/ALERT/ESCALATE decision range, lineage recording, event
  publishing, and a failure path (unknown product).

## Key design decisions / interpretations (flagged, not silently assumed)

1. **BaseAdapter vs BaseSkill naming vs the `skills/` folder.**
   `03_Domain_Specification.md` section 6 only names
   `skills/collect_price.py` as a required path, but `collect`'s task
   type is `"adapter"` and `05_Interface_Contract.md` defines
   `BaseAdapter` separately from `BaseSkill`. Read this as: the
   `skills/` folder is this project's name for "all domain runnable
   units," regardless of which core Protocol a given one satisfies —
   `collect_price.py` implements `BaseAdapter`, the others implement
   `BaseSkill` or are plain functions. Not stated explicitly anywhere;
   inferred from the folder being the only one named.
2. **No live LLM invocation.** `extract_price.md` documents the real
   prompt/output contract; `ExtractPriceSkill` implements that exact
   contract deterministically instead of calling an LLM, because no
   LLM-invocation infrastructure exists in core runtime yet. The
   prompt file's own "Implementation note" section documents this and
   the intended swap point.
3. **Mock external source.** `CollectPriceAdapter.fetch()` reads from
   a small hardcoded dict instead of a real HTTP/scraping call — real
   integration is out of scope for proving the architecture layering.
   Swappable by construction (it's the only thing implementing
   `BaseAdapter` for this task).
4. **`WorkflowExecutionException` for domain validation.** `BeerPrice`
   and the compare/decide handlers raise `WorkflowExecutionException`
   for runtime data problems (bad price, missing field) — neither
   `05_Interface_Contract.md` section 6 nor `12_Data_Contract.md`
   name an exact exception class for domain-entity validation; this
   was the closest fit ("Workflow runtime failures").
5. **`WorkflowEngine.execute()`'s `context` parameter** is treated as
   the workflow's business input dict (product_id/source/market), not
   a serialized `core.context.ExecutionContext` — see
   `core/workflow_engine.py`'s module docstring for the reasoning.
6. **Static `base_price`.** `compare`/`decide` use a base price bound
   at registration time (`registrar.py`'s `DEFAULT_BASE_PRICE`), not
   looked up per-product from any reference-price source — no such
   source exists yet.
7. **Decision thresholds** (`domains/beer/pricing/decision_engine.py`):
   `ALERT_THRESHOLD_PERCENT = 5.0`, `ESCALATE_THRESHOLD_PERCENT =
   10.0`, `LOW_CONFIDENCE_THRESHOLD = 0.7` — invented for this slice
   (not specified anywhere in the docs pack), explicit and named per
   section 4.9's rule, easy to tune later.

## Explicitly NOT done in this sprint

- No knowledge-layer/ontology integration (Brand/Product/SKU) — that's
  Sprint 4.
- No lineage persistence — in-memory only (see above).
- `WorkflowEngine.cancel()` has no real effect in practice (documented
  limitation, not silently pretended to work).
- No real HTTP adapter, no real LLM-backed extraction.
- Retry policy in `WF-PRC-001.yaml` is declared (`exponential_backoff`,
  3 attempts) at the workflow level, but no task in the workflow
  overrides it individually, and — as noted in `SPRINT_2_STATUS.md`
  from the start — `TaskExecutor` still only implements linear
  `base_delay_ms * attempt` backoff regardless of the declared
  strategy name.

## Definition of Done — Sprint 3 (`15_Acceptance_Criteria.md` section 3)

All three checks confirmed clean on the target machine on 2026-08-01
(`ruff` re-verified after the UP017 fix):

```
uv run ruff check .    -> All checks passed!
uv run mypy .           -> Success: no issues found in 32 source files
uv run pytest -v        -> 155 passed
```

- [x] Workflow PRC-001 chạy end-to-end (`test_prc_001_runs_end_to_end_and_completes`).
- [x] Adapter thu thập dữ liệu hoạt động (`test_collect_price_adapter_fetch_returns_known_product`).
- [x] Prompt extraction trả output đúng schema (`test_validate_price_handler_accepts_valid_payload`,
      `test_prc_001_runs_end_to_end_and_completes` passing `validate`).
- [x] Decision engine trả kết quả đúng policy (`test_prc_001_decision_reflects_price_variance`,
      `_alerts_on_moderate_variance`, `_escalates_on_large_variance`).
- [x] Lineage được ghi nhận (`test_prc_001_records_lineage_for_every_step`).
- [x] Workflow test pass (155/155, including the failure-path test
      `test_prc_001_fails_gracefully_for_unknown_product`).
- [x] `ruff check .` clean.

**Sprint 3 DoD is met.**

## Next (only after this Sprint's DoD is confirmed)

Sprint 4 per `10_Project_Backlog.md`: Knowledge & Lineage —
ontology load/validate, Brand/Product/SKU schemas, lineage
*persistence* (this sprint only built in-memory), provenance trace.
