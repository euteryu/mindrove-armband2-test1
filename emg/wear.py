"""Wear sessions: one guided recording per time the band is put on.

A wear session is the unit of data for the "works on every wear" goal (docs/ROADMAP.md).
It records, in order:

  1. Wear-on reference: two short holds (wrist in, open) used to estimate how far the
     ring of pods is rotated and how strong each channel is on this wear.
  2. The five target classes in three arm positions, two rounds per position, order
     shuffled each round.
  3. About a minute of "junk": everyday movement that must NOT trigger a gesture.

Each round is a "group" (0-5). The junk is cut into 6 equal pieces, one per group, so
leave-one-group-out testing inside a wear covers junk too.

Saved to <data>/wears/<YYYYMMDD_HHMMSS>/wear.npz plus meta.json.
"""
import json
import time
from pathlib import Path

import numpy as np

from .dsp import HOP, WIN, window_features

VERSION = 1
GESTURES = ["rest", "fist", "open", "wrist_in", "spiderman"]
OTHER = "other"            # internal class for junk movement; counts as rest at decision time
CLASSES = GESTURES + [OTHER]
REF = [("wrist_in", 3.0), ("open", 3.0)]
POSITIONS = [
    ("down", "Arm hanging relaxed at your side."),
    ("level", "Forearm level in front of you, elbow at a right angle."),
    ("up", "Hand up by your shoulder, elbow bent."),
]
ROUNDS_PER_POS = 2
HOLD = 4.0
JUNK = 60.0
N_GROUPS = len(POSITIONS) * ROUNDS_PER_POS

JUNK_TEXT = ("Move naturally for a minute: type, tap your phone, scratch, wave, pick something up, "
             "shake your hand out, rotate your wrist. Anything except the gestures.")


def protocol_steps(step_fn, seed=None):
    """List of step dicts. step_fn(label, hold, prep, **extra) builds one step (the
    engine's _step, which adds the emoji and instruction text)."""
    rng = np.random.default_rng(seed)
    steps = []
    for i, (g, hold) in enumerate(REF):
        s = step_fn(g, hold, prep=5.0 if i == 0 else 2.0, kind="ref", pos="level", group=-1)
        s["text"] = "Wear-on reference. " + POSITIONS[1][1] + " " + s["text"]
        steps.append(s)
    for p, (pos, pos_text) in enumerate(POSITIONS):
        for r in range(ROUNDS_PER_POS):
            order = list(rng.permutation(len(GESTURES)))
            for j, k in enumerate(order):
                g = GESTURES[k]
                s = step_fn(g, HOLD, prep=5.0 if (r, j) == (0, 0) else 2.0,
                            kind="gesture", pos=pos, group=p * ROUNDS_PER_POS + r, cls=int(k))
                s["text"] = pos_text + " " + s["text"]
                steps.append(s)
    s = step_fn("rest", JUNK, prep=4.0, kind="junk", pos="any", group=-1, cls=len(GESTURES))
    s["emoji"], s["text"], s["label"] = "🌀", JUNK_TEXT, OTHER
    steps.append(s)
    return steps


def protocol_seconds():
    n = len(GESTURES) * N_GROUPS
    return sum(h + 3.5 for _, h in REF) + n * (HOLD + 2) + 3 * 3 + JUNK + 4


# ---- saving / loading --------------------------------------------------------
def save(root, steps, segs, meta, name=None):
    out = Path(root) / "wears" / (name or time.strftime("%Y%m%d_%H%M%S"))
    out.mkdir(parents=True, exist_ok=True)
    arrays = {}
    for i, seg in enumerate(segs):
        for k in ("raw", "filt", "acc", "gyro"):
            arrays[f"{k}_{i}"] = seg[k].astype(np.float32)
    keep = ("label", "kind", "pos", "group", "cls", "hold")
    info = [{k: s.get(k) for k in keep} for s in steps]
    meta = dict(meta, version=VERSION, steps=info, wear_id=out.name)
    np.savez_compressed(out / "wear.npz", steps=json.dumps(info), **arrays)
    (out / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return out


class Wear:
    """A loaded wear session: steps (list of dicts) and segments (list of dicts of arrays)."""

    def __init__(self, path):
        path = Path(path)
        self.dir = path if path.is_dir() else path.parent
        d = np.load(self.dir / "wear.npz")
        self.steps = json.loads(str(d["steps"]))
        self.segs = [{k: d[f"{k}_{i}"].astype(float) for k in ("raw", "filt", "acc", "gyro")}
                     for i in range(len(self.steps))]
        self.meta = json.loads((self.dir / "meta.json").read_text(encoding="utf-8"))
        self.id = self.meta.get("wear_id", self.dir.name)

    def ref_segments(self):
        return [seg["filt"] for s, seg in zip(self.steps, self.segs) if s["kind"] == "ref"]


def find_wears(root):
    return sorted(p.parent for p in Path(root).glob("wears/*/wear.npz"))


# ---- rotation alignment and per-channel normalisation ------------------------
def channel_level(filt):
    """(8, n) filtered segment -> (8,) median log RMS over 200 ms windows."""
    starts = range(0, filt.shape[1] - WIN + 1, HOP)
    r = np.array([np.sqrt(np.mean(filt[:, s:s + WIN] ** 2, axis=1)) for s in starts])
    return np.median(np.log(r + 1e-3), axis=0)


def ref_pattern(ref_filts):
    """Reference holds -> (n_ref, 8) spatial pattern with the overall level removed,
    so it describes WHERE on the ring each gesture is strongest, not how strong."""
    P = np.array([channel_level(f) for f in ref_filts])
    return P - P.mean(axis=1, keepdims=True)


def shift_scores(pattern, template):
    """Similarity of np.roll(pattern, -s) to template, for s = 0..7."""
    n = pattern.shape[1]
    out = []
    for s in range(n):
        a = np.roll(pattern, -s, axis=1).ravel()
        b = template.ravel()
        out.append(float(np.corrcoef(a, b)[0, 1]))
    return np.array(out)


def estimate_shift(pattern, template):
    """Rotation s such that np.roll(data, -s, channel_axis) lines this wear up with the
    template. If channel c of this wear sits where channel c-s sat on the template wear,
    the answer is s."""
    return int(np.argmax(shift_scores(pattern, template)))


def build_template(patterns, iters=3):
    """Align a set of wear patterns to each other. Returns (template, shifts)."""
    template = patterns[0]
    shifts = [0] * len(patterns)
    for _ in range(iters):
        shifts = [estimate_shift(p, template) for p in patterns]
        template = np.mean([np.roll(p, -s, axis=1) for p, s in zip(patterns, shifts)], axis=0)
        template -= template.mean(axis=1, keepdims=True)
    return template, shifts


# ---- windows for training / testing ------------------------------------------
def windows(wear, kind="rms_wl", shift=0, norm=None):
    """All gesture and junk windows of a wear.

    Returns dict with X (n, f), y (class index into CLASSES), group (0..5), hold (step
    index, junk pieces get their own ids), and junk (bool). shift rolls the channels;
    norm is an (8,) per-channel log level subtracted from the amplitude features."""
    X, y, group, hold, junk = [], [], [], [], []
    for i, (s, seg) in enumerate(zip(wear.steps, wear.segs)):
        if s["kind"] == "ref":
            continue
        filt = np.roll(seg["filt"], -shift, axis=0) if shift else seg["filt"]
        if s["kind"] == "junk":
            pieces = np.array_split(np.arange(filt.shape[1]), N_GROUPS)
            parts = [(filt[:, idx], g, 1000 + g) for g, idx in enumerate(pieces)]
        else:
            parts = [(filt, s["group"], i)]
        for f, g, h in parts:
            if f.shape[1] < WIN:
                continue
            F = window_features(f, kind)
            if norm is not None:
                F[:, :8] -= norm
                F[:, 8:16] -= norm
            X.append(F)
            n = len(F)
            y += [s["cls"]] * n
            group += [g] * n
            hold += [h] * n
            junk += [s["kind"] == "junk"] * n
    return {"X": np.vstack(X), "y": np.array(y), "group": np.array(group),
            "hold": np.array(hold), "junk": np.array(junk)}


def wear_norm(wear, shift=0):
    """Per-channel log level over the reference holds, after rotation."""
    lv = np.mean([channel_level(f) for f in wear.ref_segments()], axis=0)
    return np.roll(lv, -shift)
