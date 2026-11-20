"""A small neural network (multi-layer perceptron) in plain numpy.

Same interface as gestures.LDA (fit / proba / predict / classes), so it drops into the
evaluator and the cross-wear model. Plain numpy on purpose: no PyTorch install, and it
runs unchanged on a Raspberry Pi. Training a few thousand windows takes seconds on CPU.

Why it can beat LDA here: LDA gives every class one average pattern, which suits clean
held gestures but not the "other" class (junk), which is many different movements. A
network with a hidden layer can carve out several regions for it.
"""
import numpy as np


class MLP:
    def __init__(self, hidden=(64, 64), epochs=40, lr=2e-3, l2=1e-4, dropout=0.2,
                 batch=128, seed=0, class_weight=True):
        self.hidden, self.epochs, self.lr, self.l2 = hidden, epochs, lr, l2
        self.dropout, self.batch, self.seed, self.class_weight = dropout, batch, seed, class_weight

    def fit(self, X, y):
        rng = np.random.default_rng(self.seed)
        self.mu, self.sd = X.mean(0), X.std(0) + 1e-9
        Z = (X - self.mu) / self.sd
        self.classes = np.unique(y)
        idx = np.searchsorted(self.classes, y)
        k = len(self.classes)
        sizes = [Z.shape[1], *self.hidden, k]
        self.W = [rng.normal(0, np.sqrt(2 / a), (a, b)) for a, b in zip(sizes[:-1], sizes[1:])]
        self.b = [np.zeros(b) for b in sizes[1:]]
        counts = np.bincount(idx, minlength=k)
        cw = (len(idx) / (k * np.maximum(counts, 1))) if self.class_weight else np.ones(k)
        params = self.W + self.b
        m = [np.zeros_like(p) for p in params]
        v = [np.zeros_like(p) for p in params]
        t = 0
        for _ in range(self.epochs):
            order = rng.permutation(len(Z))
            for s in range(0, len(Z), self.batch):
                bi = order[s:s + self.batch]
                grads = self._grads(Z[bi], idx[bi], cw, rng)
                t += 1
                for j, (p, g) in enumerate(zip(params, grads)):
                    m[j] = 0.9 * m[j] + 0.1 * g
                    v[j] = 0.999 * v[j] + 0.001 * g * g
                    p -= self.lr * (m[j] / (1 - 0.9 ** t)) / (np.sqrt(v[j] / (1 - 0.999 ** t)) + 1e-8)
        return self

    def _forward(self, Z, rng=None):
        acts = [Z]
        h = Z
        masks = []
        for W, b in zip(self.W[:-1], self.b[:-1]):
            h = np.maximum(0, h @ W + b)
            if rng is not None and self.dropout:
                mk = (rng.random(h.shape) > self.dropout) / (1 - self.dropout)
                h = h * mk
                masks.append(mk)
            else:
                masks.append(None)
            acts.append(h)
        s = h @ self.W[-1] + self.b[-1]
        s -= s.max(1, keepdims=True)
        e = np.exp(s)
        return acts, masks, e / e.sum(1, keepdims=True)

    def _grads(self, Z, idx, cw, rng):
        acts, masks, P = self._forward(Z, rng)
        n = len(Z)
        w = cw[idx][:, None]
        d = P.copy()
        d[np.arange(n), idx] -= 1
        d *= w / w.sum()
        gW, gb = [None] * len(self.W), [None] * len(self.b)
        for L in range(len(self.W) - 1, -1, -1):
            gW[L] = acts[L].T @ d + self.l2 * self.W[L]
            gb[L] = d.sum(0)
            if L:
                d = (d @ self.W[L].T) * (acts[L] > 0)
                if masks[L - 1] is not None:
                    d *= masks[L - 1]
        return gW + gb

    def proba(self, X):
        Z = (np.atleast_2d(X) - self.mu) / self.sd
        return self._forward(Z)[2]

    def predict(self, X):
        return self.classes[np.argmax(self.proba(X), axis=1)]
