# NexusOS Debian packages

| Package | Contents | Key behaviour |
|---------|----------|---------------|
| `nexusos-branding` | os-release, release metadata, default hostname, banner, ASCII logo, fastfetch config, icons, wallpapers, artwork, NOTICE | Diverts `/usr/lib/os-release`; restores Ubuntu's on removal. Never changes hostname, lsb-release, kernel or APT config. |
| `nexusos-theme` | Nexus look-and-feel, colour scheme, icon theme, Konsole profile | Installing only makes the theme available. |
| `nexusos-defaults` | zsh template, aliases, prompt | Never touches existing home directories or `/etc/skel` (the image build seeds skel). |
| `nexusos-desktop` | Metapackage, `/usr/share/nexusos/xdg` defaults, Plasma env script, SDDM drop-in, launchers | Makes Nexus the default for sessions; user config wins. |
| `nexus-cli` | `nexus` command (Python, dh-python) | Depends only on archive packages. |

Each directory contains a `debian/` tree and, where needed, `assets.txt` listing
repository files staged into the source package by `scripts/package/build-deb.sh`.
Raster images are generated in `debian/rules` from SVG masters.

```bash
scripts/package/build-in-container.sh      # reference build on ubuntu:26.04
scripts/package/build-deb.sh [PACKAGE...]  # host build
```

`lintian-overrides.txt` lists tags suppressed for development builds, each with a reason.
