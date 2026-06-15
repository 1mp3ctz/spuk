"""Generate Spuk's app icon — the "Whisper Wave" ghost on the Aurora gradient.

Draws a high-res master with Pillow (no design tools, nothing leaves the machine),
then exports:

  * packaging/icon-1024.png   — 1024px master / reference
  * packaging/spuk.icns       — macOS app icon (all sizes, via `iconutil`)
  * packaging/spuk.ico        — Windows app icon (multi-size)

The shapes mirror docs/design/app-icon-mockups.html (concept 1): a white ghost
whose bottom wisps form a voice waveform, with the eyes punched out so the
gradient shows through. Run once on macOS, then commit the generated files —
the CI build just references them.

    uv run python packaging/make_icon.py
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent

# Aurora brand gradient (top-left -> bottom-right), matching the pill / window.
STOPS = [(0.0, (139, 92, 246)), (0.5, (124, 58, 237)), (1.0, (109, 40, 217))]

SS = 2048                       # supersampled canvas; downscaled to every size
PAD = round(0.0977 * SS)        # Apple-style padding (≈100/1024)
BODY = SS - 2 * PAD             # the rounded-square "body" size
RADIUS = round(0.225 * BODY)    # squircle-ish corner radius
SCALE = BODY / 120.0            # the mockup is drawn in a 0..120 coordinate space


def _u(x: float) -> float:
    """Map a 0..120 design-space coordinate to a canvas pixel."""
    return PAD + x * SCALE


def _gradient(n: int) -> Image.Image:
    """Diagonal Aurora gradient as an n×n RGB image."""
    yy, xx = np.mgrid[0:n, 0:n]
    t = (xx + yy) / (2 * (n - 1))            # 0 at top-left → 1 at bottom-right
    offs = np.array([s[0] for s in STOPS])
    cols = np.array([s[1] for s in STOPS], dtype=float)
    out = np.empty((n, n, 3), dtype=float)
    for c in range(3):
        out[..., c] = np.interp(t, offs, cols[:, c])
    return Image.fromarray(out.round().astype("uint8"), "RGB")


def _ghost_mask(n: int) -> Image.Image:
    """Alpha mask of the white ghost (body + waveform wisps), eyes punched out."""
    m = Image.new("L", (n, n), 0)
    d = ImageDraw.Draw(m)

    # Dome (top semicircle) + straight-sided body.
    d.pieslice([_u(26), _u(25), _u(94), _u(93)], 180, 360, fill=255)
    d.rectangle([_u(26), _u(59), _u(94), _u(76)], fill=255)

    # Waveform wisps: five rounded bars of varying height = a voice equaliser.
    bars = [(28, 92), (42, 102), (56, 86), (70, 98), (84, 90)]  # (x, bottom-y)
    bw = 8
    bar_radius = bw * SCALE / 2  # round the bar tips/ends to half their width
    for x, bottom in bars:
        d.rounded_rectangle(
            [_u(x), _u(64), _u(x + bw), _u(bottom)],
            radius=bar_radius,
            fill=255,
        )

    # Eyes — punched to transparent so the gradient reads through them.
    for cx in (50, 70):
        d.ellipse([_u(cx - 5), _u(52 - 6), _u(cx + 5), _u(52 + 6)], fill=0)

    return m


def render_master() -> Image.Image:
    n = SS
    grad = _gradient(n)

    # Squircle alpha: rounded square inside the padding, transparent corners/margin.
    squircle = Image.new("L", (n, n), 0)
    ImageDraw.Draw(squircle).rounded_rectangle(
        [PAD, PAD, n - PAD, n - PAD], radius=RADIUS, fill=255
    )

    tile = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    tile.paste(grad, (0, 0), squircle)

    # Composite the white ghost (with transparent eyes) onto the tile.
    white = Image.new("RGBA", (n, n), (255, 255, 255, 255))
    tile.paste(white, (0, 0), _ghost_mask(n))

    return tile.resize((1024, 1024), Image.LANCZOS)


def main() -> None:
    master = render_master()
    png_path = HERE / "icon-1024.png"
    master.save(png_path)
    print(f"✓ {png_path.name}")

    # Windows .ico (multi-size from the master).
    ico_path = HERE / "spuk.ico"
    master.save(ico_path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"✓ {ico_path.name}")

    # macOS .icns via iconutil (needs the standard .iconset layout).
    if shutil.which("iconutil"):
        with tempfile.TemporaryDirectory() as tmp:
            iconset = Path(tmp) / "spuk.iconset"
            iconset.mkdir()
            specs = [
                (16, "16x16"), (32, "16x16@2x"), (32, "32x32"), (64, "32x32@2x"),
                (128, "128x128"), (256, "128x128@2x"), (256, "256x256"),
                (512, "256x256@2x"), (512, "512x512"), (1024, "512x512@2x"),
            ]
            for px, label in specs:
                master.resize((px, px), Image.LANCZOS).save(iconset / f"icon_{label}.png")
            icns_path = HERE / "spuk.icns"
            subprocess.run(["iconutil", "-c", "icns", "-o", str(icns_path), str(iconset)], check=True)
            print(f"✓ {icns_path.name}")
    else:
        print("⚠ iconutil not found (not on macOS) — skipped .icns. Run this on a Mac to build it.")


if __name__ == "__main__":
    main()
