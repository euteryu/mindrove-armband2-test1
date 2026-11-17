"""Signal processing: the streaming EMG filter and the features used for gestures."""
import numpy as np
from scipy import signal

BAND = (20.0, 200.0)   # where surface-EMG energy lives; below 20 Hz is mostly motion artefact
WIN = 100              # 200 ms analysis window at 500 Hz
HOP = 25               # 50 ms between windows


class StreamFilter:
    """Band-pass 20-200 Hz plus notches at mains and its harmonics, applied chunk by
    chunk with state carried over so there are no glitches at chunk edges."""

    def __init__(self, fs, n_ch, mains=50):
        sos = signal.butter(4, BAND, "bandpass", fs=fs, output="sos")
        for k in (1, 2, 3):
            f = mains * k
            if f < fs / 2 - 10:
                sos = np.vstack([sos, signal.tf2sos(*signal.iirnotch(f, 30, fs))])
        self.sos = sos
        self.n_ch = n_ch
        self.zi = None

    def reset(self):
        self.zi = None

    def __call__(self, x):
        if self.zi is None:
            # Start from the steady state for the first sample, so the electrode DC
            # offset does not ring through the filter at start-up.
            self.zi = signal.sosfilt_zi(self.sos)[:, None, :] * x[:, :1][None, :, :]
        y, self.zi = signal.sosfilt(self.sos, x, axis=1, zi=self.zi)
        return y


def rms(x, axis=-1):
    return np.sqrt(np.mean(np.square(x), axis=axis))


def features(win):
    """(n_ch, n) filtered window -> feature vector: log RMS and log waveform length
    per channel. Amplitude says how hard a muscle fires, waveform length adds
    frequency content; logs make the values roughly Gaussian for LDA."""
    r = rms(win)
    wl = np.mean(np.abs(np.diff(win, axis=1)), axis=1)
    return np.concatenate([np.log(r + 1e-3), np.log(wl + 1e-3)])


def window_features(seg):
    """(n_ch, n) segment -> (n_windows, n_features)"""
    out = [features(seg[:, s:s + WIN]) for s in range(0, seg.shape[1] - WIN + 1, HOP)]
    return np.array(out)
