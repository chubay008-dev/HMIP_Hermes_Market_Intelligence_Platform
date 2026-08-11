# HMIP — Sprint 6 Status (Deployment & Operations)

## ⚠️ Action required before re-running: delete the orphaned `platform/` folder

The predicted platform-naming risk **materialized for real** this
sprint: `ModuleNotFoundError: No module named 'platform.health';
'platform' is not a package`, interrupting collection of all 236
tests. Full root cause, decision, and consequences are in
`ADR_010_platform_package_rename.md` — summary: the package was
renamed `platform/` → `platform_/` (every reference across the repo
updated in this pass), but the tools available cannot delete files, so
the **old `platform/` folder is still physically on disk** and must be
removed manually before the next run:

```powershell
cd D:\AI_PROJECTS\HMIP_Hermes_Market_Intelligence_Platform
Remove-Item -Recurse -Force platform
```

Do this first, then run the verification commands at the bottom of
this doc.

## Scope delivered

Per `10_Project_Backlog.md` Sprint 6 and `15_Acceptance_Criteria.md`
section 3 (Sprint 6) + `09_Deployment_Guide.md`.

### Container

- `Dockerfile` (repo root) — `python:3.12-slim` base (pinned per
  ADR-009, independent of the local dev machine's Python version —
  see "Open questions" below), no secrets or runtime data baked in,
  `HEALTHCHECK` wired to `python -m platform_.health`, `ENTRYPOINT`
  is the bootstrap CLI.
- `.dockerignore` — excludes `.venv`, caches, docs, tests, and
  runtime-data directories from the build context/image.

### Health & readiness (CLI exit-code checks, not HTTP — see below)

- `platform_/health.py` — liveness only (`check_health()`: Python
  version diagnostic passes). No bootstrap/config dependency,
  no heavy work, per `09_Deployment_Guide.md` section 8.
- `platform_/readiness.py` — a marker-file-based readiness check
  (`HMIP_READY_FILE`, defaulting to a path under the OS temp
  directory — portable, not hardcoded `/tmp`). `mark_ready()` is
  called by `platform_/bootstrap.py::main()` only on a successful
  bootstrap.
- **Honest architecture note, stated in both files' docstrings**: this
  project is a run-to-completion CLI (bootstrap, optionally execute a
  workflow, exit), not a long-running server — there is no HTTP
  server to put a traditional `livenessProbe`/`readinessProbe` HTTP
  endpoint on. CLI exit-code checks (invoked via Docker `HEALTHCHECK`
  or a Kubernetes `exec` probe) are the honest fit for that
  architecture; if a long-running service model is ever added, these
  should become real HTTP endpoints instead — not faked now.

### Bootstrap CLI enhancements

`platform_/bootstrap.py` gained, beyond what Sprint 1 built:

- `_config_paths()` — now respects `HMIP_CONFIG_PATH`
  (`09_Deployment_Guide.md` section 5), defaulting to `./config`.
- Every run — success or failure — writes the full `BootstrapReport`
  as JSON to `HMIP_REPORT_DIR` (default `./reports`), satisfying
  section 11's "Nếu fail ở bootstrap, phải có report đủ ngữ cảnh để
  debug" and section 7's "persist final execution report" shutdown
  rule.
- Calls `mark_ready()` only on success.

### Config

- `config/deployment.yaml` — per `13_Configuration_Specification.md`
  section 5.5 (environment name, container settings, health-check
  behavior, readiness-check behavior, resource settings). Now loaded
  by `platform_/bootstrap.py` alongside `runtime.yaml`/`logging.yaml`.

### Versioning (partially resolves an old open question)

- `core/models.py::BootstrapReport.runtime_version`/`kernel_version`
  now read `HMIP_RUNTIME_VERSION`/`HMIP_KERNEL_VERSION` env vars at
  construction time (via `default_factory`, since a plain dataclass
  default is evaluated once at import time and would miss a
  per-run env var), falling back to the existing placeholder strings
  if unset. This directly satisfies `09_Deployment_Guide.md` section
  5's env var list, and gives a concrete answer to the "what are these
  placeholders tied to" question from `SPRINT_3_STATUS.md` — though
  what the *values themselves* should be (beyond "overridable") is
  still open.

### Deployment manifests (`deployment/`)

- `docker-compose.yml` — no exposed port (matches the run-to-
  completion architecture), volumes for `reports/`/`data/`/
  `knowledge/dynamic/` so they survive container restarts without
  being baked into the image.
- `kubernetes/job.yaml` — a `Job`, not a `Deployment` — explicitly
  because there's no long-running server to justify a `Deployment` +
  `readinessProbe` HTTP endpoint. Comments explain this choice and
  point to `CronJob` for a recurring schedule.
- `kubernetes/configmap.yaml` — non-secret env vars only; comments
  point out `HMIP_SECRET_PROVIDER` (and secret values, once a
  provider exists) belong in a Secret, never here.
- `RELEASE_CHECKLIST.md` — the six-stage flow from
  `09_Deployment_Guide.md` section 9 (test gates → container build →
  smoke test → staging → production → operational safety rules from
  section 10), plus an explicit "known gaps this checklist doesn't
  cover" section rather than implying everything is production-hardened.
- `.env.example` (repo root) — every env var from section 5, each
  honestly marked as either "wired in" (with the file/function that
  reads it) or "not read by any code yet, listed because the doc names
  it as standard."

## The `platform/` → `platform_/` rename (this round's main event)

See `ADR_010_platform_package_rename.md` for the full record. Short
version: `ruff` first reported import-sort warnings, then `pytest`
actually failed to collect 3 test files with `ModuleNotFoundError:
... 'platform' is not a package` — confirming Python's real standard
library `platform` module had won the naming collision every prior
sprint warned about. Renamed to `platform_/` (your choice, over
`hmip_platform`/`runtime_platform`), and updated every reference:
`pyproject.toml`, `Dockerfile`, `deployment/docker-compose.yml`,
`config/deployment.yaml`, `deployment/RELEASE_CHECKLIST.md`, and all
`platform_/*.py`/test imports.

**You must manually delete the old `platform/` folder** — see the top
of this document — the tooling available cannot delete files itself.

## Explicitly NOT done this sprint

- No real metrics export mechanism (`09_Deployment_Guide.md` section
  11 mentions "Metrics phải có endpoint hoặc export mechanism rõ") —
  there's no HTTP server to expose a `/metrics` endpoint from, and no
  metrics-collection code exists anywhere in this codebase yet. Not
  fabricated; flagged as a real gap rather than papered over.
- No CI pipeline file (e.g. GitHub Actions) — nothing in the docs
  pack specifies a required CI platform, and building one wasn't
  explicitly asked for.
- No secret manager integration — `HMIP_SECRET_PROVIDER` is
  documented as an env var and referenced in the K8s manifests'
  comments, but `core/config.py`'s secret resolution remains the
  Sprint-1 pass-through stub.

## Open questions

Carried over, still unresolved, still not blocking: what
`runtime_version`/`kernel_version` *values* should actually mean (the
mechanism for overriding them is now real, per above), the
`PersistentLineageTracer` default path (`SPRINT_4_STATUS.md`), and
Python 3.14.5 vs ADR-009's stated "3.12" for **local dev** — the
container itself is unambiguously pinned to 3.12 now, so this only
affects your local `uv venv`, not what ships.

## Definition of Done — Sprint 6

Confirmed on the target machine on 2026-08-04, after the
`platform/` → `platform_/` rename and manual deletion of the orphaned
folder:

```
uv run ruff check .    -> All checks passed!
uv run mypy .           -> Success: no issues found in 38 source files
uv run pytest -v        -> 257 passed
```

- [x] Old `platform/` folder deleted.
- [x] Ruff/mypy/pytest all clean — the platform-naming risk that broke
      collection is fully resolved.
- [ ] Container builds successfully — **not yet verified**, optional
      for this round if Docker isn't set up on your machine; run
      `docker build -t hmip:dev .` and `docker run --rm hmip:dev` when
      convenient.
- [ ] Health/readiness checks pass in-container — depends on the
      container build above.
- [ ] Observability works (structured JSON logs visible in
      `docker logs`/stdout) — depends on the container build above.
- [x] Release process documented (`deployment/RELEASE_CHECKLIST.md`).

**Sprint 6's code-level DoD is met.** The container-build verification
items remain open only because they require Docker locally — not a
code gap.

## Next (only after this Sprint's DoD is confirmed)

This was the last sprint named in `10_Project_Backlog.md`'s explicit
list. Remaining candidates from the open-questions backlog across all
status docs: wiring ontology into PRC-001, picking a
lineage-persistence default path, and deciding the actual
`runtime_version`/`kernel_version` values.
