"""Cleanup planning. Produces a preview; deletion of user caches is done by :func:`clean_user_path`."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from nexus_core import runner
from nexus_core.log import get_logger
from nexus_core.models import CleanupItem
from nexus_core.packages import simulate_autoremove_count

log = get_logger("cleanup")

APT_ARCHIVES = Path("/var/cache/apt/archives")

# User-owned caches that are always safe to regenerate. Paths are relative to $HOME.
USER_CACHE_DIRS: dict[str, tuple[str, str]] = {
    "thumbnails": (".cache/thumbnails", "Thumbnail cache"),
    "pip-cache": (".cache/pip", "pip download cache"),
    "npm-cache": (".npm/_cacache", "npm download cache"),
}


def dir_size(path: Path) -> int:
    """Total size of regular files below *path*, without following symlinks."""
    total = 0
    for root, _dirs, files in os.walk(path, followlinks=False):
        for name in files:
            try:
                st = os.lstat(os.path.join(root, name))
            except OSError:
                continue
            total += st.st_size
    return total


def plan_cleanup(home: Path | None = None) -> list[CleanupItem]:
    home = home or Path.home()
    items: list[CleanupItem] = []
    for item_id, (rel, description) in USER_CACHE_DIRS.items():
        path = home / rel
        if path.is_dir() and not path.is_symlink():
            items.append(
                CleanupItem(
                    id=item_id,
                    description=description,
                    reclaimable_bytes=dir_size(path),
                    privileged=False,
                    paths=[str(path)],
                )
            )

    if APT_ARCHIVES.is_dir():
        size = sum(p.stat().st_size for p in APT_ARCHIVES.glob("*.deb") if p.is_file())
        items.append(
            CleanupItem(
                id="apt-cache",
                description="Downloaded .deb package cache",
                reclaimable_bytes=size,
                privileged=True,
                command=["sudo", "apt-get", "clean"],
            )
        )

    removable = simulate_autoremove_count()
    if removable:
        items.append(
            CleanupItem(
                id="apt-autoremove",
                description=f"{removable} automatically installed packages no longer needed",
                reclaimable_bytes=None,
                privileged=True,
                command=["sudo", "apt-get", "autoremove"],
            )
        )

    if runner.which("journalctl"):
        items.append(
            CleanupItem(
                id="journal",
                description="systemd journal entries older than 14 days",
                reclaimable_bytes=None,
                privileged=True,
                command=["sudo", "journalctl", "--vacuum-time=14d"],
            )
        )
    return items


def clean_user_path(path: Path, home: Path | None = None) -> int:
    """Delete the *contents* of a user cache directory. Refuses anything outside $HOME."""
    home = (home or Path.home()).resolve()
    target = path.resolve()
    if path.is_symlink() or home not in target.parents:
        raise ValueError(f"refusing to clean {path}: not a real directory inside {home}")
    freed = 0
    for child in target.iterdir():
        try:
            if child.is_dir() and not child.is_symlink():
                freed += dir_size(child)
                shutil.rmtree(child)
            else:
                freed += child.lstat().st_size
                child.unlink()
        except OSError as exc:
            log.warning("could not remove %s: %s", child, exc)
    return freed
