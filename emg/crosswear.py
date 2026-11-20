"""The cross-wear model: one classifier trained on every saved wear session.

At start-up (and after each new wear session) all wears under <data>/wears are lined
up to each other by their wear-on reference holds (emg/wear.py), and one classifier is
trained on all of them. When the band is put on again:

  quick start (6 s)       the two reference holds tell how far the ring is turned and
                          how strong each pod is today; live windows are rotated and
                          scaled the same way before classification
  quick calibrate (~35 s) the same, plus one short hold of each gesture, added to the
                          training data (weighted) and the classifier is re-trained

The choices (classifier, features, normalisation) come from the offline results in
tools/evaluate.py and tools/grabmyo.py; see docs/ROADMAP.md.
"""
import numpy as np

from . import wear as W
from .dsp import features, window_features
from .gestures import LDA
from .mlp import MLP

DEFAULT = {"clf": "mlp", "kind": "td4", "norm": True}
CLF = {"lda": LDA, "mlp": MLP}
CALIB_WEIGHT = 3


class CrossWearModel:
    def __init__(self, data_dir=None, clf=DEFAULT["clf"], kind=DEFAULT["kind"], norm=DEFAULT["norm"],
                 _base=None, _extra=None):
        self.clf_name, self.kind, self.norm = clf, kind, norm
        self.names = list(W.CLASSES)
        self.calibrated = _extra is not None
        if _base is not None:          # re-train an existing model with calibration data
            self.wears, self.template, self.shifts = _base.wears, _base.template, _base.shifts
            self.X, self.y = _base.X, _base.y
        else:
            self.wears = [W.Wear(p) for p in W.find_wears(data_dir)]
            if not self.wears:
                raise ValueError("no wear sessions saved yet")
            pats = [W.ref_pattern(w.ref_segments()) for w in self.wears]
            self.template, self.shifts = W.build_template(pats)
            X, y = [], []
            for w, s in zip(self.wears, self.shifts):
                win = W.windows(w, kind, shift=s, norm=W.wear_norm(w, s) if norm else None)
                X.append(win["X"])
                y.append(win["y"])
            self.X, self.y = np.vstack(X), np.concatenate(y)
        X, y = self.X, self.y
        if _extra is not None:
            X = np.vstack([X] + [_extra[0]] * CALIB_WEIGHT)
            y = np.concatenate([y] + [_extra[1]] * CALIB_WEIGHT)
        self.clf = CLF[clf]().fit(X, y)

    def calibrate(self, ref_filts):
        """Wear-on reference holds of today -> alignment dict for proba()."""
        pat = W.ref_pattern(ref_filts)
        scores = W.shift_scores(pat, self.template)
        shift = int(np.argmax(scores))
        level = np.roll(np.mean([W.channel_level(f) for f in ref_filts], axis=0), -shift)
        return {"shift": shift, "match": round(float(scores[shift]), 3), "level": level}

    def _adjust(self, F, align):
        if self.norm:
            F[..., :8] -= align["level"]
            F[..., 8:16] -= align["level"]
        return F

    def with_calibration(self, segments, align):
        """segments: list of (filtered (8, n) hold, class index). Returns a new model."""
        X, y = [], []
        for filt, c in segments:
            F = self._adjust(window_features(np.roll(filt, -align["shift"], axis=0), self.kind), align)
            X.append(F)
            y += [c] * len(F)
        return CrossWearModel(clf=self.clf_name, kind=self.kind, norm=self.norm,
                              _base=self, _extra=(np.vstack(X), np.array(y)))

    def proba(self, win, align):
        f = self._adjust(features(np.roll(win, -align["shift"], axis=0), self.kind), align)
        p = np.zeros(len(self.names))
        p[self.clf.classes] = self.clf.proba(f)[0]
        return p

    def summary(self):
        return {"wears": len(self.wears), "ids": [w.id for w in self.wears], "clf": self.clf_name,
                "kind": self.kind, "norm": self.norm, "calibrated": self.calibrated}
