"""Gesture recognition: a small regularised LDA classifier on per-channel features.

LDA is the standard baseline for armband EMG: it trains in milliseconds on a minute of
data, runs anywhere numpy does, and is hard to overfit. No scikit-learn needed, which
keeps the install light on a single-board computer.
"""
import json

import numpy as np


class LDA:
    def fit(self, X, y):
        self.mu, self.sd = X.mean(0), X.std(0) + 1e-9
        Z = (X - self.mu) / self.sd
        self.classes = np.unique(y)
        means = np.array([Z[y == c].mean(0) for c in self.classes])
        S = sum(np.cov(Z[y == c].T, bias=True) * np.sum(y == c) for c in self.classes) / len(Z)
        d = Z.shape[1]
        S = 0.9 * S + 0.1 * (np.trace(S) / d) * np.eye(d)   # shrinkage: stable with little data
        P = np.linalg.inv(S)
        self.W = means @ P
        self.b = -0.5 * np.einsum("ij,ij->i", self.W, means)
        return self

    def proba(self, X):
        s = ((np.atleast_2d(X) - self.mu) / self.sd) @ self.W.T + self.b
        s -= s.max(1, keepdims=True)
        e = np.exp(s)
        return e / e.sum(1, keepdims=True)

    def predict(self, X):
        return self.classes[np.argmax(self.proba(X), axis=1)]


class GestureModel:
    """Holds the training windows so the model can be re-fitted, scored and saved."""

    def __init__(self, names, X, y, reps):
        self.names, self.X, self.y, self.reps = list(names), X, y, reps
        self.lda = LDA().fit(X, y)
        self.summary = self._score()

    def _score(self):
        """Leave-one-round-out: train on all rounds but one, test on the held-out round.
        This is honest about what happens on data the model has not seen."""
        k = len(self.names)
        conf = np.zeros((k, k), int)
        rounds = np.unique(self.reps)
        if len(rounds) >= 2:
            for r in rounds:
                tr, te = self.reps != r, self.reps == r
                pred = LDA().fit(self.X[tr], self.y[tr]).predict(self.X[te])
                np.add.at(conf, (self.y[te], pred), 1)
        total = conf.sum()
        per = [float(conf[i, i] / conf[i].sum()) if conf[i].sum() else None for i in range(k)]
        return {
            "names": self.names,
            "accuracy": float(np.trace(conf) / total) if total else None,
            "per_gesture": per,
            "confusion": conf.tolist(),
            "rounds": int(len(rounds)),
            "windows": int(len(self.y)),
        }

    def proba(self, feat):
        p = np.zeros(len(self.names))
        p[self.lda.classes] = self.lda.proba(feat)[0]
        return p

    def save(self, path):
        np.savez(path, X=self.X, y=self.y, reps=self.reps, names=json.dumps(self.names))

    @classmethod
    def load(cls, path):
        d = np.load(path)
        return cls(json.loads(str(d["names"])), d["X"], d["y"], d["reps"])
