"""Project scaffolding for ``nexus dev create``."""

from __future__ import annotations

import re
from dataclasses import dataclass
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path
from string import Template

from nexus_cli.core import runner
from nexus_cli.core.errors import DependencyMissingError, ValidationError

PROJECT_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{0,62}$")

# Template files that are renamed on output (dotfiles cannot ship reliably in wheels).
_RENAMES = {"gitignore": ".gitignore"}

# React scaffolding follows the Vite getting-started guide (https://vite.dev/guide/).
VITE_REACT_TEMPLATE = "react-ts"
MIN_NODE_MAJOR = 20


@dataclass(frozen=True)
class TemplateInfo:
    name: str
    description: str
    requires: tuple[str, ...]
    offline: bool


TEMPLATES = (
    TemplateInfo("fastapi", "FastAPI service with health endpoint and pytest suite", ("python3",), True),
    TemplateInfo("react", "React + TypeScript app scaffolded with Vite (npm create vite)", ("node", "npm"), False),
)


def validate_project_name(name: str) -> str:
    if not PROJECT_NAME_RE.match(name):
        raise ValidationError(
            f"invalid project name {name!r}",
            hint="use 1-63 lowercase letters, digits, '-' or '_', starting with a letter",
        )
    return name


def prepare_target(parent: Path, name: str) -> Path:
    parent = parent.expanduser().resolve()
    if not parent.is_dir():
        raise ValidationError(f"parent directory does not exist: {parent}")
    target = parent / name
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise ValidationError(f"{target} already exists and is not empty")
    return target


def _walk(node: Traversable, prefix: Path = Path()) -> list[tuple[Path, Traversable]]:
    entries: list[tuple[Path, Traversable]] = []
    for child in node.iterdir():
        if child.name == "__pycache__":
            continue
        if child.is_dir():
            entries.extend(_walk(child, prefix / child.name))
        elif child.name.endswith(".tmpl"):
            entries.append((prefix / child.name[: -len(".tmpl")], child))
    return entries


def create_fastapi_project(name: str, parent: Path) -> tuple[Path, list[Path]]:
    validate_project_name(name)
    target = prepare_target(parent, name)
    root = resources.files("nexus_cli.templates").joinpath("fastapi")
    created: list[Path] = []
    target.mkdir(parents=True, exist_ok=True)
    for rel, source in sorted(_walk(root), key=lambda e: str(e[0])):
        rel = rel.with_name(_RENAMES.get(rel.name, rel.name))
        content = Template(source.read_text(encoding="utf-8")).safe_substitute(project_name=name)
        out = target / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content, encoding="utf-8")
        created.append(rel)
    return target, created


def react_command(name: str) -> list[str]:
    validate_project_name(name)
    return ["npm", "create", "vite@latest", name, "--", "--template", VITE_REACT_TEMPLATE]


def check_node() -> str:
    """Return the Node.js version, raising if Node/npm are missing or too old."""
    for program in ("node", "npm"):
        if runner.which(program) is None:
            raise DependencyMissingError(
                f"{program} not found",
                hint="install Node.js and npm: `sudo apt install nodejs npm` (development manifest)",
            )
    result = runner.run(["node", "--version"], timeout=10)
    version = result.stdout.strip().lstrip("v")
    try:
        major = int(version.split(".")[0])
    except ValueError:
        return version or "unknown"
    if major < MIN_NODE_MAJOR:
        raise DependencyMissingError(
            f"Node.js {version} is too old for current Vite releases",
            hint=f"Node.js {MIN_NODE_MAJOR}+ is required",
        )
    return version
