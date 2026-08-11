# HMIP Release Checklist

Per `09_Deployment_Guide.md` sections 9 (release flow) and 10
(operational safety rules). Work through this in order; do not skip a
step because an earlier one "looked fine".

## 1. Test gates (all must pass — see SPRINT_5_STATUS.md for how these
   are enforced)

- [ ] `uv run ruff check .` — clean.
- [ ] `uv run mypy .` — clean.
- [ ] `uv run pytest -v` — all tests pass, blended coverage >= 80%
      (enforced automatically via `pyproject.toml`'s `--cov-fail-under=80`).
- [ ] `uv run pytest -o addopts="" --cov=core.workflow_engine --cov=domains.beer.pricing --cov-fail-under=90`
      — critical-workflow coverage >= 90%.
- [ ] Workflow regression tests pass
      (`tests/workflow/test_prc_001_regression.py`).
- [ ] Chaos tests pass (`tests/chaos/`).
- [ ] Prompt evaluation tests pass against the golden datasets
      (`tests/prompt/`).

## 2. Container build

- [ ] `docker build -t hmip:<version> .` succeeds from the repo root.
- [ ] Image size is reasonable (no accidental inclusion of `.venv`,
      `tests/`, docs, or `data/`/`reports/` — check against
      `.dockerignore` if it looks large).
- [ ] `docker run --rm hmip:<version>` runs bootstrap and exits `0`.
- [ ] Confirm no secrets are baked into the image:
      `docker history hmip:<version>` and a manual scan of layers for
      anything resembling an API key, password, or token.

## 3. Smoke test

- [ ] Run the container once with `HMIP_ENV=staging` and confirm:
  - [ ] `platform_/bootstrap.py`'s report is written under the mounted
        `reports/` volume, with `"status": "SUCCESS"`.
  - [ ] `python -m platform_.health` (inside the container) exits `0`.
  - [ ] `python -m platform_.readiness` (inside the container) exits
        `0` **after** bootstrap completes — and `1` if run before
        bootstrap, or after a bootstrap failure.
- [ ] Manually exercise PRC-001 end-to-end in the container (or via
      the equivalent `uv run` command) and confirm a lineage record
      exists for every task, including any `rollback:*` entries if a
      failure was deliberately injected.

## 4. Staging deployment

- [ ] Deploy `deployment/kubernetes/job.yaml` (or
      `deployment/docker-compose.yml` for a simpler target) to
      staging.
- [ ] Confirm the Job completes successfully (`kubectl get jobs` /
      `docker compose logs`).
- [ ] Review the persisted `reports/bootstrap_*.json` for the staging
      run — no unexpected `FAILED` steps.

## 5. Promote to production

- [ ] Tag the image with the release version
      (`docker tag hmip:<version> <registry>/hmip:<version>`).
- [ ] Push to the target registry.
- [ ] Update `deployment/kubernetes/job.yaml`'s `image:` field (or
      your deployment tooling's equivalent) to the new tag.
- [ ] Apply to production.
- [ ] Confirm the production run's `reports/bootstrap_*.json` shows
      `"status": "SUCCESS"`.

## 6. Operational safety rules (must hold at every step above, not
   just checked once)

Per `09_Deployment_Guide.md` section 10 — these are **must-not** gates,
not optional guidance:

- [ ] Deployment must NOT proceed if any test gate in section 1 failed.
- [ ] Container must NOT run as a process that silently swallows a
      bootstrap failure — confirm the container's exit code is
      non-zero on failure (already enforced by
      `platform_/bootstrap.py::main()`'s return value, but verify it
      propagates through your deployment tooling's own health
      evaluation).
- [ ] No secret value may appear in `deployment/kubernetes/configmap.yaml`,
      any `docker-compose.yml` `environment:` block, image layers, or
      logs. Secrets belong in a Secret resource / secret manager only
      (not yet implemented — see `.env.example`'s `HMIP_SECRET_PROVIDER`
      note).
- [ ] Rollback plan confirmed before promoting: keep the previous
      image tag deployed/available so you can revert the `image:`
      field immediately if the new release's smoke test fails in
      production.

## Known gaps this checklist does not cover (see SPRINT_*_STATUS.md files)

- No live LLM invocation exists yet (extraction/decisioning are
  deterministic — see `SPRINT_3_PRC001_STATUS.md`).
- Compensation orchestration exists and is tested
  (`SPRINT_5_STATUS.md`), but every PRC-001 task's rollback is
  currently a no-op — there is no real external side effect to verify
  gets undone in staging/production yet.
- Lineage defaults to in-memory (`InMemoryLineageTracer`) unless a
  caller explicitly wires in `PersistentLineageTracer` with an
  explicit path — there is still no agreed default path
  (`SPRINT_4_STATUS.md`'s open question). Decide this before relying
  on lineage surviving a production container restart.
