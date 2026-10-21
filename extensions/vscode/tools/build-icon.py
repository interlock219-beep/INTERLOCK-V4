#!/usr/bin/env python3
"""Generate media/interlock-icon.png (256x256) - the packaged extension icon.

The artwork is the Interlock shield logo: an electric-yellow (#FFE500) shield
with two interlocking bars in graphite (#0A0B0B). It is the same geometry as
media/interlock-activitybar.svg and SHIELD_LOGO_PATH in src/webviewHtml.ts,
drawn without any text so it stays recognisable at small sizes.

Pillow rasterises it at 8x and downsamples (LANCZOS) for clean edges.

Usage:  python tools/build-icon.py
Output: media/interlock-icon.png
"""

from __future__ import annotations

import pathlib

from PIL import Image, ImageDraw

SIZE = 256          # VS Code / Marketplace extension icons must be >= 128px
SS = 8              # supersampling factor
GRID = 24.0         # the artwork is authored on the same 24x24 grid as the SVG
ACCENT = (255, 229, 0, 255)      # #FFE500
GRAPHITE = (10, 11, 11, 255)     # #0A0B0B


def cubic(p0, p1, p2, p3, steps=48):
    """Flatten a cubic bezier to line segments."""
    points = []
    for i in range(1, steps + 1):
        t = i / steps
        u = 1.0 - t
        x = u * u * u * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t * t * t * p3[0]
        y = u * u * u * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t * t * t * p3[1]
        points.append((x, y))
    return points


def shield_points():
    """The shield outline: M12 2.2 20 5.1 ... V5.1 L12 2.2 Z (see the SVG)."""
    start = (12.0, 2.2)
    top_right = (20.0, 5.1)
    right = (20.0, 11.5)
    bottom = (12.0, 21.9)
    left = (4.0, 11.5)
    top_left = (4.0, 5.1)
    pts = [start, top_right, right]
    # c 0 4.6 -3.2 8.6 -8 10.4
    pts += cubic(right, (20.0, 16.1), (16.8, 20.1), bottom)
    # -4.8 -1.8 -8 -5.8 -8 -10.4
    pts += cubic(bottom, (7.2, 20.1), (4.0, 16.1), left)
    pts += [top_left, start]
    return pts


def main() -> None:
    scale = SIZE * SS / GRID
    canvas = Image.new("RGBA", (SIZE * SS, SIZE * SS), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    def xy(point):
        return (point[0] * scale, point[1] * scale)

    draw.polygon([xy(p) for p in shield_points()], fill=ACCENT)

    # The two interlocking bars (7.4 9.6 h9.2 v2.8 / 9.4 14 h5.2 v2.6).
    draw.rectangle([xy((7.4, 9.6)), xy((16.6, 12.4))], fill=GRAPHITE)
    draw.rectangle([xy((9.4, 14.0)), xy((14.6, 16.6))], fill=GRAPHITE)

    icon = canvas.resize((SIZE, SIZE), Image.LANCZOS)
    out = pathlib.Path(__file__).resolve().parent.parent / "media" / "interlock-icon.png"
    icon.save(out, format="PNG", optimize=True)
    print(f"wrote {out} ({out.stat().st_size} bytes, {SIZE}x{SIZE})")


if __name__ == "__main__":
    main()
