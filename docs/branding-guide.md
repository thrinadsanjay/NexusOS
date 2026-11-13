# NexusOS branding guide

**NexusOS — Engineering Edition — BUILD. AUTOMATE. DEPLOY.**

Design direction: a premium engineering workstation. Dark, geometric, precise;
subtle glass, never neon. Professional rather than gaming.

## Design tokens

The single source of truth is [`branding/design-tokens.json`](../branding/design-tokens.json).
KDE colour files are generated from it (`scripts/build/generate_theme_colors.py`)
and CI fails if they drift. Artwork may only use token colours (validated).

| Token | Hex | Use |
|-------|-----|-----|
| `background-primary` | `#0B171B` | Desktop/view background, terminal background |
| `background-secondary` | `#123B40` | Gradients, alternate backgrounds |
| `accent-primary` | `#31C6BD` | Teal accent: focus, selection, the "N" |
| `accent-secondary` | `#C47750` | Copper: the nexus node, highlights, visited links — use sparingly |
| `text-primary` | `#E8F1F2` | Body text |
| `text-secondary` | `#9EB3B7` | Captions, inactive text |
| `surface` | `#142328` | Windows, panels |
| `surface-elevated` | `#1B3036` | Buttons, headers, tooltips |
| `border` | `#29434A` | Frames, separators |

Derived tokens (hover/pressed, glass, status colours, `background-gradient-mid`)
are in the same file. Selection uses dark text on teal for contrast (≈ 9:1).

## Application UI (Command Center)

`command-center/frontend/qml/Nexus/Design/Theme.qml` implements the tokens for Qt Quick:
dark palette = the brand tokens above (default), light palette for daylight use
(`#F4F8F9` background, `#1E8F88` accent for contrast on light). Spacing uses a 4 px grid
(4/8/12/16/24/32), radii 4/8, controls 32 px high. Status is always colour **and** text.
Avoid gradients, glass and animation in the app UI (only 120 ms functional transitions).

## Typography

| Role | Family | Ubuntu package |
|------|--------|----------------|
| UI and wordmark | **Inter** (wordmark: Bold, +0.04em tracking) | `fonts-inter` |
| Monospace, terminal, tagline | **JetBrains Mono** | `fonts-jetbrains-mono` |

Fallbacks: Noto Sans / Noto Sans Mono. Tagline is always uppercase with wide
tracking: `BUILD. AUTOMATE. DEPLOY.`

## The mark

A pointy-top hexagon (all geometry on 30°/60° lines) enclosing a solid
geometric **N**, with a copper **node** connected to the upper-right vertex —
the "nexus" where systems meet.

| Asset | File | Use |
|-------|------|-----|
| Primary logo (stacked) | `branding/logo/nexusos-logo.svg` | Splash, about pages, documents |
| Horizontal lockup | `branding/logo/nexusos-logo-horizontal.svg` | Headers, README, SDDM |
| Monochrome | `branding/logo/nexusos-logo-mono.svg` | One-colour contexts (uses `currentColor`) |
| Application icon | `branding/icons/nexus-n.svg` | Launcher, `nexusos` icon name |
| Installer logo | `branding/logo/nexusos-installer-logo.svg` | Calamares, welcome screens |
| Terminal logo | `branding/logo/nexusos-terminal-logo.svg` | Konsole profile, CLI docs |
| Boot logo | `branding/boot/nexusos-boot-logo.svg` | Plymouth (draft) |
| Command Center icon | `branding/icons/nexusos-command-center.svg` | `nexusos-command-center` icon name |
| Login background | `branding/login/nexusos-login-background.svg` | SDDM greeter (planned theme) |
| ASCII logo | `configs/shell/ascii-logo.txt` | Banner, fastfetch |

Rules: keep clear space of ¼ of the mark's width; minimum size 16 px (icon) and
120 px wide (horizontal lockup); do not recolour the N to copper, rotate the
hexagon, add effects, or set the wordmark in another typeface. The live text in
SVG wordmarks must be converted to outlines for print production.

## Wallpapers

All masters are 3840×2160 SVG; PNG sizes (3840×2160, 2560×1440, 1920×1080,
1366×768) are rendered during the package build.

| Wallpaper | File | Character |
|-----------|------|-----------|
| NexusOS (default) | `nexusos-default.svg` | Layered glass hexagons over a faint hex grid, teal glow |
| NexusOS Abstract | `nexusos-abstract.svg` | Circuit traces with 30° bends and nodes |
| NexusOS Engineering Edition | `nexusos-engineering.svg` | Blueprint grid, dimension lines, edition lockup |

## Derivatives

SVG is the master format. `scripts/build/render-branding.sh` renders optimised
PNG (optipng) and WebP (cwebp) derivatives into `build/branding/`. Rasters are
never committed (`validate_branding.py` enforces this).

## Trademark use

All artwork is original and licensed GPL-2.0-or-later. The NexusOS name and
logo identify this project: forks and derivative distributions should use their
own name and logo. Never combine NexusOS marks with Ubuntu, Kubuntu or Canonical
logos, or imply endorsement by Canonical or KDE e.V.
