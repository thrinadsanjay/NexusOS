#!/usr/bin/env python3
"""Reset file permissions in a copied checkout to the modes recorded in git.

    normalize-modes.py REPO_DIR

A checkout on a filesystem without Unix permissions (a Windows drive under WSL, /mnt/c or
/mnt/e, some network shares) reports every file as executable. Debian tooling then treats
plain configuration files such as debian/clean or debian/*.install as scripts to run and the
build fails. The package build copies the repository into its container and calls this on the
copy: tracked files get 0755 or 0644 exactly as committed; untracked files are left alone.
Never run it on a checkout you work in (it only changes permission bits, nothing else).
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys


def main(repo: str) -> int:
    try:
        out = subprocess.run(
            ["git", "-c", f"safe.directory={repo}", "-C", repo, "ls-files", "-s", "-z"],
            check=True,
            capture_output=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"normalize-modes: git metadata unavailable ({exc}); permissions left as they are", file=sys.stderr)
        return 0
    changed = 0
    for entry in out.split(b"\0"):
        if not entry:
            continue
        meta, _, path = entry.partition(b"\t")
        mode = meta.split(b" ", 1)[0]
        if mode not in (b"100755", b"100644"):
            continue  # symlinks and submodules keep what they have
        full = os.path.join(repo.encode(), path)
        try:
            current = stat.S_IMODE(os.lstat(full).st_mode)
        except FileNotFoundError:
            continue
        want = 0o755 if mode == b"100755" else 0o644
        if current != want:
            os.chmod(full, want)
            changed += 1
    print(f"normalize-modes: {changed} file permission(s) reset to the committed modes")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "."))
