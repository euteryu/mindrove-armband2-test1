"""Turning per-window probabilities into actions without false triggers.

A classifier always picks some class, so on its own every stray movement would fire a
gesture. The decider only fires when:
  1. the smoothed probability of a gesture is at least `threshold`, and
  2. that gesture has stayed on top for `dwell` consecutive windows (dwell x 50 ms).
Anything else counts as rest. `rest` and `other` (junk movement) are both rest.
An active gesture is released as soon as its own probability falls below `release`,
so going straight from one gesture to another never leaves the old one stuck on.
"""
import numpy as np


class Decider:
    def __init__(self, names, threshold=0.7, dwell=4, alpha=0.4, rest=("rest", "other"), release=0.5):
        self.names = list(names)
        self.rest_idx = {i for i, n in enumerate(self.names) if n in rest}
        self.threshold, self.dwell, self.alpha = threshold, dwell, alpha
        self.release = min(release, threshold)
        self.reset()

    def reset(self):
        self.p = None
        self.cand, self.count = None, 0
        self.out = None          # currently active gesture index, None = rest

    def step(self, prob):
        """One window's probabilities -> (active gesture index or None, fired: bool)."""
        self.p = prob if self.p is None else (1 - self.alpha) * self.p + self.alpha * prob
        k = int(np.argmax(self.p))
        if self.out is not None and self.p[self.out] < self.release:
            self.out = None
        if k in self.rest_idx or self.p[k] < self.threshold:
            self.cand, self.count = None, 0
            if k in self.rest_idx:
                self.out = None
            return self.out, False
        if k == self.cand:
            self.count += 1
        else:
            self.cand, self.count = k, 1
        if self.count >= self.dwell and k != self.out:
            self.out = k
            return k, True
        return self.out, False

    def run(self, probs):
        """(n, k) probabilities of consecutive windows -> list of fired gesture indices."""
        self.reset()
        return [k for k, fired in (self.step(p) for p in probs) if fired]
