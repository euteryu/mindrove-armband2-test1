"""Generate simulated wear sessions, to test tools/evaluate.py without the band.

    python tools/sim_wears.py --n 6 --out data/sim

Each simulated wear has the band turned by a random number of pods and a random gain
per pod. Simulated results say nothing about the real band; they only prove the
pipeline (alignment, evaluation, reporting) does what it should.
"""
import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from emg import wear  # noqa: E402
from emg.dsp import StreamFilter  # noqa: E402
from emg.engine import TRIM_END, TRIM_START, _step  # noqa: E402
from emg.source import SimSource  # noqa: E402


def simulate(seed, rotate, gain):
    src = SimSource(seed=seed, rotate=rotate, gain=gain)
    src.start()
    filt = StreamFilter(src.fs, 8)
    steps = wear.protocol_steps(_step, seed=seed)
    a, b = int(TRIM_START * src.fs), int(TRIM_END * src.fs)
    segs = []
    for s in steps:
        src.hint(s["label"])
        filt(src.advance(int(s["prep"] * src.fs))["emg"])
        chunks = [src.advance(25) for _ in range(int(s["hold"] * src.fs) // 25)]
        raw = np.concatenate([c["emg"] for c in chunks], axis=1)
        seg = {"raw": raw, "filt": filt(raw),
               "acc": np.concatenate([c["acc"] for c in chunks], axis=1),
               "gyro": np.concatenate([c["gyro"] for c in chunks], axis=1)}
        segs.append({k: v[:, a:v.shape[1] - b] for k, v in seg.items()})
    return steps, segs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=6)
    ap.add_argument("--out", default="data/sim")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)
    for i in range(args.n):
        rot = int(rng.integers(0, 8))
        gain = np.exp(rng.normal(0, 0.25, 8))
        steps, segs = simulate(args.seed * 100 + i, rot, gain)
        meta = {"source": "Simulator", "fs": 500, "note": f"sim: true rotation {rot}",
                "sim_rotate": rot, "classes": wear.CLASSES}
        out = wear.save(args.out, steps, segs, meta, name=f"sim{args.seed:02d}_{i:02d}")
        print(f"{out}  rotation {rot}")


if __name__ == "__main__":
    main()
