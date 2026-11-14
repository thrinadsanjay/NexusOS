#!/usr/bin/env python3
"""Write the Plymouth animation frames as SVG (rendered to PNG at package build time).

A pointy-top hexagon outline (30°/60° geometry, as in the NexusOS mark) with a teal
segment travelling around it and a copper node. Colours come from the design tokens.
usage: generate-frames.py DESIGN_TOKENS.json OUT_DIR [FRAMES]
"""

import json
import math
import sys
from pathlib import Path

tokens = json.loads(Path(sys.argv[1]).read_text())["color"]
out = Path(sys.argv[2])
frames = int(sys.argv[3]) if len(sys.argv) > 3 else 36
out.mkdir(parents=True, exist_ok=True)

size, r, stroke = 64, 24, 3.2
cx = cy = size / 2
angles = [math.radians(-90 + 60 * i) for i in range(6)]
corners = [(cx + r * math.cos(a), cy + r * math.sin(a)) for a in angles]
outline = " ".join(f"{x:.2f},{y:.2f}" for x, y in [*corners, corners[0]])
perimeter = 6 * r
dash = perimeter * 0.28

for i in range(frames):
    offset = -perimeter * i / frames
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 {size} {size}">
  <polyline points="{outline}" fill="none" stroke="{tokens["border"]}"
            stroke-width="{stroke}" stroke-linejoin="round"/>
  <polyline points="{outline}" fill="none" stroke="{tokens["accent-primary"]}"
            stroke-width="{stroke}" stroke-linejoin="round" stroke-linecap="round"
            stroke-dasharray="{dash:.2f} {perimeter - dash:.2f}" stroke-dashoffset="{offset:.2f}"/>
  <circle cx="{corners[1][0]:.2f}" cy="{corners[1][1]:.2f}" r="3.2" fill="{tokens["accent-secondary"]}"/>
</svg>"""
    (out / f"animation-{i + 1:04d}.svg").write_text(svg)
    (out / f"throbber-{i + 1:04d}.svg").write_text(svg)
