# Demo media

The README hero shot lives here as `twin-demo.gif`.

## Generate it

```bash
cd tools
pip install -r requirements.txt
playwright install chromium
python capture_demo.py                     # -> docs/img/twin-demo.gif
```

That's it. The script drives the twin headlessly, fires the Industroyer
scenario, and encodes a looping GIF.

## Why it's scripted rather than screen-recorded

The twin's load factor is a random walk, so recording by hand means re-rolling
until you get a take you like — and you can never reproduce it afterwards. The
script injects a seeded PRNG over `Math.random` *before* any page script runs,
so `--seed 42` always produces the same take. Re-recordable after a physics
change, and diffable if something shifts underneath you.

## Options

```bash
python capture_demo.py --seed 7        # different take, still reproducible
python capture_demo.py --fps 10 --width 640    # smaller file
python capture_demo.py --full-page     # whole UI, not just the one-line diagram
```

Keep the result under ~4 MB or GitHub won't render it inline; the script warns
you and suggests flags if you go over.

## What it captures

2 s of normal operation (tags moving on the shared load factor), then the trip:
current and real power collapse while **bus voltage holds** and the conductor
*above* the breaker stays amber. That asymmetry is the whole thesis of the
project, which is why it's the frame the README leads with.

Encoding uses ffmpeg with a two-pass palette when available — noticeably better
on this dark palette — and falls back to Pillow otherwise.
