#!/usr/bin/env python3
"""Validate the Nexus application registry (applications/registry/*.yaml) against the schema.

Checks: schema (pinned SHAs, loopback ports, loopback health checks, reasons for
planned/unavailable apps), deployment files exist, compose overrides never mount the
Docker socket, and every installable app proposes a LAN-only gateway route.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "command-center" / "backend"))

from nexus_core.apps import lifecycle, registry  # noqa: E402
from nexus_core.errors import ValidationError  # noqa: E402


def main() -> int:
    root = REPO_ROOT / "applications"
    try:
        apps = registry.load_registry(root)
    except ValidationError as exc:
        print(f"FAIL {exc.message}")
        return 1
    failures = 0
    for app in apps.values():
        problems = []
        if app.deployment:
            for rel in app.deployment.files:
                text = (root / app.id / rel).read_text()
                body = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))
                if "docker.sock" in body:
                    problems.append(f"{rel} mounts the Docker socket")
                if "0.0.0.0:" in body:
                    problems.append(f"{rel} publishes on all interfaces")
        if app.installable and app.gateway:
            route = lifecycle.suggested_route(app)
            if route["access"] != "lan" or route["approved"]:
                problems.append("suggested gateway route must be LAN-only and pending approval")
        for p in problems:
            print(f"FAIL {app.id}: {p}")
        failures += len(problems)
        if not problems:
            print(f"ok   {app.id}: {app.status}")
    print("applications: " + ("OK" if not failures else f"{failures} problem(s)"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
