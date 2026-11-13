# Contributing to NexusOS

## Git workflow

* `main` — released, reviewed state. Never commit to it directly.
* `develop` — integration branch for the next release (create it from `main` when needed).
* `feature/<topic>` — all work happens here, e.g. `feature/sddm-theme`.
* `fix/<topic>`, `docs/<topic>` — small fixes and documentation.

Rules:

1. Branch from the latest `develop` (or `main` until `develop` exists).
2. Never force-push shared branches or rewrite published history.
3. Open a pull request; CI must pass and one maintainer must review.
4. Maintainers merge; contributors do not merge their own PRs.
5. Releases and ISO uploads happen only from reviewed tags (see `docs/release-process.md`).

### Commit messages

[Conventional Commits](https://www.conventionalcommits.org/):

```
feat(cli): add `nexus infra containers --running`
fix(branding): restore Ubuntu os-release on abort-install
docs: explain the XDG defaults directory
build|test|chore|refactor|ci: ...
```

## Development setup

```bash
scripts/development/setup.sh && . .venv/bin/activate
scripts/development/validate.sh
```

## Guidelines

* **One implementation**: every operation lives in `command-center/backend/nexus_core`.
  The CLI (`packages/nexus-cli`) and Command Center modules only render and confirm.
* **Python**: ≥ 3.11, type hints, `ruff check` / `ruff format` clean. Every new operation
  needs tests, including "dependency missing" and invalid-input paths.
* **Command Center**: one module = `module.json` + `controller.py` + `Page.qml`; QML calls
  controller slots only (no commands from QML); blocking work goes through `self.run(...)`;
  timers only in `poll_interval_ms` controllers; use `Nexus.Design` components; run
  `nexus-center --smoke` (must report no QML warnings).
* **Privileged operations**: add them to `nexus_agent/ops.py` with a Pydantic model
  (`extra="forbid"`), a polkit action in `org.nexusos.agent.policy`, and tests for
  unauthorized and invalid requests. Never accept command lines or arbitrary paths.
* **Never** run privileged operations implicitly. Show the command, ask for
  confirmation, refuse without a TTY.
* **Never** print environment variables, tokens or credential files in diagnostics.
* **Shell**: `set -euo pipefail`, `shellcheck` clean, idempotent where practical,
  no destructive disk commands (`mkfs`, `wipefs`, `dd of=/dev/…`, `parted`).
* **Debian packaging**: debhelper compat 13, `Rules-Requires-Root: no`, lintian
  without errors, maintainer scripts symmetrical (anything added on install is
  removed on removal). Do not ship files in `/etc/skel` or overwrite files owned
  by other packages — use diversions or separate directories.
* **Manifests**: only add package names verified in resolute
  (`validate_manifests.py --check-archive`); otherwise list them under `external`.
* **Branding**: edit SVG masters and `design-tokens.json` only; never commit
  rasters. Regenerate KDE colours with `scripts/build/generate_theme_colors.py`.
* **Honesty**: document incomplete functionality; never claim something works
  until it has been built and tested.
