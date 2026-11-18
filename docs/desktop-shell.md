# NexusOS desktop: launcher rail and System Status panel

The Engineering Edition desktop has two persistent elements and nothing else:

```
 ┌──┐                                                                   ┌──┐
 │N │  NexusOS logo → Command Center                         status  ●  │N │
 │⌂ │  Show Desktop                                          clock  11:39│  │
 │▦ │  Application menu (Kickoff)                                  Thu 30│  │
 │▭ │  Files                                                   Wi-Fi  ◉  │◉ │
 │>_│  Terminal                        wallpaper              Bluetooth  │ᛒ │
 │⬡ │  Containers   (only if Docker is installed)                  VPN  │⛨ │
 │▣ │  Virtual Machines (only if virt-manager is installed)    battery  │▮ │
 │☁ │  Cloud Platform                                        CPU/RAM/disk│% │
 │AI│  AI Assistant (only if Ollama is installed)                  expand│‹ │
 │› │  All shortcuts (expanded launcher)                notification bell │🔔│
 └──┘                                                                   └──┘
```

* **Left: launcher rail.** Icon-only, floating, centred vertically. Hover shows the name, click
  starts the application or brings its window forward, a dot marks running applications. The
  last icon opens the expanded launcher (every shortcut with its name and description).
* **Right: System Status rail.** Clock, date, network, Bluetooth, VPN, battery, CPU, memory, disk,
  expand, and the notification bell. A click (or Meta+Alt+S) opens the **System Status panel**:
  header with calendar, pin and settings; Wi-Fi/Bluetooth/VPN/notification tiles; battery;
  CPU/RAM/GPU/disk rings; health and alerts; storage; services; Focus, Settings, Lock, Power.
* **Centre:** the wallpaper. There is no top bar, taskbar or system tray.

## Architecture

Everything is native Plasma 6: two panels from the look-and-feel layout script, two Plasma applets
written in QML, and Plasma's own Kickoff and notifications applets. There is no replacement shell
and no extra daemon.

| Part | Where | What it uses |
|------|-------|--------------|
| Layout | `desktop/panels/org.kde.plasma.desktop-layout.js` | two floating vertical panels (`left`, `right`), `lengthMode: fit` |
| Launcher rail | `desktop/plasmoids/org.nexusos.launcher` | TaskManager model (running dots, activation), `kstart` (launch), .desktop + `TryExec` (availability) |
| Application menu | `org.kde.plasma.kickoff` | upstream, NexusOS grid icon |
| System Status | `desktop/plasmoids/org.nexusos.status` | see data sources |
| Notification bell | `org.kde.plasma.notifications` | upstream; Plasma shows pop-ups only while this applet exists |
| Health/alerts backend | `nexus system desktop-status --json` (`nexus_core.desktop_status`) | systemd, cached APT simulation, `df` |
| Optional tools | `org.nexusos.{containers,cloud,ai-assistant}.desktop` | `TryExec=docker` / `nexus-center` / `ollama` |

### System Status data sources

| Indicator | Source | Updates |
|-----------|--------|---------|
| Clock, date | QML timer aligned to the minute | once a minute |
| CPU, memory, GPU, disk | KSystemStats sensors (`cpu/all/usage`, `memory/physical/usedPercent`, `gpu/all/usage`, `disk/all/usedPercent`) | pushed by ksystemstats, rate-limited to 2 s |
| Network, Wi-Fi switch | plasma-nm (`NetworkStatus`, `EnabledConnections`, `Handler.enableWireless`) | event-driven; connection names re-read with `nmcli` when NetworkManager reports a change |
| VPN | active `vpn` / `wireguard` connections (same `nmcli` read) | on change |
| Bluetooth, switch | BluezQt `Manager` (`bluetoothOperational`, `bluetoothBlocked`, devices) | event-driven |
| Battery, charging, time, health | PowerDevil/UPower via the `powermanagement` data engine | event-driven; hidden without a battery |
| Notifications, Focus mode | notification server model (`unreadNotificationsCount`) and settings (`notificationsInhibitedUntil`) | event-driven |
| Health, alerts, storage, services | `nexus system desktop-status --json` | every 5 min (configurable) and whenever the panel opens; APT part cached 30 min |

GPU, battery and Bluetooth sections disappear when the hardware is not there. Docker, Ollama, the
Command Center and a browser are never required for the desktop to work.

### Behaviour

* Click the rail (not hover) to open; click outside or press Escape to close; the pin keeps it open.
  The open/pinned state is stored in the applet configuration and restored at login.
* Every section links to its Command Center page (`nexus-center --page …`); the panel itself stays
  a control surface.
* Switches run as the logged-in user through NetworkManager and BlueZ polkit rules; nothing in the
  desktop widgets uses sudo.
* Keyboard: Meta+Alt+A expanded launcher, Meta+Alt+S System Status, Meta+N notification history;
  Tab and arrow keys move between rail icons, Enter activates.

### Conflicts resolved

* **Notification pop-ups** need Plasma's notifications applet, so it stays, as the rail's bell.
* **Volume and brightness keys** are handled by Plasma services (`audioshortcutsservice`, PowerDevil)
  and keep working without the tray.
* **Removed with the tray:** application tray icons (StatusNotifierItem), clipboard history and the
  removable-device popup. The network and Bluetooth applets' full menus remain one click away in
  System Settings from the panel tiles.

## Wallpapers and lock screen

`branding/tools/generate-wallpapers.py` generates the landscape masters (deterministic, design-token
colours only): **NexusOS** (default, logo and wordmark), **Aurora** (no branding), **Summit** (dawn),
**Hex Grid** (minimal); plus the existing Abstract and Engineering. The lock screen shows a slideshow
of them (`/usr/share/nexusos/xdg/kscreenlockerrc`). Application-menu category icons are generated by
`branding/tools/generate-category-icons.py` into the Nexus icon theme.

## Verification

`scripts/validation/plasma-session-container.sh --screenshots DIR` boots a real Plasma 6 Wayland
session in a container and checks the layout (left rail, right rail, no top/bottom panel, no tray or
taskbar), that both widgets load without QML errors, the status backend, the lock-screen default, and
takes screenshots of the desktop, the open System Status panel and the expanded launcher.
