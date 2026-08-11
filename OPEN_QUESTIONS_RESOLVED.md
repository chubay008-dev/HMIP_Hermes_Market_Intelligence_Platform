# Open Questions — Resolved (2026-08-04)

Tracks resolution of the open questions carried across
`SPRINT_3_STATUS.md`, `SPRINT_4_STATUS.md`, and `SPRINT_6_STATUS.md`.
Those files are left as-is (historical record of when each question
was raised); this file is the current, authoritative answer.

## 1. `runtime_version`/`kernel_version` values — RESOLVED

- `runtime_version` is now tied to the real installed package version
  (`importlib.metadata.version("hmip")`, matching `pyproject.toml`'s
  `[project].version`), falling back to a hardcoded `"0.1.0"` only if
  package metadata isn't discoverable. Implemented in
  `shared/constants.py::_resolve_runtime_version()`.
- `kernel_version` is a separate hardcoded constant, `"1.0.0"`,
  representing this codebase's own core-runtime-kernel release train
  — bump it manually in `shared/constants.py` when kernel behavior
  changes in a way worth tracking. Not tied to `pyproject.toml`.
- Both remain overridable per-run via `HMIP_RUNTIME_VERSION`/
  `HMIP_KERNEL_VERSION` env vars (Sprint 6), which take priority over
  either default.

## 2. `PersistentLineageTracer` default path — RESOLVED

- Defaults to `knowledge/dynamic/lineage/lineage.jsonl` (relative to
  the process's current working directory — same convention as
  `platform_/bootstrap.py`'s `HMIP_REPORT_DIR`/`HMIP_CONFIG_PATH`
  defaults) when no `path` is passed to the constructor. Implemented
  in `core/lineage.py::PersistentLineageTracer.DEFAULT_PATH`.
- `core.workflow_engine.WorkflowEngine`'s own default tracer is
  **unchanged** — it still defaults to `InMemoryLineageTracer()`, not
  `PersistentLineageTracer()`. Switching the engine's default to
  write to disk automatically was a separate decision that wasn't
  asked for and would have real consequences (every test using the
  default constructor would start writing real files unless every
  such test were updated to redirect it) — callers who want
  persistence still pass `lineage_tracer=PersistentLineageTracer()`
  explicitly.

## 3. Python version for local dev — RESOLVED (no change)

- `pyproject.toml`'s `requires-python = ">=3.12"` stays as-is —
  **not** pinned to `>=3.12,<3.13`. The local dev machine keeps
  running Python 3.14.5 via `uv`.
- This only concerns local development. The container (`Dockerfile`)
  was already unambiguously pinned to `python:3.12-slim` in Sprint 6,
  independent of this decision.

## 4. Ontology wired into PRC-001 — RESOLVED

- Added a new `enrich` task to `WF-PRC-001.yaml`, between `validate`
  and `compare`: `collect → extract → validate → enrich → compare →
  decide → alert`.
- `domains/beer/pricing/skills/enrich_price.py::enrich_with_ontology()`
  cross-references the validated price record against
  `knowledge.ontology` (loaded from the real `knowledge/master/*.json`
  files):
  - Rejects an unknown `product_id` (`WorkflowExecutionException`,
    code `ENRICH_PRICE_UNKNOWN_PRODUCT`).
  - Rejects an extracted `brand` that doesn't match the ontology's
    authoritative `Brand.name` for that product (code
    `ENRICH_PRICE_BRAND_MISMATCH`) — a genuine data-quality check, not
    a formality.
  - Fills in `sku` from the ontology when extraction didn't provide
    one (PRC-001's mock collect payload never does).
- `registrar.py` registers `enrich`'s handler and rollback (a no-op,
  like most of PRC-001's other tasks — see `SPRINT_5_STATUS.md`'s
  compensation section for why that's fine).
- Tests: `domains/beer/pricing/tests/test_enrich_price.py` (isolated
  unit tests plus one test loading the real shipped master data),
  plus updated lineage/event/compensation assertions across
  `tests/workflow/test_prc_001_*.py` to include the new 7th step.
- **Bug found and fixed on first real test run**: `enrich_price.py`'s
  `_MASTER_DIR` used `Path(__file__).resolve().parents[3]`, which
  resolves to `domains/` (the file is 4 levels below repo root:
  `domains/beer/pricing/skills/enrich_price.py`), not the repo root —
  every real-workflow PRC-001 test failed with `KnowledgeValidationException:
  master data file not found`. Fixed to `parents[4]`. All 268 tests
  pass after the fix.

## Still open (not addressed this round)

None remaining from the tracked list.
