#!/usr/bin/env python3
"""
capture_demo.py -- record the breaker-trip cascade from grid_twin.html as a GIF.

This is the README hero shot: feeder current and real power collapse while bus
voltage HOLDS. Capturing it by hand means re-rolling the load walk until you get
a take you like, so this script pins the randomness instead.

WHAT IT DOES
  1. Injects a seeded PRNG over Math.random before any page script runs, so the
     same --seed always produces the same take. Reproducible, re-recordable,
     and diffable if the physics ever changes underneath you.
  2. Loads the twin, lets it settle so the tags are visibly moving.
  3. Fires the Industroyer scenario.
  4. Grabs frames at a fixed rate and assembles a looping GIF.

USAGE
    pip install -r requirements.txt
    playwright install chromium
    python capture_demo.py                      # -> docs/img/twin-demo.gif
    python capture_demo.py --seed 7 --fps 12    # different take
    python capture_demo.py --full-page          # whole UI, not just the diagram

ENCODER
  Uses ffmpeg (palettegen/paletteuse) when available -- markedly better colour
  on the dark console palette. Falls back to Pillow if not.
"""

from __future__ import annotations

import argparse
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
TWIN = ROOT / "twin" / "grid_twin.html"
OUT_DEFAULT = ROOT / "docs" / "img" / "twin-demo.gif"

# Timing, in seconds, relative to the click on "Run Industroyer scenario".
# The twin's own scenario schedule (see grid_twin.html):
#   t+0   breaker opens, alarm banner
#   t+5   "SIGNATURE CONFIRMED" banner
#   t+12  auto-reset, breaker recloses
SETTLE_S = 5.0      # let the load walk visibly move before the trip
LEAD_S = 2.0        # capture this much normal operation before the click
RECORD_S = 13.0     # trip -> signature -> just before reset

# Seeded PRNG injected before page scripts. mulberry32 -- small, fast, fine here.
SEED_SCRIPT = """
(() => {
  let a = %d >>> 0;
  Math.random = function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
})();
"""


def encode_ffmpeg(frame_dir: pathlib.Path, out: pathlib.Path, fps: int, width: int) -> bool:
    """Two-pass palette encode. Much better on a dark palette than naive quantize."""
    if not shutil.which("ffmpeg"):
        return False
    palette = frame_dir / "palette.png"
    vf = f"fps={fps},scale={width}:-1:flags=lanczos"
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps),
             "-i", str(frame_dir / "f_%04d.png"),
             "-vf", f"{vf},palettegen=stats_mode=diff", str(palette)],
            check=True,
        )
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps),
             "-i", str(frame_dir / "f_%04d.png"), "-i", str(palette),
             "-lavfi", f"{vf}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=3",
             "-loop", "0", str(out)],
            check=True,
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"  ffmpeg failed ({e}); falling back to Pillow", file=sys.stderr)
        return False


def encode_pillow(frame_dir: pathlib.Path, out: pathlib.Path, fps: int, width: int) -> bool:
    try:
        from PIL import Image
    except ImportError:
        print("  neither ffmpeg nor Pillow available -- cannot encode", file=sys.stderr)
        return False
    frames = sorted(frame_dir.glob("f_*.png"))
    if not frames:
        return False
    imgs = []
    for p in frames:
        im = Image.open(p).convert("RGB")
        if im.width != width:
            im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
        imgs.append(im.quantize(colors=128, method=Image.MEDIANCUT))
    imgs[0].save(out, save_all=True, append_images=imgs[1:],
                 duration=round(1000 / fps), loop=0, optimize=True)
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=pathlib.Path, default=OUT_DEFAULT)
    ap.add_argument("--seed", type=int, default=42, help="PRNG seed; same seed = same take")
    ap.add_argument("--fps", type=int, default=12, help="capture + playback rate")
    ap.add_argument("--width", type=int, default=760, help="output width px")
    ap.add_argument("--full-page", action="store_true",
                    help="capture the whole UI instead of just the one-line diagram")
    args = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright is required:\n  pip install -r requirements.txt"
              "\n  playwright install chromium", file=sys.stderr)
        return 1

    if not TWIN.is_file():
        print(f"twin not found at {TWIN}", file=sys.stderr)
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    total_frames = round((LEAD_S + RECORD_S) * args.fps)

    with tempfile.TemporaryDirectory() as td:
        frame_dir = pathlib.Path(td)
        print(f"twin   : {TWIN}")
        print(f"seed   : {args.seed}  (same seed reproduces this exact take)")
        print(f"capture: {args.fps} fps, {LEAD_S + RECORD_S:.0f}s, {total_frames} frames")

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 860},
                                    device_scale_factor=2)
            # Must land before any page script -- this is why init_script, not evaluate.
            page.add_init_script(SEED_SCRIPT % args.seed)
            page.goto(TWIN.as_uri())
            page.wait_for_selector("#btnAttack")

            # Fonts + first physics tick.
            page.wait_for_timeout(int(SETTLE_S * 1000))

            target = page.locator("body") if args.full_page else page.locator(".panel").first
            interval = 1.0 / args.fps
            lead_frames = round(LEAD_S * args.fps)
            n = 0

            print("  recording normal operation…")
            for i in range(lead_frames):
                target.screenshot(path=str(frame_dir / f"f_{n:04d}.png"))
                n += 1
                page.wait_for_timeout(int(interval * 1000))

            print("  firing Industroyer scenario…")
            page.click("#btnAttack")

            for i in range(total_frames - lead_frames):
                target.screenshot(path=str(frame_dir / f"f_{n:04d}.png"))
                n += 1
                page.wait_for_timeout(int(interval * 1000))

            browser.close()

        print(f"  captured {n} frames; encoding…")
        ok = encode_ffmpeg(frame_dir, args.out, args.fps, args.width) or \
            encode_pillow(frame_dir, args.out, args.fps, args.width)
        if not ok:
            return 1

    size_mb = args.out.stat().st_size / 1_048_576
    print(f"\nwrote {args.out}  ({size_mb:.2f} MB)")
    if size_mb > 4:
        print("  >4 MB -- GitHub may not render it inline.")
        print("  try: --fps 10 --width 640")
    return 0


if __name__ == "__main__":
    sys.exit(main())
