# ADR-010: Rename `platform/` package to `platform_/`

## Status

Accepted — implemented Sprint 6 (2026-08-04).

## Context

`14_Repository_File_Mapping.md` section 7 names this package's folder
`platform/` verbatim. Every status doc since Sprint 1
(`SPRINT_1_STATUS.md`'s "Known risk" section, repeated in every
subsequent `SPRINT_*_STATUS.md`) flagged that this shadows Python's
own standard library `platform` module, and that the risk stayed
theoretical only because nothing had yet imported from this project's
`platform` package from a test file, or had one `platform/*.py` module
import from a sibling submodule.

Sprint 6 added `platform/health.py` and `platform/readiness.py`, had
`platform/bootstrap.py` import `from platform.readiness import
mark_ready`, and added the first tests importing directly from this
package. Running the real test suite produced:

```
ModuleNotFoundError: No module named 'platform.health'; 'platform' is not a package
```

for every test file importing from the package — `sys.modules
["platform"]` had already been populated with the real standard
library module (most likely by `pytest`, `coverage.py`, or another
dependency importing it internally before `tests/conftest.py`'s
`sys.path` insertion could take effect) before any of our own code got
a chance to claim that name. This is a `sys.modules` caching problem,
not a `sys.path` ordering problem — no amount of `sys.path`
manipulation in `conftest.py` can fix it once the name is cached.
Pytest reported `Interrupted: 3 errors during collection` — the entire
236-test suite failed to even start.

## Decision

Rename the package from `platform/` to `platform_/` (trailing
underscore — chosen by the project owner over `hmip_platform`/
`runtime_platform` for minimal diff from the mapping doc's original
name). This deviates from `14_Repository_File_Mapping.md` section 7's
literal text — a deliberate, documented deviation from the source
mapping doc, not a silent one, made necessary by a confirmed runtime
bug rather than a style preference.

Every reference to the old name was updated in the same pass:
`pyproject.toml` (`[tool.setuptools.packages.find]`'s include list,
`addopts`'s `--cov=`, `[tool.coverage.run]`'s `source`), `Dockerfile`
(`COPY`, `HEALTHCHECK`, `ENTRYPOINT`), `deployment/docker-compose.yml`
(healthcheck command), `config/deployment.yaml` (`container.entrypoint`,
`health_check.command`, `readiness_check.command`),
`deployment/RELEASE_CHECKLIST.md`, and all `platform/*.py`
module-internal cross-references and docstrings.

## Consequence: the old `platform/` folder is orphaned on disk

The tools available for this rename cannot delete files. The old
`platform/__init__.py`, `bootstrap.py`, `diagnostics.py`, `health.py`,
`readiness.py` still physically exist on disk with their old, now-stale
content (still importing `from platform.readiness import ...`
internally, which would still fail the same way if anything ever
imported them again). Nothing in the codebase references them anymore
as of this ADR, but they must be deleted manually:

```powershell
Remove-Item -Recurse -Force platform
```

Do not skip this — `pyproject.toml`'s `include` list was deliberately
changed to the literal `"platform_*"` (not a `"platform*"` wildcard)
specifically so the orphaned folder doesn't get picked up by
`setuptools.packages.find` in the meantime, but it will still sit in
the working tree, `git status`, and any full-repo search until removed.

## Alternatives considered

- **Leave `platform/` as-is, work around the collision per-file** (e.g.
  `importlib`-based dynamic loading instead of `import` statements).
  Rejected: every prior status doc already committed to "this needs an
  ADR to rename, not a workaround" once the risk materialized — reversing
  that now would be inconsistent, and a workaround only patches the
  specific failure observed today, not the underlying name collision
  that could resurface differently later (e.g. in a future container
  base image where `sys.modules` gets populated even earlier).
- **`hmip_platform/`**: more collision-proof for the future, more
  visually distinct from the original `platform/` name. Not chosen —
  project owner preferred the minimal-diff option.
