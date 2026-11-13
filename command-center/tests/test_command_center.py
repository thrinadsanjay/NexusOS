"""Command Center: module structure, design system, QML validity, startup, navigation, budgets."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULES = ROOT / "command-center" / "modules"
SIDEBAR = [
    "overview",
    "packages",
    "settings",
    "terminal",
    "containers",
    "applications",
    "gateway",
    "storage",
    "network",
    "files",
    "ai",
    "notifications",
    "security",
    "activity",
]
TITLES = [
    "Overview",
    "Software Center",
    "System Settings",
    "Terminal & SSH",
    "Containers",
    "Nexus Applications",
    "Gateway",
    "Storage",
    "Network",
    "Files",
    "Local AI",
    "Notifications",
    "Security",
    "Activity History",
]

try:
    import PySide6  # noqa: F401

    HAVE_PYSIDE = True
except ImportError:
    HAVE_PYSIDE = False


def _qt_loads() -> bool:
    if not HAVE_PYSIDE:
        return False
    proc = subprocess.run([sys.executable, "-c", "import PySide6.QtGui"], capture_output=True, check=False)
    return proc.returncode == 0


GUI = pytest.mark.skipif(not _qt_loads(), reason="PySide6 with QtGui (libEGL/libGL) not available")


def test_modules_match_navigation_spec():
    manifests = sorted((json.loads(p.read_text()) for p in MODULES.glob("*/module.json")), key=lambda m: m["order"])
    assert [m["id"] for m in manifests] == SIDEBAR
    assert [m["title"] for m in manifests] == TITLES
    for m in manifests:
        d = MODULES / m["id"]
        assert (d / "Page.qml").is_file() and (d / "controller.py").is_file()


def test_pages_never_run_commands_from_qml():
    """QML only calls controller slots: no dynamic code, no network requests, no process spawning."""
    forbidden = re.compile(r"Qt\.createQmlObject|XMLHttpRequest|Qt\.include|eval\(")
    for page in [*MODULES.glob("*/Page.qml"), ROOT / "command-center/frontend/qml/Main.qml"]:
        assert not forbidden.search(page.read_text()), page


def test_theme_tokens_match_design_tokens():
    tokens = json.loads((ROOT / "branding/design-tokens.json").read_text())["color"]
    theme = (ROOT / "command-center/frontend/qml/Nexus/Design/Theme.qml").read_text()
    dark = theme.split("darkPalette")[1].split("lightPalette")[0]
    mapping = {
        "background": "background-primary",
        "backgroundSecondary": "background-secondary",
        "accent": "accent-primary",
        "accentSecondary": "accent-secondary",
        "text": "text-primary",
        "textSecondary": "text-secondary",
        "surface": "surface",
        "surfaceElevated": "surface-elevated",
        "border": "border",
    }
    for qml_name, token in mapping.items():
        assert f'property color {qml_name}: "{tokens[token]}"' in dark, qml_name
    assert "lightPalette" in theme and "App.dark" in theme


def test_design_system_components_present():
    qmldir = (ROOT / "command-center/frontend/qml/Nexus/Design/qmldir").read_text()
    for component in (
        "NxButton",
        "NxTextField",
        "NxConfirmDialog",
        "NxTable",
        "NxStatusBadge",
        "NxEmptyState",
        "NxErrorState",
        "NxLoading",
        "NxCard",
        "NxPageHeader",
        "NxBanner",
        "NxTabBar",
    ):
        assert component in qmldir


@pytest.mark.skipif(shutil.which("pyside6-qmllint") is None, reason="pyside6-qmllint not installed")
def test_qmllint_reports_no_errors():
    files = [str(p) for p in (ROOT / "command-center").rglob("*.qml")]
    proc = subprocess.run(
        ["pyside6-qmllint", "-I", str(ROOT / "command-center/frontend/qml"), *files],
        capture_output=True,
        text=True,
        check=False,
    )
    errors = [ln for ln in (proc.stdout + proc.stderr).splitlines() if ln.startswith("Error:")]
    assert not errors, errors[:10]


@pytest.mark.skipif(not HAVE_PYSIDE, reason="PySide6 not installed")
def test_controllers_import_and_construct():
    from nexus_center.app import discover_modules, load_controller_class
    from nexus_center.tasks import TaskRunner
    from PySide6.QtCore import QCoreApplication

    app = QCoreApplication.instance() or QCoreApplication([])
    runner = TaskRunner()
    for meta in discover_modules(MODULES):
        ctrl = load_controller_class(meta)(runner, None)
        assert hasattr(ctrl, "refresh") and isinstance(ctrl.data, dict)
    runner.wait(3000)
    assert app is not None


@pytest.mark.skipif(not HAVE_PYSIDE, reason="PySide6 not installed")
def test_polling_only_while_visible():
    from nexus_center.app import discover_modules, load_controller_class
    from nexus_center.tasks import TaskRunner
    from PySide6.QtCore import QCoreApplication

    QCoreApplication.instance() or QCoreApplication([])
    meta = next(m for m in discover_modules(MODULES) if m["id"] == "overview")
    runner = TaskRunner()
    ctrl = load_controller_class(meta)(runner, None)
    assert not ctrl._timer.isActive()
    ctrl.activate()
    assert ctrl._timer.isActive()
    ctrl.deactivate()
    assert not ctrl._timer.isActive()
    runner.wait(5000)


def _run_center(*args: str, timeout: int = 180) -> dict:
    env = {
        **os.environ,
        "QT_QPA_PLATFORM": "offscreen",
        "PYTHONPATH": os.pathsep.join(str(ROOT / p) for p in ("command-center/backend", "command-center/frontend")),
    }
    proc = subprocess.run(
        [sys.executable, "-m", "nexus_center", *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout,
        check=False,
    )
    out = proc.stdout
    assert "{" in out, proc.stderr[-2000:]
    return json.loads(out[out.index("{") :])


@GUI
@pytest.mark.gui
def test_startup_navigation_and_no_qml_warnings():
    report = _run_center("--smoke")
    assert report["modules"] == SIDEBAR
    assert report["qml_warnings"] == []
    for module in SIDEBAR:
        assert f"page:{module}" in report["timings_ms"]


@GUI
@pytest.mark.gui
def test_resource_budgets_ci():
    """Lenient CI ceilings (shared runners, software rendering). Product budgets: docs/performance.md."""
    report = _run_center("--benchmark", "5")
    assert report["startup_to_window_ms"] < 5000
    assert report["idle_rss_mib"] < 350
    assert report["idle_cpu_percent"] < 5
    assert max(v for k, v in report["timings_ms"].items() if k.startswith("page:")) < 1500
    assert report["threads"] <= 12


def test_cli_and_center_share_one_backend():
    """No second implementation: the CLI and the Command Center import nexus_core, not each other."""
    cli = ROOT / "packages/nexus-cli/nexus_cli"
    for py in cli.rglob("*.py"):
        text = py.read_text()
        assert "subprocess.run" not in text or py.name == "runner.py", py
        assert "nexus_center" not in text
    assert not list(cli.glob("services/*.py")), "CLI services moved to nexus_core"
    assert importlib.util.find_spec("nexus_core") is not None
