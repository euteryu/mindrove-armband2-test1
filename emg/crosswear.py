"""The cross-wear model: one classifier trained on every saved wear session.

At start-up (and after each new wear session) all wears under <data>/wears are lined
up to each other by their wear-on reference holds (emg/wear.py), and one LDA is trained
on all of them. When the band is put on again, a 6 s "quick start" (the same two
reference holds) tells how far the ring is turned and how strong each pod is today;
live windows are then rotated and scaled the same way before classification.

Which variant is used (rotation alignment, strength normalisation, rotation
augmentation) is chosen from the offline results in tools/evaluate.py; see ROADMAP.md.
"""
import numpy as np

from . import wear as W
from .dsp import features
from .gestures import LDA

DEFAULT = {"kind": "rms_wl", "norm": True, "aug": 0}


class CrossWearModel:
    def __init__(self, data_dir, kind=DEFAULT["kind"], norm=DEFAULT["norm"], aug=DEFAULT["aug"]):
        self.kind, self.norm, self.aug = kind, norm, aug
        self.wears = [W.Wear(p) for p in W.find_wears(data_dir)]
        if not self.wears:
            raise ValueError("no wear sessions saved yet")
        pats = [W.ref_pattern(w.ref_segments()) for w in self.wears]
        self.template, self.shifts = W.build_template(pats)
        X, y = [], []
        for w, s in zip(self.wears, self.shifts):
            for d in range(-aug, aug + 1):
                sh = (s + d) % 8
                win = W.windows(w, kind, shift=sh, norm=W.wear_norm(w, sh) if norm else None)
                X.append(win["X"])
                y.append(win["y"])
        self.lda = LDA().fit(np.vstack(X), np.concatenate(y))
        self.names = list(W.CLASSES)

    def calibrate(self, ref_filts):
        """Wear-on reference holds of today -> alignment dict for proba()."""
        pat = W.ref_pattern(ref_filts)
        scores = W.shift_scores(pat, self.template)
        shift = int(np.argmax(scores))
        level = np.roll(np.mean([W.channel_level(f) for f in ref_filts], axis=0), -shift)
        return {"shift": shift, "match": round(float(scores[shift]), 3), "level": level}

    def proba(self, win, align):
        x = np.roll(win, -align["shift"], axis=0)
        f = features(x, self.kind)
        if self.norm:
            f[:8] -= align["level"]
            f[8:16] -= align["level"]
        p = np.zeros(len(self.names))
        p[self.lda.classes] = self.lda.proba(f)[0]
        return p

    def summary(self):
        return {"wears": len(self.wears), "ids": [w.id for w in self.wears],
                "kind": self.kind, "norm": self.norm, "aug": self.aug}
