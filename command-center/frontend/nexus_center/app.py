"""Nexus Command Center application shell.

Startup cost is kept low: only the shell (sidebar, header, palette) is created at
launch. Module controllers are imported and instantiated the first time their page
is opened; pages are loaded by a single Loader, so hidden pages hold no QML objects.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
from collections.abc import MutableMapping
from pathlib import Path
from typing import Any

PROCESS_START = time.monotonic()

from nexus_core import notifications, search, services, settings  # noqa: E402
from nexus_core.log import get_logger  # noqa: E402
from nexus_core.store import default_store  # noqa: E402
from PySide6.QtCore import Property, QObject, QTimer, QUrl, Signal, Slot  # noqa: E402
from PySide6.QtGui import QGuiApplication, QIcon  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402

from nexus_center import __version__  # noqa: E402
from nexus_center.base import ModuleController, to_qml  # noqa: E402
from nexus_center.tasks import TaskRunner  # noqa: E402

log = get_logger("center")
HERE = Path(__file__).resolve().parent


def _first_existing(*candidates: Path) -> Path:
    for c in candidates:
        if c.exists():
            return c
    return candidates[-1]


def qml_dir() -> Path:
    return (
        Path(os.environ.get("NEXUSOS_CC_QML", ""))
        if os.environ.get("NEXUSOS_CC_QML")
        else _first_existing(Path("/usr/share/nexusos-command-center/qml"), HERE.parent / "qml")
    )


def modules_dir() -> Path:
    return (
        Path(os.environ["NEXUSOS_CC_MODULES"])
        if os.environ.get("NEXUSOS_CC_MODULES")
        else _first_existing(Path("/usr/share/nexusos-command-center/modules"), HERE.parents[1] / "modules")
    )


def discover_modules(root: Path | None = None) -> list[dict[str, Any]]:
    root = root or modules_dir()
    found = []
    for manifest in sorted(root.glob("*/module.json")):
        meta = json.loads(manifest.read_text())
        meta["dir"] = str(manifest.parent)
        meta["pageUrl"] = QUrl.fromLocalFile(str(manifest.parent / meta.get("page", "Page.qml"))).toString()
        found.append(meta)
    return sorted(found, key=lambda m: m.get("order", 100))


def load_controller_class(meta: dict[str, Any]) -> type[ModuleController]:
    path = Path(meta["dir"]) / meta.get("controller", "controller.py")
    spec = importlib.util.spec_from_file_location(f"nexus_center_module_{meta['id']}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load module controller {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, meta.get("class", "Controller"))


class AppController(QObject):
    themeChanged = Signal()
    preferencesChanged = Signal()
    unreadChanged = Signal()
    searchChanged = Signal()
    pageTimed = Signal(str, float)
    toastRequested = Signal(str, str)
    navigateRequested = Signal(str, str)

    def __init__(self, tasks: TaskRunner, modules: list[dict[str, Any]]) -> None:
        super().__init__()
        self.tasks = tasks
        self._modules = modules
        self._controllers: dict[str, ModuleController] = {}
        self._results: list[dict] = []
        self._unread = 0
        self._search_job = 0
        self.timings: dict[str, float] = {}
        store = default_store()
        self._dark = bool(store.get_setting("ui.dark", True))
        self._interval = int(store.get_setting("ui.monitoring_interval_ms", 5000))
        self._unread_timer = QTimer(self)
        self._unread_timer.timeout.connect(self.refreshUnread)
        self._unread_timer.start(60_000)  # cheap SQLite count once a minute
        QTimer.singleShot(0, self.refreshUnread)

    # ------------------------------------------------------------ theme / preferences
    def _get_dark(self) -> bool:
        return self._dark

    def _set_dark(self, value: bool) -> None:
        if value != self._dark:
            self._dark = value
            default_store().set_setting("ui.dark", value)
            self.themeChanged.emit()

    dark = Property(bool, _get_dark, _set_dark, notify=themeChanged)

    def _get_interval(self) -> int:
        return self._interval

    def _set_interval(self, value: int) -> None:
        value = max(1000, min(int(value), 60_000))
        self._interval = value
        default_store().set_setting("ui.monitoring_interval_ms", value)
        self.preferencesChanged.emit()

    monitoringInterval = Property(int, _get_interval, _set_interval, notify=preferencesChanged)

    @property
    def monitoring_interval_ms(self) -> int:
        return self._interval

    @Property(str, constant=True)
    def version(self) -> str:
        return __version__

    @Property("QVariantList", constant=True)
    def modules(self) -> list:
        return [{k: v for k, v in m.items() if k != "dir"} for m in self._modules]

    # ------------------------------------------------------------ module host
    @Slot(str, result=QObject)
    def controller(self, module_id: str) -> QObject | None:
        if module_id not in self._controllers:
            meta = next((m for m in self._modules if m["id"] == module_id), None)
            if meta is None:
                return None
            started = time.monotonic()
            try:
                cls = load_controller_class(meta)
                ctrl = cls(self.tasks, self)
            except Exception as exc:
                log.exception("module %s failed to load", module_id)
                self.toastRequested.emit("error", f"{meta.get('title', module_id)} failed to load: {exc}")
                return None
            ctrl.toast.connect(self.toastRequested)
            self._controllers[module_id] = ctrl
            self.timings[f"controller:{module_id}"] = round((time.monotonic() - started) * 1000, 1)
        return self._controllers[module_id]

    @Slot(str, float)
    def recordPageLoad(self, module_id: str, ms: float) -> None:
        self.timings[f"page:{module_id}"] = round(ms, 1)
        self.pageTimed.emit(module_id, ms)

    # ------------------------------------------------------------ notifications
    def _get_unread(self) -> int:
        return self._unread

    unread = Property(int, _get_unread, notify=unreadChanged)

    @Slot()
    def refreshUnread(self) -> None:
        self._unread = notifications.unread_count()
        self.unreadChanged.emit()

    # ------------------------------------------------------------ global search
    def _get_results(self) -> list:
        return self._results

    searchResults = Property("QVariantList", _get_results, notify=searchChanged)

    @Slot(str)
    def search(self, query: str) -> None:
        quick = [to_qml(r) for r in search.search(query)]  # static index: instant
        self._results = quick
        self.searchChanged.emit()
        if len(query.strip()) < 2:
            return
        token = self._search_job = self._search_job + 1

        def slow() -> list:
            return [to_qml(r) for r in search.search(query, search.DEFAULT_PROVIDERS)]

        def done(results: list) -> None:
            if token == self._search_job:
                self._results = results
                self.searchChanged.emit()

        self.tasks.submit(slow, done)

    @Slot(str)
    def openSetting(self, kcm: str) -> None:
        try:
            settings.open_kcm(kcm)
        except Exception as exc:
            self.toastRequested.emit("error", str(exc))

    @Slot(str)
    def runAction(self, action_id: str) -> None:
        """Run a confirmed palette action (the QML side always confirms dangerous ones first)."""
        kind, _, arg = action_id.partition(":")

        def fn() -> str:
            if kind in ("service.restart", "service.start", "service.stop"):
                services.control(arg, kind.split(".")[1])  # type: ignore[arg-type]
                return f"{arg}: {kind.split('.')[1]} requested"
            return ""

        if kind.startswith("service."):
            self.tasks.submit(
                fn,
                lambda msg: self.toastRequested.emit("success", msg),
                lambda m, h: self.toastRequested.emit("error", m),
            )
        else:
            target = {
                "packages.update": "packages",
                "packages.upgrade": "packages",
                "gateway.apply": "gateway",
                "gateway.test": "gateway",
                "terminal.open": "terminal",
                "health.run": "overview",
            }.get(kind)
            if target:
                self.navigateRequested.emit(target, kind)

    @Slot(str, result=str)
    def resourceSnapshot(self, _unused: str = "") -> str:
        return json.dumps(resource_usage())


def resource_usage() -> dict[str, float]:
    status = Path("/proc/self/status").read_text()
    rss = next(int(line.split()[1]) for line in status.splitlines() if line.startswith("VmRSS:"))
    stat = Path("/proc/self/stat").read_text().rsplit(")", 1)[1].split()
    ticks = os.sysconf("SC_CLK_TCK")
    cpu = (int(stat[11]) + int(stat[12])) / ticks
    threads = int(stat[17])
    return {"rss_mib": round(rss / 1024, 1), "cpu_seconds": round(cpu, 3), "threads": threads}


def configure_platform_theme(env: MutableMapping[str, str]) -> None:
    """Use Qt's generic platform theme unless the user opts in to the desktop's one.

    The Command Center draws every control with Nexus.Design, so the KDE platform theme
    (plasma-integration) only adds file dialogs and palette hints: measured on Plasma 6.6
    Wayland it costs ~93 MiB RSS and 9 threads (see docs/performance.md).
    ``NEXUS_CENTER_PLATFORMTHEME=kde`` (any Qt platform theme name, or ``desktop`` for the
    session default) restores native file dialogs.
    """
    choice = env.get("NEXUS_CENTER_PLATFORMTHEME", "").strip() or "generic"
    if choice != "desktop":  # "desktop": keep whatever the session exported
        env["QT_QPA_PLATFORMTHEME"] = choice


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nexus-center", description="Nexus Command Center")
    parser.add_argument("--page", default="overview", help="module to open first")
    parser.add_argument(
        "--benchmark",
        type=float,
        metavar="SECONDS",
        help="measure startup, page loads and idle usage, print JSON and exit",
    )
    parser.add_argument("--smoke", action="store_true", help="open every module once, report errors, exit")
    parser.add_argument(
        "--no-visit",
        action="store_true",
        help="with --benchmark: stay on --page (measures a plain launch instead of all modules)",
    )
    parser.add_argument("--screenshots", metavar="DIR", help="with --smoke: save a PNG of every page into DIR")
    parser.add_argument("--version", action="version", version=f"nexus-center {__version__}")
    args = parser.parse_args(argv)

    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    configure_platform_theme(os.environ)
    app = QGuiApplication(sys.argv[:1])
    app.setApplicationName("Nexus Command Center")
    app.setOrganizationName("NexusOS")
    app.setDesktopFileName("org.nexusos.CommandCenter")
    app.setWindowIcon(QIcon.fromTheme("nexusos-command-center"))

    warnings: list[str] = []
    from PySide6.QtCore import QtMsgType, qInstallMessageHandler

    def handler(mode: QtMsgType, _context: object, message: str) -> None:
        if mode in (QtMsgType.QtWarningMsg, QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
            warnings.append(message)
        sys.stderr.write(message + "\n") if os.environ.get("NEXUS_CENTER_DEBUG") else None

    qInstallMessageHandler(handler)

    tasks = TaskRunner()
    controller = AppController(tasks, discover_modules())
    engine = QQmlApplicationEngine()
    engine.addImportPath(str(qml_dir()))
    engine.rootContext().setContextProperty("App", controller)
    engine.rootContext().setContextProperty("InitialPage", args.page)
    engine.rootContext().setContextProperty("SmokeMode", bool(args.smoke or args.benchmark))
    icon = _first_existing(
        Path("/usr/share/icons/hicolor/scalable/apps/nexusos-command-center.svg"),
        HERE.parents[2] / "branding" / "icons" / "nexusos-command-center.svg",
    )
    engine.rootContext().setContextProperty("AppIconUrl", QUrl.fromLocalFile(str(icon)).toString())
    engine.load(QUrl.fromLocalFile(str(qml_dir() / "Main.qml")))
    if not engine.rootObjects():
        sys.stderr.write("failed to load Main.qml\n" + "\n".join(warnings) + "\n")
        return 1
    window = engine.rootObjects()[0]
    startup_ms = round((time.monotonic() - PROCESS_START) * 1000, 1)
    controller.timings["startup_to_window_ms"] = startup_ms

    if args.smoke or args.benchmark:
        ids = [m["id"] for m in controller._modules]
        idle_seconds = args.benchmark or 0.5
        state = {"index": 0}

        shots = Path(args.screenshots) if args.screenshots else None
        if shots:
            shots.mkdir(parents=True, exist_ok=True)

        def visit_next() -> None:
            if shots and state["index"] > 0:
                try:
                    from PySide6.QtCore import Q_ARG, QMetaObject

                    target = str(shots / f"{state['index']:02d}-{ids[state['index'] - 1]}.png")
                    QMetaObject.invokeMethod(window, "capture", Q_ARG("QVariant", target))
                except Exception as exc:
                    warnings.append(f"screenshot failed: {exc}")
            if state["index"] < len(ids):

                def go() -> None:
                    window.setProperty("currentPage", ids[state["index"]])
                    state["index"] += 1
                    QTimer.singleShot(1500 if shots else 300, visit_next)

                QTimer.singleShot(600 if shots and state["index"] > 0 else 0, go)  # let async grabs finish
            else:
                window.setProperty("currentPage", "overview")
                QTimer.singleShot(1000, measure_idle)

        def measure_idle() -> None:
            before = resource_usage()
            t0 = time.monotonic()

            def finish() -> None:
                after = resource_usage()
                elapsed = time.monotonic() - t0
                report = {
                    "version": __version__,
                    "startup_to_window_ms": startup_ms,
                    "timings_ms": controller.timings,
                    "idle_window_s": round(elapsed, 1),
                    "idle_cpu_percent": round(100 * (after["cpu_seconds"] - before["cpu_seconds"]) / elapsed, 2),
                    "idle_rss_mib": after["rss_mib"],
                    "threads": after["threads"],
                    "qml_warnings": warnings,
                    "modules": ids,
                }
                print(json.dumps(report, indent=2))
                tasks.wait(3000)
                app.exit(1 if (args.smoke and warnings) else 0)

            QTimer.singleShot(int(idle_seconds * 1000), finish)

        if args.no_visit and args.benchmark:
            ids = [args.page]
            QTimer.singleShot(1000, measure_idle)
        else:
            QTimer.singleShot(200, visit_next)
    code = app.exec()
    tasks.wait(3000)
    return code
