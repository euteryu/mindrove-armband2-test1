"""Device health check: turns the recordings from the guided steps into verdicts.

The thresholds are engineering judgement for dry-electrode forearm EMG, not values
published by MindRove. They are deliberately relative (channel vs. its own rest level,
channel vs. the other channels) so they do not depend on exact unit scaling.
"""
import numpy as np
from scipy import signal

from .dsp import rms, WIN, HOP

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"
ACTIVE_STEPS = ("fist", "wrist_out", "wrist_in")
_RANK = {PASS: 0, WARN: 1, FAIL: 2}


def _worst(items):
    return max((i["verdict"] for i in items), key=_RANK.get, default=PASS)


def _robust_rms(x, keep=None):
    """Median of 200 ms window RMS: a short burst (a twitch, a bump of the band)
    cannot dominate it the way it dominates one RMS over the whole step.
    keep: optional boolean mask of samples to use."""
    if keep is not None and keep.sum() >= WIN:
        x = x[:, keep]
    starts = range(0, max(x.shape[1] - WIN, 0) + 1, HOP)
    return np.median(np.array([rms(x[:, s:s + WIN]) for s in starts]), axis=0)


def _motion(x, blk):
    """Per-sample motion level: max-over-axes std of the IMU signal in blocks of blk samples."""
    n = x.shape[1]
    out = np.zeros(n)
    for s in range(0, n, blk):
        out[s:s + blk] = np.std(x[:, s:s + blk], axis=1).max() if x[:, s:s + blk].shape[1] > 1 else 0
    return out


def analyze(phases, link, fs, mains):
    """phases: {label: {"raw": (8,n), "filt": (8,n), "acc": (3,n), "gyro": (3,n)}}
    link: {"rate", "loss_pct", "battery"} measured over the whole check."""
    rest = phases["rest"]
    n_ch = rest["raw"].shape[0]
    # The rest baseline is only valid while the arm is actually still. Find the
    # moving parts of the rest step from the gyroscope and leave them out.
    blk = fs // 2
    gmot = _motion(rest["gyro"], blk)
    if "rotate" in phases:
        moving_level = np.median(_motion(phases["rotate"]["gyro"], blk))
        thr = 0.2 * moving_level if moving_level > 0 else np.inf
    else:
        thr = 10 * max(gmot.min(), 1e-9)
    still = gmot <= max(thr, 3 * gmot.min())
    rest_moved = bool((~still).any())
    rest_still_s = still.sum() / fs
    rest_rms = _robust_rms(rest["filt"], still)
    act_rms = {k: _robust_rms(phases[k]["filt"]) for k in ACTIVE_STEPS if k in phases}
    best = np.max(np.array(list(act_rms.values())), axis=0)
    best_step = np.array(list(act_rms))[np.argmax(np.array(list(act_rms.values())), axis=0)]

    raw_still = rest["raw"][:, still] if still.sum() >= fs else rest["raw"]
    f, p = signal.welch(raw_still - raw_still.mean(1, keepdims=True), fs, nperseg=min(fs, raw_still.shape[1]), axis=1)
    hum = p[:, np.abs(f - mains) <= 2].sum(1) / np.maximum(p[:, f >= 10].sum(1), 1e-12)

    channels = []
    for c in range(n_ch):
        raw_all = np.concatenate([ph["raw"][c] for ph in phases.values()])
        others = np.median(np.delete(rest_rms, c))
        gain_db = 20 * np.log10(max(best[c], 1e-9) / max(rest_rms[c], 1e-9))
        notes, verdict = [], PASS

        def flag(v, text):
            nonlocal verdict
            notes.append(text)
            if _RANK[v] > _RANK[verdict]:
                verdict = v

        if np.std(raw_all) < 1e-6 or np.unique(raw_all).size < 8:
            flag(FAIL, "No signal at all: the channel is flat or stuck on one value.")
        else:
            if gain_db < 6:
                flag(FAIL, "Barely reacts to muscle effort (under 6 dB above rest).")
            elif gain_db < 12:
                flag(WARN, "Weak reaction to muscle effort (6-12 dB above rest).")
            if rest_rms[c] > 3 * others and rest_rms[c] > 10:
                flag(WARN, "Much noisier at rest than the other channels: usually poor skin contact.")
            if hum[c] > 0.5:
                flag(WARN, f"Mostly {mains} Hz mains hum at rest: usually poor skin contact.")
        if not notes:
            notes.append("Quiet at rest and clearly responds to effort.")
        channels.append({
            "ch": c + 1, "verdict": verdict, "notes": notes,
            "rest_uv": round(float(rest_rms[c]), 2),
            "active_uv": round(float(best[c]), 2),
            "best_step": str(best_step[c]),
            "gain_db": round(float(gain_db), 1),
            "hum_pct": round(float(100 * hum[c]), 1),
        })

    device = []

    def dev(name, verdict, value, note):
        device.append({"name": name, "verdict": verdict, "value": value, "note": note})

    rate, loss = link["rate"], link["loss_pct"]
    dev("Sample rate", PASS if abs(rate - fs) < 0.02 * fs else WARN if abs(rate - fs) < 0.08 * fs else FAIL,
        f"{rate:.0f} Hz", f"Expected {fs} Hz. A low rate means samples are being lost on the Wi-Fi link.")
    dev("Dropped samples", PASS if loss < 0.5 else WARN if loss < 3 else FAIL,
        f"{loss:.2f} %", "From the band's packet counter. Loss points to Wi-Fi or a low battery, not electrodes.")
    b = link.get("battery")
    if b is not None:
        dev("Battery", PASS, f"{b:.2f}", "Raw value reported by the band (shown for reference, not judged).")
    if rest_moved:
        dev("Still at rest", WARN if rest_still_s >= 2 else FAIL, f"{rest_still_s:.1f} s still",
            "The arm moved during the rest step (seen on the gyroscope); only the still part was used "
            "as the baseline." + ("" if rest_still_s >= 2 else " Too little was still: rerun and keep the "
                                  "arm relaxed and motionless during rest."))
    if "rotate" in phases:
        for key, label in (("acc", "Accelerometer"), ("gyro", "Gyroscope")):
            x = phases["rotate"][key]
            base_x = phases["rest"][key][:, still] if still.sum() > 1 else phases["rest"][key]
            moved = float(np.median(_motion(x, blk)))
            base = float(np.median(_motion(base_x, blk)))
            if np.all(x == 0) or moved == 0:
                dev(label, FAIL, "no data", "All zeros while rotating the arm.")
            elif moved > 3 * base:
                dev(label, PASS, f"{moved / max(base, 1e-9):.0f}x rest", "Readings change when the arm rotates.")
            else:
                dev(label, WARN, f"{moved / max(base, 1e-9):.1f}x rest",
                    "Hardly changed during the rotate step. Rerun and rotate the forearm more.")

    n_fail = sum(c["verdict"] == FAIL for c in channels)
    n_warn = sum(c["verdict"] == WARN for c in channels)
    overall = max(_worst(channels), _worst(device), key=_RANK.get)
    if overall == PASS:
        summary = "All 8 channels and the link look healthy."
    elif n_fail or n_warn:
        summary = (f"{n_fail} channel(s) failed, {n_warn} need attention. Dampen the skin, reseat the band "
                   "and rerun. Then rotate the band by one pod and rerun: a fault that follows the channel "
                   "number is the hardware, a fault that stays at the same place on your arm is contact.")
    else:
        summary = "Electrodes look fine; the issue is with the link or motion sensor (see below)."
    return {"overall": overall, "summary": summary, "channels": channels, "device": device}


def to_text(report):
    lines = [f"MindRove armband check: {report['overall']}", report["summary"], "",
             "ch  verdict  rest uV  active uV  gain dB  hum %  notes"]
    for c in report["channels"]:
        lines.append(f"{c['ch']:<3} {c['verdict']:<8} {c['rest_uv']:<8} {c['active_uv']:<10} "
                     f"{c['gain_db']:<8} {c['hum_pct']:<6} {' '.join(c['notes'])}")
    lines.append("")
    for d in report["device"]:
        lines.append(f"{d['name']:<16} {d['verdict']:<5} {d['value']:<12} {d['note']}")
    return "\n".join(lines) + "\n"
