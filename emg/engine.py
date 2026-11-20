"""The engine: one background thread that owns the armband connection.

It pulls samples, filters them, tracks link quality, runs the guided protocols (device
check and gesture training) and publishes JSON messages for any front-end to consume.
It has no UI dependency, so it runs the same on a laptop or a headless Linux board.
"""
import json
import queue
import re
import threading
import time
import traceback
from collections import deque
from pathlib import Path

import numpy as np

from . import health, wear
from .dsp import HOP, WIN, StreamFilter, features, rms, window_features
from .gestures import GestureModel
from .recorder import Recorder

TICK = 0.05
TRIM_START = 0.8   # seconds dropped from the start of each hold (reaction time)
TRIM_END = 0.2

STEP_INFO = {
    "rest": ("😌", "Relax. Let your hand and forearm go completely limp."),
    "fist": ("✊", "Make a tight fist and keep squeezing."),
    "open": ("🖐", "Spread your fingers wide open."),
    "pinch": ("🤏", "Pinch thumb and index finger together firmly."),
    "point": ("☝", "Point with your index finger, other fingers curled."),
    "thumbs_up": ("👍", "Thumbs up, other fingers curled."),
    "wrist_out": ("↗", "Bend your wrist back, so the back of your hand moves toward your forearm."),
    "wrist_in": ("↙", "Curl your wrist inward, palm toward your forearm."),
    "spiderman": ("🤟", "Spider-Man: thumb, index and pinky straight out; middle and ring fingers folded onto the palm."),
    "other": ("🌀", "Everyday movement that is not one of the gestures."),
    "rotate": ("🔄", "Relax your hand and slowly twist your forearm back and forth, like turning a door knob."),
}
CHECK_STEPS = [("rest", 6), ("fist", 5), ("wrist_out", 5), ("wrist_in", 5), ("rotate", 5)]
DEFAULT_GESTURES = ["rest", "fist", "open", "wrist_in", "wrist_out"]


def _step(label, hold, prep=3.0, **extra):
    emoji, text = STEP_INFO.get(label, ("✋", f"Hold the gesture: {label.replace('_', ' ')}."))
    return dict(label=label, emoji=emoji, text=text, prep=prep, hold=float(hold), **extra)


class Engine(threading.Thread):
    def __init__(self, source, mains=50, data_dir="data"):
        super().__init__(daemon=True)
        self.source, self.mains, self.fs = source, mains, source.fs
        self.data_dir = Path(data_dir)
        self.filter = StreamFilter(self.fs, 8, mains)
        self.ring = np.zeros((8, WIN))
        self.cmds = queue.Queue()
        self.subs, self.subs_lock = set(), threading.Lock()
        self._halt = threading.Event()

        self.connected, self.next_try, self.last_data = False, 0.0, 0.0
        self.status, self.status_msg = "connecting", ""
        self.mode = "emg"
        self.battery = None
        self.resistance = None
        self.dc = np.zeros(8)
        self._reset_link()

        self.proto = None
        self.report, self.report_dir = None, None
        self.model, self.p_smooth = None, None
        self.gestures, self.reps, self.hold = list(DEFAULT_GESTURES), 3, 4.0
        self.notice = ""
        self.rec, self.last_rec_dir = None, None
        self._load_model()

    # ---- pub/sub -------------------------------------------------------------
    def subscribe(self):
        q = queue.Queue(maxsize=200)
        q.put(self._state_json())
        with self.subs_lock:
            self.subs.add(q)
        return q

    def unsubscribe(self, q):
        with self.subs_lock:
            self.subs.discard(q)

    def _broadcast(self, text):
        with self.subs_lock:
            for q in self.subs:
                try:
                    q.put_nowait(text)
                except queue.Full:
                    pass   # slow client: drop frames rather than stall acquisition

    def _state_json(self):
        return json.dumps({
            "t": "state", "fs": self.fs, "sim": self.source.is_sim, "source": self.source.name,
            "mode": self.mode, "mains": self.mains, "report": self.report,
            "report_dir": str(self.report_dir) if self.report_dir else None,
            "model": self.model.summary if self.model else None,
            "gestures": self.gestures, "reps": self.reps, "hold": self.hold,
            "step_info": STEP_INFO, "notice": self.notice,
            "rec_dir": str(self.last_rec_dir) if self.last_rec_dir else None,
        })

    def command(self, cmd):
        self.cmds.put(cmd)

    def stop(self):
        self._halt.set()

    # ---- main loop -----------------------------------------------------------
    def run(self):
        while not self._halt.is_set():
            t = time.perf_counter()
            try:
                self._handle_cmds()
                self._tick(t)
            except Exception as e:
                traceback.print_exc()
                self.status, self.status_msg = "error", f"{type(e).__name__}: {e}"
                self.connected, self.next_try = False, t + 3
            self._halt.wait(max(0.0, TICK - (time.perf_counter() - t)))
        self._rec_stop()
        self.source.stop()

    # ---- session recording ---------------------------------------------------
    def _rec_start(self):
        if self.rec:
            return
        self.rec = Recorder(self.data_dir, self.fs, self.source.name, self.mains)
        self.last_rec_dir = self.rec.dir.resolve()

    def _rec_stop(self):
        if self.rec:
            rec, self.rec = self.rec, None
            rec.close()

    def _reset_link(self):
        self.total, self.lost = 0, 0
        self.last_counter, self.counter_step = None, None
        self.rate_win = deque()
        self.rate = 0.0

    def _tick(self, now):
        msg = {"t": "tick", "emg": [], "rms": None, "pred": None}
        if not self.connected:
            if now >= self.next_try:
                self.source.start()
                self.connected, self.last_data = True, now
                self.filter.reset()
                self._reset_link()
                self.status, self.status_msg = "connecting", ""
                if self.mode != "emg":   # a fresh session always starts in normal mode
                    self.mode = "emg"
                    self._broadcast(self._state_json())
            chunk = None
        else:
            chunk = self.source.read()

        if chunk is None:
            if self.connected and now - self.last_data > 4.0:
                # The SDK gives up on its socket after ~3 s of silence, so reopen it.
                self.connected, self.next_try = False, now
                self.status = "no_data"
                self._abort_proto("Lost the data stream, so the recording was cancelled.")
            elif self.connected and now - self.last_data > 1.0:
                self.status = "no_data"
        else:
            self.last_data, self.status = now, "streaming"
            emg = chunk["emg"]
            n = emg.shape[1]
            self._update_link(now, chunk["counter"], n)
            self.battery, self.resistance = chunk["battery"], chunk["resistance"]
            filt = self.filter(emg)
            self.ring = np.concatenate([self.ring, filt], axis=1)[:, -WIN:]
            if self.mode == "test":   # show the raw test waveform, just centred
                self.dc += 0.05 * (emg.mean(1) - self.dc)
                shown = emg - self.dc[:, None]
            else:
                shown = filt
            msg["emg"] = np.round(shown, 1).tolist()
            msg["rms"] = np.round(rms(self.ring), 2).tolist()
            msg["acc"] = np.round(chunk["acc"][:, -1], 3).tolist()
            msg["gyro"] = np.round(chunk["gyro"][:, -1], 2).tolist()
            if self.mode == "impedance" and self.resistance is not None:
                msg["imp"] = np.round(self.resistance, 1).tolist()
            if self.proto:
                if self.proto["phase"] == "hold":
                    self.proto["data"][self.proto["i"]].append((chunk, filt))
            elif self.model and self.mode == "emg":
                p = self.model.proba(features(self.ring))
                self.p_smooth = p if self.p_smooth is None else 0.6 * self.p_smooth + 0.4 * p
                k = int(np.argmax(self.p_smooth))
                msg["pred"] = {"label": self.model.names[k], "conf": round(float(self.p_smooth[k]), 3),
                               "probs": np.round(self.p_smooth, 3).tolist()}
            if self.rec:
                pr, pd = self.proto, msg["pred"]
                try:
                    self.rec.write(chunk, activity=self.rec.activity, prompt=pr["steps"][pr["i"]]["label"] if pr else "",
                                   phase=pr["phase"] if pr else "",
                                   pred=pd["label"] if pd else "", conf=pd["conf"] if pd else None)
                except OSError as e:
                    self._rec_stop()
                    self.notice = f"Recording stopped: could not write to disk ({e})."
                    self._broadcast(self._state_json())

        if self.proto:
            self._advance_proto(now)
        msg["status"], msg["status_msg"] = self.status, self.status_msg
        msg["rec"] = self.rec and {"dir": str(self.rec.dir.resolve()), "secs": round(self.rec.seconds, 1),
                                   "activity": self.rec.activity,
                                   "markers": self.rec.n_markers}
        msg["link"] = {"rate": round(self.rate, 1), "battery": self.battery,
                       "loss_pct": round(100 * self.lost / max(1, self.lost + self.total), 3)}
        p = self.proto
        msg["proto"] = p and {
            "kind": p["kind"], "i": p["i"], "n": len(p["steps"]), "phase": p["phase"],
            "left": round(max(0.0, p["t_end"] - now), 2), "step": p["steps"][p["i"]],
            "next": p["steps"][p["i"] + 1]["label"] if p["i"] + 1 < len(p["steps"]) else None,
        }
        self._broadcast(json.dumps(msg))

    def _update_link(self, now, counter, n):
        self.total += n
        self.rate_win.append((now, n))
        while now - self.rate_win[0][0] > 3.0:
            self.rate_win.popleft()
        if len(self.rate_win) > 2:
            span = self.rate_win[-1][0] - self.rate_win[0][0]
            self.rate = sum(c for _, c in list(self.rate_win)[1:]) / span
        # Packet counter: learn its normal step, then count anything bigger as loss.
        c = counter if self.last_counter is None else np.concatenate([[self.last_counter], counter])
        d = np.diff(c)
        d = d[d > 0]   # ignore wrap-around / resets
        if self.counter_step is None and d.size >= 8:
            self.counter_step = float(np.median(d))
        if self.counter_step and d.size:
            self.lost += int(round(np.sum(d[d > self.counter_step] / self.counter_step - 1)))
        self.last_counter = counter[-1]

    # ---- commands ------------------------------------------------------------
    def _handle_cmds(self):
        while True:
            try:
                cmd = self.cmds.get_nowait()
            except queue.Empty:
                return
            op = cmd.get("op")
            self.notice = ""
            if op == "cancel":
                self._abort_proto("")
            elif op == "rec_start":
                self._rec_start()
                self._broadcast(self._state_json())
            elif op == "rec_stop":
                self._rec_stop()
                self._broadcast(self._state_json())
            elif op == "activity":
                if self.rec:
                    act = re.sub(r"[^\w ]", "", str(cmd.get("label", "")))[:40].strip().replace(" ", "_")
                    if act != self.rec.activity:
                        self.rec.activity = act
                        self.rec.marker(f"activity -> {act or '(none)'}")
            elif op == "marker":
                text = str(cmd.get("text", "")).strip()[:200]
                if self.rec and text:
                    self.rec.marker(text)
            elif op == "pose":
                self.source.hint(str(cmd.get("label", "rest")))
            elif op == "mode" and cmd.get("mode") in ("emg", "impedance", "test"):
                if self.connected and not self.proto:
                    self.source.set_mode(cmd["mode"])
                    self.mode = cmd["mode"]
                    self.filter.reset()
            elif op in ("check", "train", "wear"):
                if self.status != "streaming":
                    self.notice = "No data from the armband yet, so nothing can be recorded."
                elif self.proto:
                    self.notice = "A recording is already running."
                else:
                    if self.mode != "emg":
                        self.source.set_mode("emg")
                        self.mode = "emg"
                        self.filter.reset()
                    extra = {}
                    if op == "check":
                        steps = [_step(lbl, hold) for lbl, hold in CHECK_STEPS]
                    elif op == "wear":
                        steps = wear.protocol_steps(_step)
                        extra["note"] = str(cmd.get("note", "")).strip()[:200]
                    else:
                        steps = self._training_steps(cmd)
                    if steps:
                        self._start_proto(op, steps, **extra)
            self._broadcast(self._state_json())

    def _training_steps(self, cmd):
        names = []
        for g in cmd.get("gestures", []):
            g = re.sub(r"[^a-z0-9]+", "_", str(g).lower()).strip("_")[:24]
            if g and g not in names:
                names.append(g)
        if len(names) < 2:
            self.notice = "Add at least two gestures to train."
            return None
        self.gestures = names
        self.reps = int(min(8, max(2, cmd.get("reps", 3))))
        self.hold = float(min(8, max(2, cmd.get("hold", 4))))
        return [_step(g, self.hold, prep=3.0 if (r, k) == (0, 0) else 2.0, rep=r, cls=k)
                for r in range(self.reps) for k, g in enumerate(names)]

    # ---- guided protocols ----------------------------------------------------
    def _start_proto(self, kind, steps, **extra):
        now = time.perf_counter()
        self.proto = {"kind": kind, "steps": steps, "i": 0, "phase": "prep",
                      "t_end": now + steps[0]["prep"], "data": [[] for _ in steps],
                      "t0": now, "total0": self.total, "lost0": self.lost, **extra}
        self.source.hint(steps[0]["label"])

    def _abort_proto(self, why):
        if self.proto:
            self.proto = None
            self.source.hint("rest")
            self.notice = why
            self._broadcast(self._state_json())

    def _advance_proto(self, now):
        p = self.proto
        if now < p["t_end"]:
            return
        if p["phase"] == "prep":
            p["phase"], p["t_end"] = "hold", now + p["steps"][p["i"]]["hold"]
            return
        p["i"] += 1
        if p["i"] < len(p["steps"]):
            p["phase"], p["t_end"] = "prep", now + p["steps"][p["i"]]["prep"]
            self.source.hint(p["steps"][p["i"]]["label"])
            return
        p["i"] -= 1
        self.proto = None
        self.source.hint("rest")
        try:
            {"check": self._finish_check, "train": self._finish_training,
             "wear": self._finish_wear}[p["kind"]](p, now)
        except Exception as e:
            traceback.print_exc()
            self.notice = f"Could not process the recording ({type(e).__name__}: {e}). Please run it again."
        self._broadcast(self._state_json())

    def _segments(self, p):
        """Per step: dict of arrays with the reaction-time edges trimmed off."""
        a, b = int(TRIM_START * self.fs), int(TRIM_END * self.fs)
        out = []
        for chunks in p["data"]:
            if not chunks:
                raise RuntimeError("a step recorded no data")
            seg = {k: np.concatenate([c[k] for c, _ in chunks], axis=1) for k in ("emg", "acc", "gyro")}
            seg["raw"] = seg.pop("emg")
            seg["filt"] = np.concatenate([f for _, f in chunks], axis=1)
            seg = {k: v[:, a:v.shape[1] - b] for k, v in seg.items()}
            if seg["filt"].shape[1] < WIN + HOP:
                raise RuntimeError("a step recorded too little data")
            out.append(seg)
        return out

    def _finish_check(self, p, now):
        segs = self._segments(p)
        phases = {s["label"]: seg for s, seg in zip(p["steps"], segs)}
        got, lost = self.total - p["total0"], self.lost - p["lost0"]
        link = {"rate": got / (now - p["t0"]), "loss_pct": 100 * lost / max(1, got + lost),
                "battery": self.battery}
        self.report = health.analyze(phases, link, self.fs, self.mains)
        self.report["when"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self.report["source"] = self.source.name
        out = self.data_dir / "checks" / time.strftime("%Y%m%d_%H%M%S")
        out.mkdir(parents=True, exist_ok=True)
        (out / "report.txt").write_text(health.to_text(self.report), encoding="utf-8")
        (out / "report.json").write_text(json.dumps(self.report, indent=1), encoding="utf-8")
        np.savez_compressed(out / "recording.npz", fs=self.fs,
                            **{f"{k}_{name}": v for name, seg in phases.items() for k, v in seg.items()})
        self.report_dir = out.resolve()

    def _finish_training(self, p, now):
        X, y, reps = [], [], []
        for s, seg in zip(p["steps"], self._segments(p)):
            f = window_features(seg["filt"])
            X.append(f)
            y += [s["cls"]] * len(f)
            reps += [s["rep"]] * len(f)
        self.model = GestureModel(self.gestures, np.vstack(X), np.array(y), np.array(reps))
        self.p_smooth = None
        out = self.data_dir / "models"
        out.mkdir(parents=True, exist_ok=True)
        self.model.save(out / "latest.npz")
        self.model.save(out / time.strftime("model_%Y%m%d_%H%M%S.npz"))

    def _finish_wear(self, p, now):
        segs = self._segments(p)
        got, lost = self.total - p["total0"], self.lost - p["lost0"]
        meta = {"started": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - (now - p["t0"]))),
                "source": self.source.name, "fs": self.fs, "mains_hz": self.mains,
                "note": p.get("note", ""), "loss_pct": round(100 * lost / max(1, got + lost), 3),
                "classes": wear.CLASSES}
        out = wear.save(self.data_dir, p["steps"], segs, meta)
        # Train the live model on this wear alone, so it is usable straight away; the
        # cross-wear models are built offline by tools/evaluate.py.
        w = wear.windows(wear.Wear(out))
        self.model = GestureModel(wear.CLASSES, w["X"], w["y"], w["group"])
        self.p_smooth = None
        models = self.data_dir / "models"
        models.mkdir(parents=True, exist_ok=True)
        self.model.save(models / "latest.npz")
        self.model.save(models / time.strftime("model_%Y%m%d_%H%M%S.npz"))
        self.notice = f"Wear session saved to {out.resolve()}"

    def _load_model(self):
        path = self.data_dir / "models" / "latest.npz"
        if path.exists():
            try:
                self.model = GestureModel.load(path)
                self.gestures = [g for g in self.model.names if g != wear.OTHER]
            except Exception:
                traceback.print_exc()
