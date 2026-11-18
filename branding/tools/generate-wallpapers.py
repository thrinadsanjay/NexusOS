#!/usr/bin/env python3
"""Generate the NexusOS landscape wallpapers (SVG masters) from a seeded scene description.

    branding/tools/generate-wallpapers.py            # rewrite branding/wallpapers/*.svg

The scenes are deterministic (fixed seeds), use only design-token colours and contain no
raster data, so the SVGs are reproducible masters; PNGs are rendered at package build time.

  nexusos-default.svg  night lake, mountains, aurora, centred logo, wordmark and tagline
  nexusos-aurora.svg   the same landscape without branding (lock screen, clean desktop)
  nexusos-summit.svg   dawn over the range, copper horizon
  nexusos-hexgrid.svg  minimal: deep navy, faint hex grid, teal glow
"""

from __future__ import annotations

import math
import random
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "wallpapers"
W, H = 1920, 1080
HORIZON = 742  # shoreline (y)

# design tokens (core + derived)
BG = "#0B171B"
BG2 = "#123B40"
MID = "#102E33"
SURFACE = "#142328"
ELEV = "#1B3036"
BORDER = "#29434A"
TEAL = "#31C6BD"
TEAL_HI = "#4FD3CB"
COPPER = "#C47750"
COPPER_HI = "#D28B66"
TEXT = "#E8F1F2"
TEXT2 = "#9EB3B7"
NAVY_DEEP = "#0A1424"
NAVY = "#10213A"
NAVY_MIST = "#1A3350"

LOGO = """
  <g transform="translate({x} {y}) scale({s}) translate(-128 -128)" filter="url(#logoGlow)">
    <polygon points="128,12 228.5,70 228.5,186 128,244 27.5,186 27.5,70" fill="{bg}" fill-opacity="0.55"
             stroke="{teal}" stroke-width="6" stroke-linejoin="round"/>
    <polygon points="76,180 76,76 100,76 156,148 156,76 180,76 180,180 156,180 100,108 100,180" fill="{teal_hi}"/>
    <path d="M180 76 L204 62" stroke="{copper}" stroke-width="5" stroke-linecap="round"/>
    <circle cx="208" cy="60" r="10" fill="{copper}"/>
    <circle cx="208" cy="60" r="4" fill="{bg}"/>
  </g>"""


def ridge(
    rng: random.Random, base: float, amp: float, rough: float, peaks: int, x0=-40, x1=W + 40, centre_dip: float = 0.0
) -> list:
    """Mountain ridge: a few dominant summits (sharp, asymmetric) plus fractal detail."""
    n = 1025
    xs = [x0 + (x1 - x0) * i / (n - 1) for i in range(n)]
    summits = [
        (
            rng.uniform(x0 + 120, x1 - 120),
            rng.uniform(amp * 0.9, amp * 2.0),
            rng.uniform(150, 330),
            rng.uniform(0.7, 1.4),
        )
        for _ in range(peaks)
    ]
    heights = []
    for x in xs:
        h = amp * 0.25
        for cx, ph, width, skew in summits:
            d = (x - cx) / (width * (skew if x > cx else 1 / skew))
            h = max(h, ph * max(0.0, 1 - abs(d)) ** 1.6)
        heights.append(h)
    # fractal detail (midpoint displacement on a 1D grid)
    detail = [0.0] * n
    step, disp = n - 1, amp * 0.45
    while step > 1:
        half = step // 2
        for i in range(half, n - 1, step):
            detail[i] = (detail[i - half] + detail[i + half]) / 2 + rng.uniform(-disp, disp)
        step, disp = half, disp * rough
    # keep the centre low behind the wordmark (branded scene)
    dip = [1 - centre_dip * math.exp(-(((x - W / 2) / 420) ** 2)) for x in xs]
    return [(x, base - max(0.0, (h + d) * k)) for x, h, d, k in zip(xs, heights, detail, dip, strict=True)]


def poly(pts: list, bottom: float) -> str:
    d = f"M{pts[0][0]:.1f},{bottom:.1f} " + " ".join(f"L{x:.1f},{y:.1f}" for x, y in pts)
    return d + f" L{pts[-1][0]:.1f},{bottom:.1f} Z"


def snow_line(pts: list, base: float, frac: float) -> float:
    top = min(y for _, y in pts)
    return top + (base - top) * frac


def snow(pts: list, line: float) -> str:
    """Snow caps: the parts of the ridge above *line*, closed a little below the crest."""
    caps, cur = [], []
    for x, y in pts:
        if y < line:
            cur.append((x, y))
        elif cur:
            caps.append(cur)
            cur = []
    out = []
    for cap in caps:
        if len(cap) < 3:
            continue
        top = " ".join(f"L{x:.1f},{y:.1f}" for x, y in cap)
        back = " ".join(
            f"L{x:.1f},{max(y + 2, line + 7 * math.sin(x / 6) + 5 * math.sin(x / 2.3)):.1f}" for x, y in reversed(cap)
        )
        out.append(f"M{cap[0][0]:.1f},{cap[0][1]:.1f} {top} {back} Z")
    return " ".join(out)


def mirror(d_pts: list, axis: float, squash: float = 0.55) -> list:
    return [(x, axis + (axis - y) * squash) for x, y in d_pts]


def stars(rng: random.Random, n: int, ymax: float) -> str:
    out = []
    for _ in range(n):
        x, y = rng.uniform(0, W), rng.uniform(0, ymax) ** 1.0
        r = rng.choice([0.6, 0.7, 0.8, 1.0, 1.0, 1.3, 1.7])
        o = rng.uniform(0.25, 0.9) * (1 - y / ymax * 0.7)
        out.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{r}" fill="{TEXT}" opacity="{o:.2f}"/>')
    return "\n    ".join(out)


def trees(rng: random.Random, y: float, x0: float, x1: float, colour: str) -> str:
    out, x = [], x0
    while x < x1:
        h = rng.uniform(10, 26)
        w = h * rng.uniform(0.32, 0.45)
        out.append(f"M{x:.1f},{y:.1f} L{x + w / 2:.1f},{y - h:.1f} L{x + w:.1f},{y:.1f} Z")
        x += w * rng.uniform(0.55, 1.1)
    return f'<path d="{" ".join(out)}" fill="{colour}"/>'


def scene(seed: int, *, dawn: bool = False, branding: bool = False) -> str:
    rng = random.Random(seed)  # noqa: S311 - deterministic artwork, not security
    sky_top, sky_mid = (NAVY, NAVY_MIST) if dawn else (NAVY_DEEP, NAVY)
    glow, glow_hi = (COPPER, COPPER_HI)
    dip = 0.62 if branding else 0.0
    far = ridge(rng, HORIZON - 70, 95, 0.6, 5, centre_dip=dip)
    mid_r = ridge(rng, HORIZON - 10, 120, 0.6, 4, centre_dip=dip)
    near = ridge(rng, HORIZON + 4, 34, 0.58, 3)
    aurora_o = 0.35 if dawn else 0.75
    sun_x = 1290 if not branding else 1340
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="3840" height="2160" viewBox="0 0 {W} {H}">',
        "  <defs>",
        f'    <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{sky_top}"/><stop offset="0.55" stop-color="{sky_mid}"/>'
        f'<stop offset="0.86" stop-color="{BG2}"/><stop offset="1" stop-color="{glow}" stop-opacity="{0.9 if dawn else 0.55}"/>'
        "</linearGradient>",
        f'    <radialGradient id="sun" cx="{sun_x / W:.3f}" cy="{HORIZON / H:.3f}" r="0.42">'
        f'<stop offset="0" stop-color="{glow_hi}" stop-opacity="{0.95 if dawn else 0.75}"/>'
        f'<stop offset="0.25" stop-color="{glow}" stop-opacity="{0.55 if dawn else 0.35}"/>'
        f'<stop offset="1" stop-color="{glow}" stop-opacity="0"/></radialGradient>',
        f'    <linearGradient id="lake" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{MID}"/>'
        f'<stop offset="1" stop-color="{BG}"/></linearGradient>',
        f'    <linearGradient id="aur" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{TEAL}" stop-opacity="0"/>'
        f'<stop offset="0.35" stop-color="{TEAL_HI}" stop-opacity="0.9"/><stop offset="0.7" stop-color="{TEAL}" stop-opacity="0.6"/>'
        f'<stop offset="1" stop-color="{TEAL}" stop-opacity="0"/></linearGradient>',
        '    <filter id="blurL" x="-150%" y="-60%" width="400%" height="220%"><feGaussianBlur stdDeviation="22"/></filter>',
        '    <filter id="blurM" x="-20%" y="-50%" width="140%" height="200%"><feGaussianBlur stdDeviation="7"/></filter>',
        '    <filter id="blurS"><feGaussianBlur stdDeviation="1.4"/></filter>',
        f'    <filter id="logoGlow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur in="SourceAlpha" stdDeviation="14"/>'
        f'<feFlood flood-color="{TEAL}" flood-opacity="0.55"/><feComposite operator="in" in2="SourceAlpha"/>'
        '<feMorphology operator="dilate" radius="2"/><feGaussianBlur stdDeviation="10"/>'
        '<feMerge><feMergeNode/><feMergeNode in="SourceGraphic"/></feMerge></filter>',
        f'    <linearGradient id="fade" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{BG}" stop-opacity="0"/>'
        f'<stop offset="1" stop-color="{BG}" stop-opacity="0.85"/></linearGradient>',
        "  </defs>",
        f'  <rect width="{W}" height="{H}" fill="url(#sky)"/>',
        f"  <g>\n    {stars(rng, 260 if not dawn else 90, HORIZON - 160)}\n  </g>",
        # aurora: wide soft ribbons + a crisp arc
        f'  <g opacity="{aurora_o}">',
        '    <path d="M-100,420 C260,140 620,90 980,170 S1560,330 2040,120" fill="none" stroke="url(#aur)" stroke-width="150" filter="url(#blurL)"/>',
        '    <path d="M-100,330 C300,120 700,40 1060,110 S1640,260 2040,40" fill="none" stroke="url(#aur)" stroke-width="60" opacity="0.7" filter="url(#blurM)"/>',
        '    <path d="M80,520 C420,250 760,180 1110,230 S1700,380 2000,250" fill="none" stroke="url(#aur)" stroke-width="3" opacity="0.8"/>',
        f'    <path d="M-60,250 C380,70 760,0 1180,60" fill="none" stroke="{TEAL_HI}" stroke-width="1.6" opacity="0.5"/>',
        "  </g>",
        f'  <rect width="{W}" height="{H}" fill="url(#sun)"/>',
        # mountains
        f'  <path d="{poly(far, HORIZON + 2)}" fill="{BORDER}" opacity="0.85"/>',
        f'  <path d="{snow(far, snow_line(far, HORIZON - 70, 0.42))}" fill="{TEXT2}" opacity="0.6"/>',
        f'  <path d="{poly(mid_r, HORIZON + 2)}" fill="{ELEV}"/>',
        f'  <path d="{snow(mid_r, snow_line(mid_r, HORIZON - 10, 0.4))}" fill="{TEXT}" opacity="0.88"/>',
        f'  <path d="{poly(near, HORIZON + 2)}" fill="{SURFACE}"/>',
        trees(rng, HORIZON + 2, 40, 760, BG),
        trees(rng, HORIZON + 2, 1500, 1900, BG),
        # lake + reflections
        f'  <rect y="{HORIZON}" width="{W}" height="{H - HORIZON}" fill="url(#lake)"/>',
        '  <g opacity="0.22" filter="url(#blurS)">',
        f'    <path d="{poly(mirror(far, HORIZON), HORIZON)}" fill="{BORDER}"/>',
        f'    <path d="{poly(mirror(mid_r, HORIZON), HORIZON)}" fill="{ELEV}"/>',
        "  </g>",
        f'  <ellipse cx="{sun_x}" cy="{HORIZON + 70}" rx="46" ry="200" fill="{glow_hi}" opacity="{0.55 if dawn else 0.35}" filter="url(#blurL)"/>',
    ]
    for i in range(16):  # glints on the water
        y = HORIZON + 18 + i * 17
        w = 120 - i * 5 + rng.uniform(-20, 20)
        parts.append(
            f'  <rect x="{sun_x - w / 2 + rng.uniform(-12, 12):.0f}" y="{y}" width="{w:.0f}" height="2.2" rx="1.1" '
            f'fill="{glow_hi}" opacity="{0.55 - i * 0.03:.2f}"/>'
        )
    parts += [
        f'  <path d="M0,{HORIZON + 1} H{W}" stroke="{TEAL}" stroke-opacity="0.25" stroke-width="1.2"/>',
        f'  <rect y="{H - 220}" width="{W}" height="220" fill="url(#fade)"/>',
    ]
    if branding:
        parts += [
            LOGO.format(x=W / 2, y=258, s=0.86, bg=BG, teal=TEAL, teal_hi=TEAL_HI, copper=COPPER),
            f'  <text x="{W / 2}" y="470" text-anchor="middle" font-family="Inter, sans-serif" font-size="104" '
            f'font-weight="700" letter-spacing="1" fill="{TEXT}">Nexus<tspan fill="{TEAL_HI}">OS</tspan></text>',
            f'  <text x="{W / 2}" y="528" text-anchor="middle" font-family="Inter, sans-serif" font-size="25" '
            f'font-weight="500" letter-spacing="13" fill="{TEXT2}">ENGINEERING EDITION</text>',
            f'  <text x="{W / 2}" y="580" text-anchor="middle" font-family="Inter, sans-serif" font-size="20" '
            f'font-weight="600" letter-spacing="6" fill="{TEAL}">BUILD  •  AUTOMATE  •  DEPLOY  •  MANAGE</text>',
        ]
    parts.append("</svg>\n")
    return "\n".join(parts)


def hexgrid() -> str:
    r = 46
    dx, dy = r * math.sqrt(3), r * 1.5
    cells = []
    for row in range(int(H / dy) + 2):
        for col in range(int(W / dx) + 2):
            cx = col * dx + (dx / 2 if row % 2 else 0)
            cy = row * dy
            pts = " ".join(
                f"{cx + r * math.cos(math.radians(60 * k - 30)):.1f},{cy + r * math.sin(math.radians(60 * k - 30)):.1f}"
                for k in range(6)
            )
            cells.append(f'<polygon points="{pts}"/>')
    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="3840" height="2160" viewBox="0 0 {W} {H}">',
            "  <defs>",
            f'    <radialGradient id="g" cx="0.72" cy="0.38" r="0.75"><stop offset="0" stop-color="{BG2}"/>'
            f'<stop offset="0.55" stop-color="{NAVY}"/><stop offset="1" stop-color="{NAVY_DEEP}"/></radialGradient>',
            f'    <radialGradient id="glow" cx="0.72" cy="0.38" r="0.35"><stop offset="0" stop-color="{TEAL}" stop-opacity="0.35"/>'
            f'<stop offset="1" stop-color="{TEAL}" stop-opacity="0"/></radialGradient>',
            '    <radialGradient id="mask" cx="0.72" cy="0.38" r="0.6"><stop offset="0" stop-color="#FFFFFF" stop-opacity="1"/>'
            '<stop offset="1" stop-color="#FFFFFF" stop-opacity="0"/></radialGradient>',
            '    <mask id="m"><rect width="100%" height="100%" fill="url(#mask)"/></mask>',
            "  </defs>",
            f'  <rect width="{W}" height="{H}" fill="url(#g)"/>',
            f'  <g mask="url(#m)" fill="none" stroke="{TEAL}" stroke-opacity="0.16" stroke-width="1.2">',
            *cells,
            "  </g>",
            f'  <rect width="{W}" height="{H}" fill="url(#glow)"/>',
            LOGO.format(x=W * 0.72, y=H * 0.38, s=0.5, bg=BG, teal=TEAL, teal_hi=TEAL_HI, copper=COPPER),
            "</svg>\n",
        ]
    )


def main() -> None:
    header = "<!-- Generated by branding/tools/generate-wallpapers.py; original artwork, (c) NexusOS contributors, GPL-2.0-or-later. -->\n"
    files = {
        "nexusos-default.svg": scene(7, branding=True),
        "nexusos-aurora.svg": scene(7),
        "nexusos-summit.svg": scene(23, dawn=True),
        "nexusos-hexgrid.svg": hexgrid(),
    }
    for name, svg in files.items():
        (OUT / name).write_text(svg.replace("<svg ", header + "<svg ", 1))
        print(f"wrote {OUT / name}")


if __name__ == "__main__":
    main()
