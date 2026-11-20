"""Offline evaluation of wear sessions: does recognition survive taking the band off?

    python tools/evaluate.py                  all wears under data/wears
    python tools/evaluate.py --data data/sim  simulated wears (tools/sim_wears.py)

Every method is tested on rounds 2-6 of a wear (groups 1-5). Methods:

  within        train on the other rounds of the SAME wear (today's per-wear retrain;
                the reference the others are aiming for)
  pooled        train on all OTHER wears, nothing from the test wear
  +align        ... channels rotated to line up, using the 2 wear-on reference holds
  +align+norm   ... and per-channel strength scaled from the same reference holds
  +aug          ... and training copies rotated one pod either way
  +calib        ... plus round 1 of the test wear (a ~30 s quick calibration)

Metrics:
  window acc    each 200 ms window classified on its own (junk excluded)
  hold acc      a hold counts as right when the decider fired only the right gesture
                (rest holds: fired nothing)
  false/min     gestures fired during the junk minute, per minute

Results go to <data>/eval/<time>/report.txt and report.json.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from emg import wear as W  # noqa: E402
from emg.decide import Decider  # noqa: E402
from emg.dsp import FEATURE_KINDS, HOP  # noqa: E402
from emg.gestures import LDA  # noqa: E402

NG = len(W.GESTURES)        # 5 real classes; index NG is "other"
TEST_GROUPS = list(range(1, W.N_GROUPS))
METHODS = ["within", "pooled", "+align", "+align+norm", "+aug", "+calib"]


class Model:
    def __init__(self, X, y):
        self.lda = LDA().fit(X, y)

    def proba(self, X):
        p = np.zeros((len(X), len(W.CLASSES)))
        p[:, self.lda.classes] = self.lda.proba(X)
        return p


class Cache:
    def __init__(self, kind):
        self.kind, self.d = kind, {}

    def get(self, w, shift=0, norm=False):
        key = (w.id, shift % 8, norm)
        if key not in self.d:
            nv = W.wear_norm(w, shift) if norm else None
            self.d[key] = W.windows(w, self.kind, shift=shift % 8, norm=nv)
        return self.d[key]


def stack(parts):
    return np.vstack([p[0] for p in parts]), np.concatenate([p[1] for p in parts])


def score(model, t, args):
    """t: windows dict of the test wear, already restricted to TEST_GROUPS."""
    P = model.proba(t["X"])
    pred = P.argmax(1)
    merged = lambda v: np.where(v == NG, 0, v)   # other counts as rest
    g = ~t["junk"]
    conf = np.zeros((NG, NG), int)
    np.add.at(conf, (merged(t["y"][g]), merged(pred[g])), 1)
    dec = Decider(W.CLASSES, args.threshold, args.dwell)
    holds_ok, holds_n = np.zeros(NG), np.zeros(NG)
    false, junk_s = 0, 0.0
    for h in np.unique(t["hold"]):
        m = t["hold"] == h
        fired = dec.run(P[m])
        if t["junk"][m][0]:
            false += len(fired)
            junk_s += m.sum() * HOP / W_FS
            continue
        c = int(t["y"][m][0])
        holds_n[c] += 1
        holds_ok[c] += (not fired) if c == 0 else (len(fired) > 0 and set(fired) == {c})
    return {"conf": conf, "holds_ok": holds_ok, "holds_n": holds_n,
            "false": false, "junk_s": junk_s}


def summarise(rs):
    conf = sum(r["conf"] for r in rs)
    ok, n = sum(r["holds_ok"] for r in rs), sum(r["holds_n"] for r in rs)
    false, js = sum(r["false"] for r in rs), sum(r["junk_s"] for r in rs)
    return {"window_acc": float(np.trace(conf) / conf.sum()),
            "per_class": [float(conf[i, i] / max(1, conf[i].sum())) for i in range(NG)],
            "hold_acc": float(ok.sum() / max(1, n.sum())),
            "hold_per_class": [float(ok[i] / max(1, n[i])) for i in range(NG)],
            "false_per_min": float(false / max(1e-9, js / 60)),
            "confusion": conf.tolist()}


def select(d, mask):
    return {k: v[mask] for k, v in d.items()}


def evaluate(wears, kind, args, log):
    cache = Cache(kind)
    pats = {w.id: W.ref_pattern(w.ref_segments()) for w in wears}
    res = {m: [] for m in METHODS}
    shifts = {}
    for t in wears:
        test_mask = lambda d: np.isin(d["group"], TEST_GROUPS)
        # within: leave one round out inside the test wear
        full = cache.get(t)
        rs = []
        for g in TEST_GROUPS:
            tr, te = full["group"] != g, full["group"] == g
            rs.append(score(Model(full["X"][tr], full["y"][tr]), select(full, te), args))
        res["within"].append(_merge(rs))

        others = [w for w in wears if w.id != t.id]
        if not others:
            continue
        template, sh = W.build_template([pats[w.id] for w in others])
        s_t = W.estimate_shift(pats[t.id], template)
        shifts[t.id] = {"estimated": s_t, "note": t.meta.get("note", ""),
                        "train": {w.id: s for w, s in zip(others, sh)}}

        def train(align, norm, aug=0):
            parts = []
            for w, s in zip(others, sh):
                for d in range(-aug, aug + 1):
                    x = cache.get(w, (s if align else 0) + d, norm)
                    parts.append((x["X"], x["y"]))
            return parts

        st = s_t
        variants = {
            "pooled": (train(False, False), cache.get(t)),
            "+align": (train(True, False), cache.get(t, st)),
            "+align+norm": (train(True, True), cache.get(t, st, True)),
            "+aug": (train(True, True, 1), cache.get(t, st, True)),
        }
        for name, (parts, tw) in variants.items():
            X, y = stack(parts)
            res[name].append(score(Model(X, y), select(tw, test_mask(tw)), args))
        tw = cache.get(t, st, True)
        cal = tw["group"] == 0
        parts = train(True, True, 1) + [(tw["X"][cal], tw["y"][cal])] * args.calib_weight
        X, y = stack(parts)
        res["+calib"].append(score(Model(X, y), select(tw, test_mask(tw)), args))
    return {m: summarise(r) for m, r in res.items() if r}, shifts, res


def _merge(rs):
    return {"conf": sum(r["conf"] for r in rs), "holds_ok": sum(r["holds_ok"] for r in rs),
            "holds_n": sum(r["holds_n"] for r in rs), "false": sum(r["false"] for r in rs),
            "junk_s": sum(r["junk_s"] for r in rs)}


def fmt(summary, shifts, per_wear, wears, kind):
    L = [f"Features: {kind}", ""]
    hdr = f"{'method':<13}{'window':>8}{'hold':>7}{'false/min':>11}   " + "".join(f"{g[:9]:>10}" for g in W.GESTURES)
    L += [hdr, "-" * len(hdr)]
    for m, s in summary.items():
        L.append(f"{m:<13}{100*s['window_acc']:>7.1f}%{100*s['hold_acc']:>6.0f}%{s['false_per_min']:>11.2f}   "
                 + "".join(f"{100*v:>9.0f}%" for v in s["per_class"]))
    L += ["", "Per wear, window accuracy:"]
    ids = [w.id for w in wears]
    for m, rs in per_wear.items():
        if rs:
            vals = [np.trace(r["conf"]) / r["conf"].sum() for r in rs]
            L.append(f"  {m:<13}" + "  ".join(f"{100*v:5.1f}" for v in vals))
    L.append("  wears        " + "  ".join(i[-5:] for i in ids))
    L += rotation_report(wears)
    L += ["", "Confusion of the best cross-wear method (rows = made, cols = recognised):"]
    cross = {m: s for m, s in summary.items() if m != "within"}
    if cross:
        best = max(cross, key=lambda m: cross[m]["window_acc"])
        L.append(f"  {best}")
        L.append("  " + " " * 11 + "".join(f"{g[:9]:>10}" for g in W.GESTURES))
        for g, row in zip(W.GESTURES, summary[best]["confusion"]):
            L.append(f"  {g[:10]:<11}" + "".join(f"{v:>10}" for v in row))
    return "\n".join(L)


W_FS = 500


def rotation_report(wears):
    """Rotation of every wear relative to the first, from the wear-on holds, next to the
    tape note. The note counts pods by hand, so only its differences matter, and the
    pod numbering may run either way round the ring: either est - note or est + note
    should be the same for every wear."""
    if len(wears) < 2:
        return []
    pats = [W.ref_pattern(w.ref_segments()) for w in wears]
    template, sh = W.build_template(pats)
    sh = [(s - sh[0]) % 8 for s in sh]
    L = ["", "Rotation of each wear relative to the first (pods), from the wear-on holds:"]
    notes = []
    for w, s in zip(wears, sh):
        note = str(w.meta.get("sim_rotate", w.meta.get("note", ""))).strip()
        notes.append(int(note) if note.lstrip("-").isdigit() else None)
        L.append(f"  {w.id}: {s}   note: {w.meta.get('note') or '-'}")
    known = [(s, n) for s, n in zip(sh, notes) if n is not None]
    if len(known) >= 2:
        same = max(max(np.bincount([(s - n) % 8 for s, n in known], minlength=8)),
                   max(np.bincount([(s + n) % 8 for s, n in known], minlength=8)))
        L.append(f"  agrees with the notes on {same} of {len(known)} wears")
    return L


def main():
    global W_FS
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data")
    ap.add_argument("--features", nargs="+", default=list(FEATURE_KINDS), choices=FEATURE_KINDS)
    ap.add_argument("--threshold", type=float, default=0.7)
    ap.add_argument("--dwell", type=int, default=4)
    ap.add_argument("--calib-weight", type=int, default=3)
    args = ap.parse_args()
    paths = W.find_wears(args.data)
    if not paths:
        sys.exit(f"No wear sessions under {Path(args.data) / 'wears'}. Record one in the app first.")
    wears = [W.Wear(p) for p in paths]
    W_FS = int(wears[0].meta.get("fs", 500))
    print(f"{len(wears)} wear(s): " + ", ".join(w.id for w in wears))
    if len(wears) == 1:
        print("Only one wear: showing within-wear results only (Checkpoint A).")
    out = Path(args.data) / "eval" / time.strftime("%Y%m%d_%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    texts, js = [], {"wears": [w.id for w in wears], "args": vars(args), "results": {}}
    for kind in args.features:
        summary, shifts, per_wear = evaluate(wears, kind, args, print)
        texts.append(fmt(summary, shifts, per_wear, wears, kind))
        js["results"][kind] = {"summary": summary, "shifts": shifts}
    report = (f"Wear evaluation {time.strftime('%Y-%m-%d %H:%M')}, {len(wears)} wears, tested on rounds 2-6, "
              f"decider threshold {args.threshold}, dwell {args.dwell} windows\n\n" + "\n\n".join(texts))
    print(report)
    (out / "report.txt").write_text(report, encoding="utf-8")
    (out / "report.json").write_text(json.dumps(js, indent=1), encoding="utf-8")
    print(f"\nSaved to {out.resolve()}")


if __name__ == "__main__":
    main()
