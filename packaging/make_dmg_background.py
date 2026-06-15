"""Generate the macOS installer (.dmg) background — Aurora purple, on brand.

A 600×400 window: the Spuk app sits on the left, the Applications folder on the
right (Finder draws those icons + labels itself), and this background supplies the
gradient, a title, and an arrow pointing from Spuk → Applications.

Run on a Mac (uses a system font), then commit packaging/dmg-background.png so the
CI release build just references it.

    uv run python packaging/make_dmg_background.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
W, H = 600, 400
STOPS = [(0.0, (139, 92, 246)), (0.5, (124, 58, 237)), (1.0, (76, 29, 149))]

# Icon centres (must match the create-dmg --icon / --app-drop-link positions).
APP_XY = (150, 185)
APPS_XY = (450, 185)


def _font(size: int, bold: bool = False):
    candidates = [
        "/System/Library/Fonts/SFNS.ttf",
        "/System/Library/Fonts/SFNSDisplay.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _gradient() -> Image.Image:
    yy, xx = np.mgrid[0:H, 0:W]
    t = (xx / (W - 1) + yy / (H - 1)) / 2
    offs = np.array([s[0] for s in STOPS])
    cols = np.array([s[1] for s in STOPS], dtype=float)
    out = np.empty((H, W, 3), dtype=float)
    for c in range(3):
        out[..., c] = np.interp(t, offs, cols[:, c])
    return Image.fromarray(out.round().astype("uint8")).convert("RGBA")


def _centered(d: ImageDraw.ImageDraw, cx: int, y: int, text: str, font, fill):
    w = d.textlength(text, font=font)
    d.text((cx - w / 2, y), text, font=font, fill=fill)


def main() -> None:
    img = _gradient()

    # Soft top-left highlight for a little depth.
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([-160, -220, 320, 180], fill=(255, 255, 255, 38))
    img = Image.alpha_composite(img, glow)

    d = ImageDraw.Draw(img)
    _centered(d, W // 2, 40, "Install Spuk", _font(30), (255, 255, 255, 255))
    _centered(d, W // 2, 80, "Drag Spuk into your Applications folder", _font(15), (255, 255, 255, 220))

    # Arrow from the app toward Applications, along the icon row.
    y = APP_XY[1]
    x0, x1 = APP_XY[0] + 78, APPS_XY[0] - 78
    d.line([(x0, y), (x1 - 8, y)], fill=(255, 255, 255, 235), width=5)
    d.polygon([(x1, y), (x1 - 18, y - 11), (x1 - 18, y + 11)], fill=(255, 255, 255, 235))

    _centered(d, W // 2, 318, "Then eject this disk — that's it.", _font(13), (255, 255, 255, 170))

    out = HERE / "dmg-background.png"
    img.convert("RGB").save(out)
    print(f"✓ {out.name} ({W}×{H})")


if __name__ == "__main__":
    main()
