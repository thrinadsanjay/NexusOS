"""Global search / command palette index.

Results point at pages, settings, packages, SSH profiles, containers, applications,
gateway routes, files and supported actions. Selecting an action only *proposes* it:
administrative or destructive actions always require confirmation in the UI/CLI.
Nothing is ever executed because it matched a query.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel

from nexus_core import settings
from nexus_core.log import get_logger

log = get_logger("search")

Kind = Literal["page", "setting", "action", "package", "ssh", "container", "app", "route", "file"]


class Result(BaseModel):
    kind: Kind
    title: str
    subtitle: str = ""
    target: str  # page id, kcm, action id, package name, profile id, ...
    requires_confirmation: bool = False
    score: int = 0


PAGES = [
    ("overview", "Overview"),
    ("packages", "Software Center"),
    ("settings", "System Settings"),
    ("terminal", "Terminal & SSH"),
    ("containers", "Containers"),
    ("applications", "Nexus Applications"),
    ("gateway", "Gateway"),
    ("storage", "Storage"),
    ("network", "Network"),
    ("files", "Files"),
    ("ai", "Local AI"),
    ("notifications", "Notifications"),
    ("security", "Security"),
    ("activity", "Activity History"),
]


class Action(BaseModel):
    id: str
    title: str
    keywords: list[str]
    dangerous: bool = True


# Supported quick actions. Their handlers live in the frontends and always confirm first.
ACTIONS = [
    Action(
        id="service.restart:nginx.service",
        title="Restart NGINX",
        keywords=["restart nginx", "nginx restart", "reload web"],
    ),
    Action(id="service.restart:docker.service", title="Restart Docker Engine", keywords=["restart docker"]),
    Action(id="service.start:ollama.service", title="Start Ollama", keywords=["start ollama", "ai start"]),
    Action(id="service.stop:ollama.service", title="Stop Ollama", keywords=["stop ollama", "ai stop"]),
    Action(
        id="packages.update", title="Refresh package indexes", keywords=["apt update", "update packages", "refresh"]
    ),
    Action(id="packages.upgrade", title="Upgrade installed packages", keywords=["upgrade", "apt upgrade", "updates"]),
    Action(id="gateway.apply", title="Apply gateway configuration", keywords=["apply gateway", "nginx apply"]),
    Action(id="gateway.test", title="Test NGINX configuration", keywords=["nginx -t", "test nginx"], dangerous=False),
    Action(
        id="terminal.open", title="Open a local terminal", keywords=["terminal", "shell", "konsole"], dangerous=False
    ),
    Action(id="health.run", title="Run system health check", keywords=["health", "check system"], dangerous=False),
]


def _score(query: str, *fields: str) -> int:
    q = query.lower()
    best = 0
    for i, field in enumerate(fields):
        f = field.lower()
        if not f:
            continue
        if f == q:
            best = max(best, 100 - i)
        elif f.startswith(q):
            best = max(best, 80 - i)
        elif q in f:
            best = max(best, 60 - i)
        elif all(word in f for word in q.split()):
            best = max(best, 40 - i)
    return best


Provider = Callable[[str], list[Result]]


def static_results(query: str) -> list[Result]:
    out = []
    for pid, title in PAGES:
        s = _score(query, title, pid)
        if s:
            out.append(Result(kind="page", title=title, subtitle="Command Center", target=pid, score=s + 5))
    for entry in settings.CATALOG:
        s = _score(query, entry.title, *entry.keywords, entry.category)
        if s:
            out.append(
                Result(
                    kind="setting",
                    title=entry.title,
                    subtitle=entry.category,
                    target=entry.kcm or f"native:{entry.native}",
                    score=s,
                )
            )
    for action in ACTIONS:
        s = _score(query, action.title, *action.keywords)
        if s:
            out.append(
                Result(
                    kind="action",
                    title=action.title,
                    subtitle="Action (asks for confirmation)" if action.dangerous else "Action",
                    target=action.id,
                    requires_confirmation=action.dangerous,
                    score=s + 10,
                )
            )
    return out


def search(query: str, providers: list[Provider] | None = None, limit: int = 30) -> list[Result]:
    query = query.strip()
    if len(query) < 2:
        return []
    results = static_results(query)
    for provider in providers or []:
        try:
            results += provider(query)
        except Exception as exc:
            log.debug("search provider failed: %s", exc)
    return sorted(results, key=lambda r: -r.score)[:limit]


# ----------------------------------------------------------------- optional providers
def ssh_provider(query: str) -> list[Result]:
    from nexus_core.ssh import profiles

    return [
        Result(
            kind="ssh",
            title=p.name,
            subtitle=f"SSH {p.user}@{p.host}",
            target=p.id,
            score=_score(query, p.name, p.host, p.group, *p.tags),
        )
        for p in profiles.list_profiles()
        if _score(query, p.name, p.host, p.group, *p.tags)
    ]


def apps_provider(query: str) -> list[Result]:
    from nexus_core.apps import registry

    return [
        Result(kind="app", title=a.name, subtitle=a.summary, target=a.id, score=_score(query, a.name, a.id))
        for a in registry.load_registry().values()
        if _score(query, a.name, a.id, a.category)
    ]


def packages_provider(query: str) -> list[Result]:
    from nexus_core import packages

    if len(query) < 3:
        return []
    return [
        Result(
            kind="package",
            title=e.name,
            subtitle=("installed · " if e.installed_version else "") + e.summary,
            target=e.name,
            score=_score(query, e.name) or 20,
        )
        for e in packages.search(query, limit=8)
    ]


def files_provider(query: str) -> list[Result]:
    from nexus_core import files

    return [
        Result(kind="file", title=p.rsplit("/", 1)[-1], subtitle=p, target=p, score=15)
        for p in files.search(query, limit=8)
    ]


DEFAULT_PROVIDERS: list[Provider] = [ssh_provider, apps_provider, packages_provider, files_provider]
