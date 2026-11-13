# KDE defaults

| Path | Installed to | Package |
|------|--------------|---------|
| `konsole/Nexus.profile` | `/usr/share/konsole/Nexus.profile` | nexusos-theme |
| `konsole/Nexus.colorscheme` (generated) | `/usr/share/konsole/Nexus.colorscheme` | nexusos-theme |
| `xdg/*` | `/usr/share/nexusos/xdg/` | nexusos-desktop |
| `xdg/plasma-workspace/env/nexusos-xdg.sh` | `/etc/xdg/plasma-workspace/env/` | nexusos-desktop |

## Why a separate XDG directory?

Writing `/etc/xdg/kdeglobals` would conflict with other flavour packages (for
example `kubuntu-settings-desktop` ships files in `/etc/xdg`). Instead
`nexusos-desktop` installs its defaults into `/usr/share/nexusos/xdg` and the
Plasma env script prepends that directory to `XDG_CONFIG_DIRS`.

Placing NexusOS *first* means its defaults win over `/etc/xdg`. Per-user
configuration in `~/.config` always wins over both. Removing `nexusos-desktop`
removes the env script, and the next session falls back to upstream defaults.

**Verification pending:** confirm in a Plasma 6.6 Wayland VM session that
`echo $XDG_CONFIG_DIRS` from Konsole starts with `/usr/share/nexusos/xdg`.
