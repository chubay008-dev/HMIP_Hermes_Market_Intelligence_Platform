"""HMIP platform package: bootstrap entrypoints, diagnostics, and other
environment/startup tooling. No business logic.

NOTE: this package was named `platform/` through Sprint 6, per
14_Repository_File_Mapping.md section 7. Renamed to `platform_/` (see
ADR_010_platform_package_rename.md) after the collision with Python's
standard library `platform` module — flagged as a risk since Sprint 1
— actually broke test collection in Sprint 6 once tests started
importing from this package directly.
"""
