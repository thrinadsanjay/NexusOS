"""Package manifests: YAML syntax, required keys, codename and package-list structure."""

from __future__ import annotations

import copy

import pytest
import yaml

from tests.conftest import REPO_ROOT, load_script

vm = load_script("scripts/validation/validate_manifests.py")
MANIFESTS = {name: yaml.safe_load((REPO_ROOT / "manifests" / f"{name}.yaml").read_text()) for name in vm.EXPECTED}


def test_all_manifests_valid(capsys):
    assert vm.main([]) == 0, capsys.readouterr().out


@pytest.mark.parametrize("name", vm.EXPECTED)
def test_codename_and_arch(name):
    dist = MANIFESTS[name]["distribution"]
    assert dist["codename"] == "resolute"
    assert str(dist["version"]) == "26.04"
    assert dist["architecture"] == "amd64"


def test_required_flags():
    assert MANIFESTS["base"]["required"] is True
    assert MANIFESTS["desktop"]["required"] is True
    for optional in ("development", "infrastructure", "ai"):
        assert MANIFESTS[optional]["required"] is False


def test_ai_is_post_install_only():
    ai = MANIFESTS["ai"]
    assert ai["policy"]["include_in_iso"] is False
    assert ai["policy"]["download_models_during_build"] is False
    assert ai["models"]["preinstalled"] == []
    names = {e["name"] for e in ai["external"]}
    assert {"ollama", "open-webui"} <= names
    all_packages = {p for m in MANIFESTS.values() for _, p in vm.package_names(m)}
    assert "ollama" not in all_packages and "open-webui" not in all_packages


def test_no_duplicates_across_manifests():
    seen: dict[str, str] = {}
    for name, data in MANIFESTS.items():
        for _, pkg in vm.package_names(data):
            assert pkg not in seen, f"{pkg} in {seen.get(pkg)} and {name}"
            seen[pkg] = name


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda m: m["distribution"].update(codename="noble"), "codename"),
        (lambda m: m.pop("packages"), "missing key 'packages'"),
        (lambda m: m["packages"]["mandatory"].append("Bad Name"), "invalid package name"),
        (lambda m: m["packages"]["mandatory"].append(m["packages"]["mandatory"][0]), "duplicate"),
        (lambda m: m["packages"].update(extras=["x"]), "unknown package groups"),
    ],
)
def test_validator_rejects_bad_manifests(mutation, message):
    data = copy.deepcopy(MANIFESTS["base"])
    mutation(data)
    errors = vm.validate_manifest("base", data)
    assert any(message in e for e in errors), errors


def test_ai_validator_rejects_models_in_iso():
    data = copy.deepcopy(MANIFESTS["ai"])
    data["policy"]["include_in_iso"] = True
    data["models"]["preinstalled"] = ["llama3"]
    errors = vm.validate_manifest("ai", data)
    assert len([e for e in errors if e.startswith("ai.")]) == 2
