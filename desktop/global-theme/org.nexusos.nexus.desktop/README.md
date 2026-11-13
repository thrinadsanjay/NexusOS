# Nexus global theme (`org.nexusos.nexus.desktop`)

A KDE Plasma 6 Look-and-Feel package. It *composes* upstream components rather
than forking them:

| Component | Value | Notes |
|-----------|-------|-------|
| Colour scheme | `Nexus` | generated from `branding/design-tokens.json` |
| Plasma style | `default` (Breeze) | Breeze Plasma SVGs follow the active colour scheme |
| Application style | Breeze | |
| Window decoration | Breeze | |
| Icons | `Nexus` | inherits `breeze-dark`, adds NexusOS launcher/distributor icons |
| Wallpaper | `NexusOS` | wallpaper package shipped by `nexusos-branding` |
| Splash | `org.kde.Breeze` | placeholder until a Nexus splash exists |
| Layout | `contents/layouts/org.kde.plasma.desktop-layout.js` | staged at build time from `desktop/panels/` |

`contents/previews/*` are rendered from the SVG wallpaper master during the
package build (`debian/rules`) so no binaries are stored in Git.
