#!/usr/bin/env python3
"""Validate NexusOS package manifests (manifests/*.yaml).

Structural checks (always):
  * YAML syntax, required keys, schema_version
  * Ubuntu 26.04 codename "resolute", amd64
  * package groups are lists of unique, valid Debian package names
  * no package listed in two manifests / groups
  * AI manifest keeps models and Ollama out of the ISO

Archive check (``--check-archive``, needs network or ``--index-dir``):
  * every package name exists in the resolute main+universe amd64 Packages indices
"""

from __future__ import annotations

import argparse
import lzma
import re
import sys
import urllib.request
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_DIR = REPO_ROOT / "manifests"
EXPECTED = ("base", "desktop", "development", "infrastructure", "ai")
CODENAME = "resolute"
ARCH = "amd64"
PACKAGE_GROUPS = ("mandatory", "recommended", "optional")
DEB_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9+.\-]+$")
ARCHIVE = "http://archive.ubuntu.com/ubuntu/dists/{codename}/{component}/binary-{arch}/Packages.xz"


def load(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError("top level must be a mapping")
    return data


def package_names(manifest: dict) -> list[tuple[str, str]]:
    """(group, name) pairs from the manifest's package groups."""
    pairs = []
    for group, names in (manifest.get("packages") or {}).items():
        if group in PACKAGE_GROUPS:
            pairs.extend((group, name) for name in names or [])
    return pairs


def validate_manifest(name: str, data: dict) -> list[str]:
    errors: list[str] = []
    for key in ("schema_version", "name", "description", "required", "distribution", "packages"):
        if key not in data:
            errors.append(f"missing key '{key}'")
    if errors:
        return errors
    if data["schema_version"] != 1:
        errors.append("schema_version must be 1")
    if data["name"] != name:
        errors.append(f"name '{data['name']}' does not match file name '{name}'")
    if not isinstance(data["required"], bool):
        errors.append("'required' must be a boolean")
    dist = data["distribution"]
    if dist.get("name") != "ubuntu" or str(dist.get("version")) != "26.04":
        errors.append("distribution must be ubuntu 26.04")
    if dist.get("codename") != CODENAME:
        errors.append(f"codename must be '{CODENAME}', got {dist.get('codename')!r}")
    if dist.get("architecture") != ARCH:
        errors.append(f"architecture must be '{ARCH}'")

    packages = data["packages"]
    if not isinstance(packages, dict):
        return [*errors, "'packages' must be a mapping"]
    unknown = set(packages) - set(PACKAGE_GROUPS) - {"notes"}
    if unknown:
        errors.append(f"unknown package groups: {sorted(unknown)}")
    if data["required"] and not packages.get("mandatory"):
        errors.append("required manifests need a non-empty 'mandatory' group")
    if not data["required"] and packages.get("mandatory"):
        errors.append("optional manifests must not declare 'mandatory' packages")
    seen: set[str] = set()
    for group in PACKAGE_GROUPS:
        names = packages.get(group, [])
        if names is None or not isinstance(names, list):
            errors.append(f"packages.{group} must be a list")
            continue
        for pkg in names:
            if not isinstance(pkg, str) or not DEB_NAME_RE.match(pkg):
                errors.append(f"invalid package name {pkg!r} in {group}")
            elif pkg in seen:
                errors.append(f"duplicate package {pkg!r}")
            seen.add(pkg)
    for ext in data.get("external", []) or []:
        for key in ("name", "source", "install", "reason"):
            if key not in ext:
                errors.append(f"external entry {ext.get('name', '?')!r} missing '{key}'")
        if ext.get("name") in seen:
            errors.append(f"{ext['name']!r} is both an archive package and external")

    if name == "ai":
        policy = data.get("policy") or {}
        if policy.get("include_in_iso") is not False:
            errors.append("ai.policy.include_in_iso must be false")
        if policy.get("download_models_during_build") is not False:
            errors.append("ai.policy.download_models_during_build must be false")
        if (data.get("models") or {}).get("preinstalled"):
            errors.append("ai.models.preinstalled must be empty")
    return errors


def fetch_index(index_dir: Path | None) -> set[str]:
    names: set[str] = set()
    for component in ("main", "universe"):
        if index_dir:
            raw = (index_dir / f"{component}.xz").read_bytes()
        else:
            url = ARCHIVE.format(codename=CODENAME, component=component, arch=ARCH)
            with urllib.request.urlopen(url, timeout=60) as response:
                raw = response.read()
        for line in lzma.decompress(raw).decode("utf-8", "replace").splitlines():
            if line.startswith("Package: "):
                names.add(line[len("Package: ") :].strip())
    return names


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate NexusOS package manifests.")
    parser.add_argument("--check-archive", action="store_true", help="verify names against the resolute archive")
    parser.add_argument("--index-dir", type=Path, help="directory with main.xz/universe.xz Packages indices")
    parser.add_argument("--manifest-dir", type=Path, default=MANIFEST_DIR)
    args = parser.parse_args(argv)

    failures = 0
    manifests: dict[str, dict] = {}
    for name in EXPECTED:
        path = args.manifest_dir / f"{name}.yaml"
        if not path.exists():
            print(f"FAIL {path.name}: missing")
            failures += 1
            continue
        try:
            data = load(path)
        except (yaml.YAMLError, ValueError) as exc:
            print(f"FAIL {path.name}: {exc}")
            failures += 1
            continue
        errors = validate_manifest(name, data)
        for error in errors:
            print(f"FAIL {path.name}: {error}")
        failures += len(errors)
        if not errors:
            print(f"ok   {path.name}: {len(package_names(data))} packages")
        manifests[name] = data

    owner: dict[str, str] = {}
    for name, data in manifests.items():
        for _group, pkg in package_names(data):
            if pkg in owner:
                print(f"FAIL {pkg!r} listed in both {owner[pkg]} and {name}")
                failures += 1
            owner.setdefault(pkg, name)

    if args.check_archive:
        archive = fetch_index(args.index_dir)
        print(f"archive index: {len(archive)} package names ({CODENAME} main+universe {ARCH})")
        for name, data in manifests.items():
            for group, pkg in package_names(data):
                if pkg not in archive:
                    print(f"FAIL {name}.{group}: {pkg!r} not found in {CODENAME}")
                    failures += 1
    print("manifests: " + ("OK" if failures == 0 else f"{failures} problem(s)"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
