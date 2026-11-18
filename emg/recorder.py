"""Continuous session recorder: writes every sample to disk as it arrives.

One folder per recording, data/sessions/YYYYMMDD_HHMMSS/:
  signals.csv   one row per sample (see COLUMNS)
  markers.csv   free-text notes typed in the app, tied to a sample number
  meta.json     sample rate, source, start/stop time, column meanings

The EMG is stored raw (as the band sends it, DC offset included) so any filter can be
applied later; the app's own filter is described in meta.json.
"""
import csv
import json
import time
from pathlib import Path

import numpy as np

from .dsp import BAND

COLUMNS = (["sample", "host_time", "counter"]
           + [f"emg{c}" for c in range(1, 9)]
           + ["acc_x", "acc_y", "acc_z", "gyro_x", "gyro_y", "gyro_z",
              "activity", "prompt", "prompt_phase", "pred", "pred_conf"])

COLUMN_NOTES = {
    "sample": "running sample number from 0 at the start of this recording",
    "host_time": "laptop clock (Unix seconds) when the chunk holding this sample arrived; "
                 "samples in one chunk share it, use sample/fs for precise timing",
    "counter": "the band's own packet counter (gaps = samples lost on Wi-Fi)",
    "emg1..emg8": "raw EMG per channel in microvolts, unfiltered, DC offset included",
    "acc_*": "accelerometer, units as reported by the MindRove SDK",
    "gyro_*": "gyroscope, units as reported by the MindRove SDK",
    "activity": "ground-truth label YOU set in the app's Recording panel; applies to every sample "
                "until you change it",
    "prompt": "what the app was asking you to do (device check / gesture training step), "
              "empty when no guided recording was running",
    "prompt_phase": "prep = getting into position, hold = holding the gesture",
    "pred": "gesture the live recogniser output for this chunk (empty if no model or during training)",
    "pred_conf": "smoothed probability of that gesture, 0-1",
}

FLUSH_EVERY = 1.0   # seconds


class Recorder:
    def __init__(self, root, fs, source_name, mains):
        self.dir = Path(root) / "sessions" / time.strftime("%Y%m%d_%H%M%S")
        self.dir.mkdir(parents=True, exist_ok=True)
        self.fs = fs
        self.n = 0
        self.n_markers = 0
        self.t_start = time.time()
        self.last_flush = time.perf_counter()
        self.meta = {
            "fs": fs, "source": source_name, "mains_hz": mains,
            "started": time.strftime("%Y-%m-%d %H:%M:%S"),
            "app_filter_for_display_and_gestures": f"Butterworth band-pass {BAND[0]:g}-{BAND[1]:g} Hz "
                                                   f"(order 4) + notches at {mains}, {2*mains}, {3*mains} Hz",
            "columns": COLUMN_NOTES,
        }
        self._write_meta()
        self.f = open(self.dir / "signals.csv", "w", newline="", encoding="utf-8")
        self.w = csv.writer(self.f)
        self.w.writerow(COLUMNS)
        self.mf = open(self.dir / "markers.csv", "w", newline="", encoding="utf-8")
        self.mw = csv.writer(self.mf)
        self.mw.writerow(["sample", "host_time", "text"])
        self.activity = ""

    def _write_meta(self):
        (self.dir / "meta.json").write_text(json.dumps(self.meta, indent=1), encoding="utf-8")

    def write(self, chunk, activity="", prompt="", phase="", pred="", conf=None):
        emg, acc, gyro, cnt = chunk["emg"], chunk["acc"], chunk["gyro"], chunk["counter"]
        k = emg.shape[1]
        now = f"{time.time():.3f}"
        conf_s = "" if conf is None else f"{conf:.3f}"
        idx = np.arange(self.n, self.n + k)
        for j in range(k):
            self.w.writerow([idx[j], now, f"{cnt[j]:g}",
                             *(f"{v:.2f}" for v in emg[:, j]),
                             *(f"{v:.4f}" for v in acc[:, j]),
                             *(f"{v:.3f}" for v in gyro[:, j]),
                             activity, prompt, phase, pred, conf_s])
        self.n += k
        t = time.perf_counter()
        if t - self.last_flush > FLUSH_EVERY:
            self.f.flush()
            self.mf.flush()
            self.last_flush = t

    def marker(self, text):
        self.mw.writerow([self.n, f"{time.time():.3f}", text])
        self.mf.flush()
        self.n_markers += 1

    @property
    def seconds(self):
        return self.n / self.fs

    def close(self):
        self.f.close()
        self.mf.close()
        self.meta.update(stopped=time.strftime("%Y-%m-%d %H:%M:%S"), samples=self.n,
                         seconds=round(self.seconds, 2), markers=self.n_markers)
        self._write_meta()
