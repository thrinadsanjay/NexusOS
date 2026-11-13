# Wallpaper packages

KDE wallpaper packages (`Wallpaper/Images` KPackage structure). Each package
has a `metadata.json` here; `contents/images/<W>x<H>.png` are rendered from the
SVG masters in `branding/wallpapers/` by `debian/rules` in `nexusos-branding`
(no rasters are committed).

| Package | Master | Rendered sizes |
|---------|--------|----------------|
| `NexusOS` (default) | `nexusos-default.svg` | 3840x2160, 2560x1440, 1920x1080, 1366x768 |
| `NexusOS-Abstract` | `nexusos-abstract.svg` | same |
| `NexusOS-Engineering` | `nexusos-engineering.svg` | same |
