"""Check the cross-wear methods on REAL multi-day EMG from other people (GRABMyo).

GRABMyo (PhysioNet, CC-BY 4.0; Pradhan, He & Jiang, Sci Data 9, 733, 2022): 43 people,
3 days, forearm ring of 8 bipolar channels at 2048 Hz, 7 trials x 5 s per gesture.
Electrodes were re-applied each day (first electrode on the elbow-crease centreline),
so day-to-day differences are real skin/placement changes, with little ring rotation.

Mapped onto our classes:
  rest = Rest (17)  fist = Hand Close (16)  open = Hand Open (15)
  wrist_in = Wrist Flexion (12)
  spiderman stand-in = Thumb and Little Finger Extension (6)   (finger-level, like ours)
  other (junk) = Lateral Prehension, Thumb Adduction, Index Ext., Wrist Ext.,
                 Supination, Pronation (1, 2, 9, 11, 13, 14): deliberate contractions,
                 so harder to reject than everyday movement.
Each day becomes one "wear": trial 1 of wrist flexion and hand open = the wear-on
reference holds, trials 2-7 = groups 0-5. Signals are resampled to 500 Hz and run
through our own filter (mains 60 Hz, Canada) so features match the armband pipeline.

    python tools/grabmyo.py --raw data/public/grabmyo/raw --participants 1-10
    python tools/grabmyo.py ... --rotate     each day's ring turned by a random number
                                            of pods, to test rotation alignment on
                                            real muscle signals
"""
import argparse
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from scipy.signal import resample_poly

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from emg import wear as W  # noqa: E402
from emg.dsp import StreamFilter  # noqa: E402
import evaluate as E  # noqa: E402

CLASS_OF = {17: 0, 16: 1, 15: 2, 12: 3, 6: 4}
JUNK = [1, 2, 9, 11, 13, 14]
FS_IN, FS = 2048, 500
TRIM = (0.8, 0.2)


def read_trial(hea):
    """WFDB format-16 record -> (8, n) forearm ring 1 in microvolts at 500 Hz."""
    lines = [l for l in Path(hea).read_text().splitlines() if l.strip() and not l.startswith("#")]
    nsig = int(lines[0].split()[1])
    gains, bases = [], []
    for l in lines[1:9]:
        g = l.split()[2]                          # e.g. 109223.81(4352)/mV
        gains.append(float(g.split("(")[0]))
        bases.append(float(g.split("(")[1].split(")")[0]) if "(" in g else 0.0)
    d = np.fromfile(Path(hea).with_suffix(".dat"), dtype="<i2").reshape(-1, nsig)[:, :8].T.astype(float)
    uv = (d - np.array(bases)[:, None]) / np.array(gains)[:, None] * 1000.0
    return resample_poly(uv, 125, 512, axis=1)


def build_day(raw_root, s, p, rotate):
    folder = Path(raw_root) / f"Session{s}" / f"session{s}_participant{p}"
    a, b = int(TRIM[0] * FS), int(TRIM[1] * FS)
    steps, segs = [], []

    def add(g, t, **info):
        x = read_trial(folder / f"session{s}_participant{p}_gesture{g}_trial{t}.hea")
        f = StreamFilter(FS, 8, mains=60)(x)
        x, f = np.roll(x, rotate, axis=0), np.roll(f, rotate, axis=0)
        n = x.shape[1]
        segs.append({"raw": x[:, a:n - b], "filt": f[:, a:n - b],
                     "acc": np.zeros((3, n - a - b)), "gyro": np.zeros((3, n - a - b))})
        steps.append(dict(info, hold=5.0))

    for g, lbl in ((12, "wrist_in"), (15, "open")):
        add(g, 1, label=lbl, kind="ref", pos="seated", group=-1)
    for t in range(2, 8):
        for g, c in CLASS_OF.items():
            add(g, t, label=W.CLASSES[c], kind="gesture", pos="seated", group=t - 2, cls=c)
        for g in JUNK:
            add(g, t, label=W.OTHER, kind="junk", pos="seated", group=t - 2, cls=len(W.GESTURES))
    return steps, segs


def parse_range(text):
    out = []
    for part in text.split(","):
        lo, _, hi = part.partition("-")
        out += list(range(int(lo), int(hi or lo) + 1))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", default="data/public/grabmyo/raw")
    ap.add_argument("--out", default="data/public/grabmyo")
    ap.add_argument("--participants", default="1-10")
    ap.add_argument("--rotate", action="store_true")
    ap.add_argument("--features", nargs="+", default=["rms_wl", "td4"])
    ap.add_argument("--threshold", type=float, default=0.7)
    ap.add_argument("--dwell", type=int, default=4)
    ap.add_argument("--calib-weight", type=int, default=3)
    args = ap.parse_args()
    rng = np.random.default_rng(0)
    tag = "rotated" if args.rotate else "natural"
    per_person = {k: [] for k in args.features}
    rot_ok = []
    for p in parse_range(args.participants):
        root = Path(args.out) / "wears_converted" / tag / f"p{p:02d}"
        try:
            for s in (1, 2, 3):
                if not (root / "wears" / f"day{s}" / "wear.npz").exists():
                    r = int(rng.integers(0, 8)) if args.rotate else 0
                    steps, segs = build_day(args.raw, s, p, r)
                    W.save(root, steps, segs, {"source": "GRABMyo", "fs": FS, "participant": p,
                                               "day": s, "sim_rotate": r, "note": str(r)}, name=f"day{s}")
        except FileNotFoundError as e:
            print(f"participant {p}: missing files ({Path(e.filename).name}), skipped")
            continue
        wears = [W.Wear(d) for d in W.find_wears(root)]
        line = []
        for kind in args.features:
            summary, _, _ = E.evaluate(wears, kind, args, print)
            per_person[kind].append(summary)
            line.append(f"{kind}: within {100*summary['within']['window_acc']:.0f}%, "
                        f"best cross {100*max(v['window_acc'] for k, v in summary.items() if k != 'within'):.0f}%")
        rr = E.rotation_report(wears)
        if rr and "agrees" in rr[-1]:
            rot_ok.append(rr[-1].split("on ")[1])
        print(f"participant {p}: " + " | ".join(line))

    out = Path(args.out) / "eval" / f"{tag}_{time.strftime('%Y%m%d_%H%M%S')}"
    out.mkdir(parents=True, exist_ok=True)
    L = [f"GRABMyo check ({tag}), {len(per_person[args.features[0]])} participants, "
         f"3 days each, leave-one-day-out, tested on trials 3-7", ""]
    for kind, sums in per_person.items():
        if not sums:
            continue
        L += [f"Features: {kind}   (mean over participants; min-max in brackets for window acc)",
              f"{'method':<13}{'window':>8}{'range':>12}{'hold':>7}{'false/min':>11}   "
              + "".join(f"{g[:9]:>10}" for g in W.GESTURES)]
        for m in E.METHODS:
            vals = [s[m] for s in sums if m in s]
            wa = [v["window_acc"] for v in vals]
            pc = np.mean([v["per_class"] for v in vals], axis=0)
            L.append(f"{m:<13}{100*np.mean(wa):>7.1f}%  [{100*min(wa):3.0f}-{100*max(wa):3.0f}]"
                     f"{100*np.mean([v['hold_acc'] for v in vals]):>6.0f}%"
                     f"{np.mean([v['false_per_min'] for v in vals]):>11.2f}   "
                     + "".join(f"{100*x:>9.0f}%" for x in pc))
        L.append("")
    if rot_ok:
        L.append("Rotation estimate agreed with the true rotation on: " + ", ".join(rot_ok) + " (per participant)")
    report = "\n".join(L)
    print("\n" + report)
    (out / "report.txt").write_text(report, encoding="utf-8")
    (out / "report.json").write_text(json.dumps({k: v for k, v in per_person.items()}, indent=1), encoding="utf-8")
    print(f"Saved to {out.resolve()}")


if __name__ == "__main__":
    main()
