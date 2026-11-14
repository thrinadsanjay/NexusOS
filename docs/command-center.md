# Nexus Command Center

`nexus-center` (package `nexusos-command-center`) is the native NexusOS management
application: Qt 6 / QML (PySide6) over the shared Python backend `nexus_core`. It is
installed by default (`nexusos-desktop` depends on it), runs as the logged-in user, and
needs no browser, no web server, no Electron and no Node.js.

Status legend: **Implemented** = code exists and is exercised by automated tests ·
**Tested** = additionally verified end-to-end in a disposable Ubuntu 26.04 container
(`scripts/validation/integration-container.sh`) or in a real Plasma 6.6 Wayland session
with systemd and polkit (`scripts/validation/plasma-session-container.sh`) ·
**Experimental** = implemented but not yet verified on a real Plasma session or real
hardware · **Planned** · **Unsupported**.

## Architecture

```
QML pages (modules/<id>/Page.qml)  ──slots/props──►  module controllers (modules/<id>/controller.py)
        │                                                     │  background TaskRunner (4 threads, idle-expiring)
        │ Nexus.Design (Theme, NxButton, NxTable, …)          ▼
        ▼                                               nexus_core  (same code as the `nexus` CLI)
   Main.qml shell: sidebar · header · palette             │            │                 │
                                                          │ polkit-protected services    └─► nexusos-management-agent
                                                          │ (systemd, udisks2, NetworkManager,     (socket-activated, polkit, audited)
                                                          │  hostnamed, timedated) used directly        APT · gateway · SMART · firewall
```

* **Lazy loading** — only the shell is created at start. A module's controller is
  imported the first time its page opens; pages are loaded by a single `Loader`, so a
  hidden page holds no QML objects.
* **Polling only while visible** — controllers get `activate()`/`deactivate()`; timers run
  only for the visible page (Overview: user interval, default 5 s; Containers: 10 s).
  `Sampler` computes CPU/network rates from two `/proc` reads; no monitoring daemon.
* **No permanent background services** — the agent is socket-activated and exits after
  120 s idle. The Command Center starts nothing (no Docker, Ollama or Compose apps).
* **Bounded state** — one SQLite file (`~/.local/share/nexusos/command-center.db`, 0600)
  with row limits: activity 5,000, notifications 1,000, SSH history 500, chat 20,000.
* **Failure isolation** — a module that fails to load shows a toast; Docker/Ollama/app
  failures surface as page-level error or empty states, never crash the shell.

## Modules

| # | Module | Backend | Status |
|---|--------|---------|--------|
| 1 | Overview (operations dashboard) | `dashboard`, `hardware`, `metrics`, `storage`, `packages` | **Tested** on Plasma Wayland with real systemd/APT data: 8 tiles with sparklines, hardware spec cards (CPU, memory modules, GPUs, drives) on (i) hover/click, attention list, 24 h chart (sysstat or session), services, infrastructure, activity, sar history, backups, certificates |
| 2 | Software Center | `packages` + agent `apt.*` | **Tested** (search 88k packages, plans, real install/remove via agent, progress, lock, cancel before dpkg) |
| 3 | System Settings | `settings`, `services` + KDE KCMs | **Tested** on Plasma 6.6: catalogue checked against `kcmshell6 --list`, KCMs open, missing ones name their package; service control refused without polkit authentication |
| 4 | Terminal & SSH | `terminal`, `ssh.*` | **Tested**: local and SSH sessions open as Konsole tabs with the Nexus profile on Plasma; KDE Wallet storage and SFTP against a real server **Experimental** |
| 5 | Containers | `docker`, `compose` | Implemented (Engine API mocked in tests; CLI against a live daemon) |
| 6 | Nexus Applications | `apps.registry`, `apps.lifecycle` | Implemented; lifecycle tested with mocked Compose; real app installs **Experimental** |
| 7 | Gateway | `gateway.*` + agent `gateway.*` | **Tested** with real NGINX (HTTPS, redirect, SSRF, rollback) |
| 8 | Storage | `storage` (lsblk, UDisks2, smartctl via agent) | Inventory/usage Implemented; formatting **Experimental** (mocked only, by design) |
| 9 | Network | `network` (nmcli, iproute2, NM checkpoints) | Implemented; checkpoint rollback **Experimental** |
| 10 | Files | `files` (KIO, Dolphin, Baloo, Ark) | Implemented; KIO operations **Experimental** |
| 11 | Local AI | `ollama`, `chat` | Implemented (API mocked in tests); **Experimental** against a real Ollama |
| 12 | Notifications | `notifications` | Implemented (dedupe, preferences) |
| 13 | Security | `security` | Implemented |
| 14 | Activity History | `activity` | Implemented |

Global search / command palette: **Ctrl+K** (or Ctrl+Shift+P). Pages, settings,
installed/available packages, SSH profiles, Nexus apps, files (Baloo) and quick actions
("restart nginx"). Actions never run on match; administrative ones always confirm.

## Who may do what

The sidebar shows the signed-in user and their role. Administrative actions (marked
`admin: true` on `NxButton`) are hidden for users without sudo rights. When a task needs the
user's sudo password, a floating password box appears (`NxPasswordPrompt`); passwordless
sudo runs immediately; no sudo means "access denied". Details: `docs/security.md`.

## Design system

`command-center/frontend/qml/Nexus/Design/` — `Theme` (dark default + light, tokens
from `branding/design-tokens.json`, spacing scale, typography), `NxButton` (primary,
secondary, danger, ghost), `NxTextField`, `NxTable`, `NxCard`, `NxPageHeader`
(breadcrumb/title/actions), `NxStatusBadge` (colour + label), `NxBanner`, `NxEmptyState`,
`NxErrorState`, `NxLoading`, `NxConfirmDialog` (shows exact command/plan; optional typed
confirmation token), `NxTabBar`, `NxMetric`, `NxProgress`, `NxLogView`, `NxFormRow`,
`NxIcon` (line icons recoloured per theme), `NxSparkline`, `NxPasswordPrompt`.
Toasts and the palette live in `Main.qml`, which also sets a complete Qt palette from the
tokens so Basic-style controls (combo boxes, spin boxes, check boxes, menus, dialogs) never
pick up the desktop's palette.

### Platform theme

`nexus-center` runs with Qt's `generic` platform theme by default: under Plasma the KDE
platform theme costs ~93 MiB RSS (measured, see `docs/performance.md`) and the UI draws its
own controls anyway. File pickers are then Qt Quick dialogs. For native KDE dialogs start it
with `NEXUS_CENTER_PLATFORMTHEME=kde`, or `desktop` to keep the session's setting.

## Running

```bash
nexus-center                          # installed
QT_QPA_PLATFORM=offscreen nexus-center --smoke                 # load every module, report QML warnings
nexus-center --smoke --size 1680x980 --screenshots /tmp/shots # PNG of each page (+ page states, e.g. spec cards)
nexus-center --benchmark 20 [--no-visit --page overview]       # resource report (JSON)
# from a checkout:
PYTHONPATH=command-center/backend:command-center/frontend python3 -m nexus_center
```

## Known limitations

* Terminals are **Konsole tabs**, not embedded in the Command Center window. Embedding
  needs a C++ QML plugin around KPty/Konsole's terminal part (planned).
* Files embeds no Dolphin view (Dolphin's KPart is a QWidget; planned via KIO models).
* Application web UIs open in the default browser (`embed: window`); embedded
  QtWebEngine views are planned and will load only on demand.
* KCM pages open in `kcmshell6` windows rather than inside the Command Center.
* File dialogs are not KDE dialogs by default (see *Platform theme*).
* `qmllint` reports ~800 style warnings (mostly unqualified access in delegates); no errors.
