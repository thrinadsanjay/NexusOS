# Panels and dock

`org.kde.plasma.desktop-layout.js` is the single source for the Nexus default
layout. The `nexusos-theme` package build copies it into
`org.nexusos.nexus.desktop/contents/layouts/`.

## Design

```
┌──────────────────────────────────────────────────────────────────────┐
│ [N] [pager]        CPU ▁▃▅  MEM ▆▆▂  NET ↑↓        12:04        tray │  top panel
└──────────────────────────────────────────────────────────────────────┘

                 ╭───────────────────────────────────────╮
                 │ 📁 🌐 │ >_  ✎  dev │ infra  mon │ AI │ ⚙ │            floating dock
                 ╰───────────────────────────────────────╯
```

* **NexusOS launcher** — Kickoff with the `nexusos` icon (shipped by `nexusos-branding`).
* **System monitoring** — upstream `org.kde.plasma.systemmonitor.{cpu,memory,net}` presets.
* **Development shortcuts** — Konsole, Kate, *Nexus Dev* (`nexus dev list` in Konsole).
* **Infrastructure shortcuts** — *Nexus Infra* (`nexus infra status`), Plasma System Monitor.
* **Local AI shortcut** — *Nexus AI* (`nexus ai status`). It reports Ollama
  availability; it is not a chat client. Ollama/Open WebUI are optional
  post-install components.

The `org.nexusos.*.desktop` launchers are shipped by `nexusos-desktop`.

## Verification status

The script uses documented Plasma 6 scripting properties (`location`, `height`,
`floating`, `alignment`, `lengthMode`, `hiding`, `addWidget`,
`currentConfigGroup`, `writeConfig`). It has been syntax-checked with Node but
**not yet executed inside a live Plasma 6.6 session**. Validate in a VM:

```bash
qdbus6 org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript "$(cat org.kde.plasma.desktop-layout.js)"
```

(This adds panels to the running session; use a throwaway VM user.)
