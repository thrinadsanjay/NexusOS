#!/usr/bin/env python3
"""Scan tracked files for committed secrets (private keys, tokens, passwords in configs).

Placeholders used in documentation and tests are allow-listed explicitly.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PATTERNS = {
    "private key": re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    "AWS key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "Slack token": re.compile(r"\bxox[abpr]-[A-Za-z0-9-]{10,}"),
    "generic secret assignment": re.compile(
        r"(?i)\b(password|passwd|secret|token|api_key)\s*[:=]\s*['\"](?!\$\{|<|\*\*\*|changeme|change-me|example|dummy|test)[A-Za-z0-9+/_!-]{12,}['\"]"
    ),
}
ALLOW_FILES = {"scripts/validation/check_secrets.py"}
ALLOW_SNIPPETS = (
    "\\nAAAA\\n",
    "S3cr3t-value",
    "hunter2",
    "TOPSECRETVALUE",
    "dummy-not-a-secret",
    "abcdefghijklmnop",
    "do-not-leak",
)


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout
    return sorted(set(out.split() + untracked.split()))


def main() -> int:
    findings = []
    for rel in tracked_files():
        if rel in ALLOW_FILES or rel.endswith((".png", ".svg", ".gz")):
            continue
        path = REPO_ROOT / rel
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line_no, line in enumerate(text.splitlines(), 1):
            if any(a in line for a in ALLOW_SNIPPETS):
                continue
            for name, pattern in PATTERNS.items():
                if (pattern.search(line) and "tests/" not in rel) or (
                    name != "generic secret assignment" and pattern.search(line)
                ):
                    findings.append(f"{rel}:{line_no}: possible {name}")
    for f in findings:
        print("FAIL", f)
    print("secrets: " + ("OK" if not findings else f"{len(findings)} finding(s)"))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
