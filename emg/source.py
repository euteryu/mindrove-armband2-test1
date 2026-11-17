"""Data sources: the real MindRove armband (via the official SDK) and a simulator.

Both expose the same interface so everything above this file is hardware-agnostic:

    start()            open the connection (may raise)
    read() -> dict     new samples since the last call, or None if nothing arrived
    set_mode(name)     "emg" | "impedance" | "test"
    hint(label)        simulator only: which pose the fake hand should hold
    stop()

A chunk is a dict of numpy arrays, samples along the last axis:
    emg (8, n) microvolts, acc (3, n), gyro (3, n), counter (n,),
    battery (float or None), resistance (10,) or None, raw (rows, n)
"""
import time
import zlib

import numpy as np

N_CH = 8
FS = 500


class MindRoveSource:
    name = "MindRove armband (Wi-Fi)"
    is_sim = False

    def __init__(self):
        from mindrove.board_shim import BoardIds, BoardShim, MindRoveInputParams

        self._BoardShim, self._Params = BoardShim, MindRoveInputParams
        self.bid = BoardIds.MINDROVE_WIFI_BOARD.value
        d = BoardShim.get_board_descr(self.bid)
        self.fs = int(d["sampling_rate"])
        self.emg_rows = d["emg_channels"]
        self.acc_rows = d["accel_channels"]
        self.gyro_rows = d["gyro_channels"]
        self.res_rows = d.get("resistance_channels", [])
        self.counter_row = d["package_num_channel"]
        self.battery_row = d["battery_channel"]
        self.board = None
        self.mode = "emg"
        BoardShim.disable_board_logger()

    def start(self):
        self.stop()
        self.board = self._BoardShim(self.bid, self._Params())
        self.board.prepare_session()
        self.board.start_stream(450000)
        self.mode = "emg"

    def read(self):
        if self.board is None or self.board.get_board_data_count() == 0:
            return None
        raw = self.board.get_board_data()
        if raw.shape[1] == 0:
            return None
        return {
            "emg": raw[self.emg_rows],
            "acc": raw[self.acc_rows],
            "gyro": raw[self.gyro_rows],
            "counter": raw[self.counter_row],
            "battery": float(raw[self.battery_row, -1]),
            "resistance": raw[self.res_rows, -1] if self.res_rows else None,
            "raw": raw,
        }

    def set_mode(self, mode):
        from mindrove.board_shim import MindroveConfigMode as M

        if self.board is None:
            return
        # Always return to plain measurement first, as MindRove's boardconfig example does.
        self.board.config_board(M.EEG_MODE)
        if mode == "impedance":
            self.board.config_board(M.IMP_MODE)
        elif mode == "test":
            self.board.config_board(M.TEST_MODE)
        self.mode = mode

    def hint(self, label):
        pass

    def stop(self):
        if self.board is not None:
            try:
                self.board.release_session()
            except Exception:
                pass
            self.board = None


# Per-channel muscle activity (microvolts RMS) for each simulated pose.
_POSES = {
    "rest": [0, 0, 0, 0, 0, 0, 0, 0],
    "fist": [60, 80, 70, 50, 60, 90, 80, 55],
    "open": [70, 90, 45, 10, 8, 10, 20, 50],
    "wrist_out": [95, 60, 15, 6, 5, 6, 12, 75],
    "wrist_in": [8, 10, 30, 80, 90, 70, 25, 10],
    "pinch": [12, 10, 12, 40, 22, 60, 50, 18],
    "rotate": [20, 25, 20, 20, 25, 20, 20, 25],
}


def _pose_pattern(label):
    if label in _POSES:
        return np.array(_POSES[label], float)
    rng = np.random.default_rng(zlib.crc32(label.encode()))
    return rng.uniform(5, 85, N_CH)


class SimSource:
    """Fake armband for trying the app without hardware. Faults can be planted on
    channels (1-based) to prove the health check catches them, e.g.
    {"dead": [3], "hum": [5], "noisy": [7], "weak": [2], "drop": True}."""

    name = "Simulator"
    is_sim = True
    fs = FS

    def __init__(self, faults=None, seed=None):
        self.faults = faults or {}
        self.rng = np.random.default_rng(seed)
        self.mode = "emg"
        self.pose = "rest"
        self.amp = np.zeros(N_CH)
        self.dc = self.rng.uniform(-4000, 4000, N_CH)
        self.n_done = 0
        self.t0 = None

    def start(self):
        self.t0 = time.perf_counter()
        self.n_done = 0

    def _ch(self, kind):
        return [c - 1 for c in self.faults.get(kind, [])]

    def read(self):
        if self.t0 is None:
            return None
        n = int((time.perf_counter() - self.t0) * self.fs) - self.n_done
        if n <= 0:
            return None
        idx = self.n_done + np.arange(n)
        t = idx / self.fs
        self.n_done += n

        target = _pose_pattern(self.pose)
        target[self._ch("weak")] *= 0.08
        frac = np.minimum(1.0, (np.arange(n) + 1) / (0.1 * self.fs))   # ~100 ms onset
        env = self.amp[:, None] + (target - self.amp)[:, None] * frac[None, :]
        self.amp = env[:, -1].copy()

        base = np.full(N_CH, 3.0)
        base[self._ch("noisy")] = 45.0
        emg = self.rng.standard_normal((N_CH, n)) * (env * self.rng.uniform(0.85, 1.15, (N_CH, 1)) + base[:, None])
        hum = np.full(N_CH, 2.0)
        hum[self._ch("hum")] = 400.0
        emg += hum[:, None] * np.sin(2 * np.pi * 50 * t)[None, :]
        emg += self.dc[:, None] + 30 * np.sin(2 * np.pi * 0.3 * t)[None, :]
        if self.mode == "test":
            emg = np.tile(1000.0 * np.sign(np.sin(2 * np.pi * 1.0 * t)), (N_CH, 1))
        emg[self._ch("dead")] = 0.0

        acc = np.array([[0.0], [0.0], [1.0]]) + 0.005 * self.rng.standard_normal((3, n))
        gyro = 0.5 * self.rng.standard_normal((3, n))
        if self.pose == "rotate":
            a = 1.2 * np.sin(2 * np.pi * 0.5 * t)
            acc = np.stack([np.sin(a), 0 * a, np.cos(a)]) + 0.005 * self.rng.standard_normal((3, n))
            gyro = gyro + np.stack([120 * np.cos(2 * np.pi * 0.5 * t), 0 * t, 0 * t])

        counter = idx.astype(float)
        if self.faults.get("drop") and n > 4:
            keep = self.rng.random(n) > 0.03
            emg, acc, gyro, counter = emg[:, keep], acc[:, keep], gyro[:, keep], counter[keep]
            if counter.size == 0:
                return None

        res = None
        if self.mode == "impedance":
            res = self.rng.uniform(40, 160, 10)
            res[self._ch("dead")] = 9999.0
        return {
            "emg": emg, "acc": acc, "gyro": gyro, "counter": counter,
            "battery": 4.02, "resistance": res,
            "raw": np.vstack([emg, acc, gyro, counter[None, :]]),
        }

    def set_mode(self, mode):
        self.mode = mode

    def hint(self, label):
        self.pose = label

    def stop(self):
        self.t0 = None


def parse_faults(text):
    """'dead:3,hum:5,drop' -> {'dead': [3], 'hum': [5], 'drop': True}"""
    out = {}
    for part in filter(None, (p.strip() for p in (text or "").split(","))):
        kind, _, ch = part.partition(":")
        if kind == "drop":
            out["drop"] = True
        else:
            out.setdefault(kind, []).append(int(ch))
    return out
