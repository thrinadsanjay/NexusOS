# Panels

`org.kde.plasma.desktop-layout.js` is the single source for the Nexus default layout. The
`nexusos-theme` package build copies it into `org.nexusos.nexus.desktop/contents/layouts/`.

Two floating vertical panels and nothing else: the launcher rail on the left
(`org.nexusos.launcher`, Kickoff, `org.nexusos.launcher`) and the System Status rail on the right
(`org.nexusos.status`, the notifications bell). No top bar, taskbar or system tray.

Design, data sources and conflicts: [`docs/desktop-shell.md`](../../docs/desktop-shell.md).
Verified in a real Plasma 6 Wayland session by `scripts/validation/plasma-session-container.sh`.
