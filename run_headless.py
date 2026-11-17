"""Headless gesture recognition: no screen, no browser, no PC.

This is the shape of the end goal on a single-board computer: the board joins the
armband's Wi-Fi, loads the model trained earlier (data/models/latest.npz) and reacts
to gestures on its own. Replace on_gesture() with whatever the wearable should do
(drive a GPIO pin, send a serial command, ...).

    python run_headless.py            real armband
    python run_headless.py --sim      simulated armband
"""
import argparse
import json
import queue
import time
from pathlib import Path

from emg.engine import Engine
from emg.source import MindRoveSource, SimSource

MIN_CONFIDENCE = 0.8   # ignore uncertain guesses
MIN_HOLD = 0.25        # seconds a gesture must persist before it counts


def on_gesture(label, confidence):
    print(f"{time.strftime('%H:%M:%S')}  {label}  ({confidence:.0%})", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sim", action="store_true")
    ap.add_argument("--mains", type=int, default=50, choices=(50, 60))
    ap.add_argument("--data-dir", default=None, help="default: data/, or data/sim/ with --sim")
    args = ap.parse_args()

    data_dir = args.data_dir or Path(__file__).parent / "data" / ("sim" if args.sim else "")
    engine = Engine(SimSource() if args.sim else MindRoveSource(), mains=args.mains, data_dir=data_dir)
    if engine.model is None:
        raise SystemExit("No trained model found. Train one first in the app (python app.py), Gestures tab.")
    print("Gestures:", ", ".join(engine.model.names), "  Ctrl+C to stop")
    engine.start()
    q = engine.subscribe()
    current, candidate, since, status = None, None, 0.0, None
    try:
        while True:
            try:
                m = json.loads(q.get(timeout=1))
            except queue.Empty:
                continue
            if m["t"] != "tick":
                continue
            if m["status"] != status:
                status = m["status"]
                print(f"[link: {status}]", flush=True)
            p = m["pred"]
            if not p or p["conf"] < MIN_CONFIDENCE:
                candidate = None
                continue
            now = time.monotonic()
            if p["label"] != candidate:
                candidate, since = p["label"], now
            elif candidate != current and now - since >= MIN_HOLD:
                current = candidate
                on_gesture(current, p["conf"])
    except KeyboardInterrupt:
        pass
    finally:
        engine.stop()
        engine.join(timeout=5)


if __name__ == "__main__":
    main()
