# HMIP — Sprint 4 Status (Knowledge & Lineage)

## Scope delivered

Per `10_Project_Backlog.md` Epic D / Sprint 4 and
`15_Acceptance_Criteria.md` section 3 (Sprint 4) + section 4
(Knowledge module):

### Ontology (`knowledge/ontology/`)

- `core_schema.json` — required artifact per
  `14_Repository_File_Mapping.md` section 6. JSON Schema definitions
  for `Brand`/`Product`/`SKU`, with a top-level `"version"` field
  (Sprint 4 AC: "Ontology versioned").
- `models.py` — `Brand`, `Product`, `SKU` frozen dataclasses with
  per-entity `__post_init__` validation, plus `OntologyDataset` (the
  validated, cross-referenced result of loading a full dataset).
- `loader.py` — `OntologyLoader`: loads/validates individual entities
  against `core_schema.json` via `jsonschema`, and
  `load_dataset()`/`load_dataset_from_files()` validate **referential
  integrity** across a whole dataset (`Product.brand_id` must
  reference a known `Brand.id`; `SKU.product_id` must reference a
  known `Product.id`) — this is the actual "ontology load/validate"
  and "Entities rõ quan hệ" acceptance criteria, not just per-entity
  shape checking.

### Master data (`knowledge/master/`)

- `brands.json`, `products.json`, `skus.json` — real, valid master
  data (not just test fixtures), deliberately tied to PRC-001's mock
  product: `Product.id = "P123"` matches
  `domains/beer/pricing/skills/collect_price.py`'s mock collect data,
  so `OntologyLoader.load_dataset_from_files()` against these real
  files is tested directly (`test_load_dataset_from_files_accepts_real_master_data`).

### Dynamic data (`knowledge/dynamic/`)

- Currently just a `.gitkeep` explaining its purpose. Nothing computes
  "dynamic intelligence" (e.g. trend snapshots) yet — there's no
  derived-analytics component in the codebase to produce it. Not
  populated with placeholder content to avoid pretending this exists.

### Lineage persistence (`core/lineage.py`)

- `PersistentLineageTracer` — append-only, file-persisted, one JSON
  line per `record_trace()` call (durable immediately, no buffering).
  `query(step=...)` and `list_records()` read it back — Sprint 4's
  actual deliverable: "Lineage records được tạo và lưu" / "Provenance
  trace có thể kiểm tra được".
- `LineageTracer` — a `Protocol` (structural typing) so
  `core.workflow_engine.WorkflowEngine` can accept either tracer
  without hardcoding a concrete class. Only `record_trace()` is part
  of the actual locked contract (05_Interface_Contract.md section
  4.8); `list_records()` is included in this *local* Protocol purely
  for typing convenience (documented in its own docstring).
- `InMemoryLineageTracer` is unchanged (still Sprint 3's tracer,
  still the `WorkflowEngine` default).

### Tests

- `tests/unit/test_ontology.py` — entity validation, schema
  loading/versioning, per-entity and dataset-level referential
  integrity, plus loading the **real** shipped master data files.
- `tests/unit/test_lineage.py` — extended with `PersistentLineageTracer`
  tests: append, parent-directory creation, empty-before-write,
  cross-instance persistence (a second tracer instance reads what the
  first wrote — proves real file durability, not shared memory),
  `query()` filtering, hash preservation across reload.
- `tests/unit/test_workflow_engine.py` — one new test running the
  full generic-fixture workflow with a `PersistentLineageTracer` and
  re-reading the file afterward.

## Explicitly NOT done this sprint

- Ontology is **not wired into the PRC-001 workflow**. `WF-PRC-001`
  still runs exactly as it did in Sprint 3 — nothing in
  `domains/beer/pricing/` calls `OntologyLoader` yet. Wiring them
  together (e.g. having `collect`/`extract` resolve `brand`/`sku` via
  the ontology instead of PRC-001's own ad hoc mock fields) wasn't
  asked for and would be new scope, not a Sprint 4 requirement per the
  docs — Sprint 4's AC is about the knowledge layer existing and
  working on its own, not about integration with Sprint 3.
- No provenance data model beyond `LineageRecord` itself. The docs
  never define a distinct "ProvenanceRecord" shape anywhere found so
  far (`12_Data_Contract.md` section 8.1 only defines `LineageRecord`)
  — reading back an ordered sequence of `LineageRecord`s via
  `list_records()`/`query()` **is** the provenance trace here.
- `knowledge/dynamic/` stays empty — see above.

## Assumptions / open questions

1. **Where should lineage actually persist by default?**
   `PersistentLineageTracer` takes a required `path` with no default —
   deliberately not decided here. Two reasonable conventions exist
   (`knowledge/dynamic/lineage/` — arguably "dynamic intelligence", or
   `data/processed/lineage/` — arguably "ready-to-use domain output"),
   and picking one unilaterally felt like a real architecture decision
   rather than an implementation detail. Please pick one (or a third
   option) before any real deployment wires this in permanently.
2. **`OntologyValidationException` naming**: introduced
   `core.exceptions.KnowledgeValidationException` since neither
   `05_Interface_Contract.md` section 6 nor any other doc names an
   exact exception class for the Knowledge Layer. Same
   "closest-fit-and-flagged" approach used for
   `WorkflowExecutionException` in Sprint 3's `BeerPrice` validation.
3. Carried over, still unresolved, still not blocking: placeholder
   `runtime_version`/`kernel_version` strings, Python 3.14.5 vs
   ADR-009's stated "3.12".

## Definition of Done — Sprint 4

Confirmed on the target machine on 2026-08-01, first run — no fix
rounds needed:

```
uv run ruff check .    -> All checks passed!
uv run mypy .           -> Success: no issues found in 36 source files
uv run pytest -v        -> 178 passed
```

- [x] Ontology load/validate thành công (`test_load_dataset_from_files_accepts_real_master_data`
      and the referential-integrity rejection tests).
- [x] Brand/Product/SKU schema rõ ràng (`core_schema.json` + `models.py`).
- [x] Lineage records được tạo và lưu (`PersistentLineageTracer` tests).
- [x] Provenance trace có thể kiểm tra được (`query()`/`list_records()`
      cross-instance persistence tests).
- [x] Tests cho knowledge và lineage pass (178/178 total).

**Sprint 4 DoD is met.**

## Next (only after this Sprint's DoD is confirmed)

Sprint 5 per `10_Project_Backlog.md`: Testing & Quality — expanded
unit coverage, workflow regression tests, prompt evaluation tests
against a golden dataset, chaos/fault-injection tests.
