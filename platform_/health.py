"""Health check.

09_Deployment_Guide.md section 8: "kiểm tra process còn sống, kiểm
tra dependency cơ bản, không thực hiện work nặng."

This project has no long-running HTTP server — it is a run-to-
completion CLI (bootstrap, optionally execute a workflow, exit; see
`platform_/bootstrap.py`). Health/readiness here are CLI exit-code
checks meant to be invoked as a container `HEALTHCHECK CMD` (or a
Kubernetes probe's `exec` command), not HTTP endpoints. If a
long-running service model is ever added, these should become real
HTTP endpoints instead — noted honestly rather than faked.
"""

from __future__ import annotations

from platform_.diagnostics import run_diagnostics


def check_health() -> bool:
    """Minimal liveness check: the interpreter can run and basic
    environment diagnostics pass (currently just the Python version
    check — see `platform_/diagnostics.py`). Deliberately does NOT
    check bootstrap/config/registry state — that's `readiness`'s job,
    not liveness's."""
    return all(result.passed for result in run_diagnostics())


def main() -> int:
    healthy = check_health()
    print("HEALTHY" if healthy else "UNHEALTHY")
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
