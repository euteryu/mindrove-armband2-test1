"""End-to-end smoke test on the simulator (no hardware, takes about 2 minutes).

    python tests/smoke.py

1. Healthy simulated band  -> device check must PASS on all 8 channels.
2. Band with planted faults -> each fault must be caught on the right channel.
3. Gesture training on 5 poses -> held-out accuracy must be high and the live
   prediction must follow the simulated hand.
4. Wear session (timings shortened) -> saved to disk, loads back, trains a model,
   and tools/evaluate.py runs on it.
"""
import json
import queue
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from emg import wear  # noqa: E402
from emg.engine import Engine  # noqa: E402
from emg.source import SimSource, parse_faults  # noqa: E402


def wait_state(q, pred, timeout):
    end = time.time() + timeout
    while time.time() < end:
        try:
            m = json.loads(q.get(timeout=1))
        except queue.Empty:
            continue
        if pred(m):
            return m
    raise TimeoutError("engine did not reach the expected state")


def run_check(faults):
    eng = Engine(SimSource(parse_faults(faults), seed=1), data_dir=tempfile.mkdtemp())
    eng.start()
    q = eng.subscribe()
    wait_state(q, lambda m: m["t"] == "tick" and m["status"] == "streaming", 10)
    eng.command({"op": "check"})
    m = wait_state(q, lambda m: m["t"] == "state" and m["report"], 90)
    eng.stop()
    eng.join()
    print(open(Path(m["report_dir"]) / "report.txt", encoding="utf-8").read())
    return m["report"]


def main():
    ok = True

    def expect(cond, text):
        nonlocal ok
        ok &= bool(cond)
        print(("ok   " if cond else "FAIL ") + text)

    r = run_check("")
    expect(r["overall"] == "PASS", "healthy band passes overall")
    expect(all(c["verdict"] == "PASS" for c in r["channels"]), "healthy band: all channels PASS")

    r = run_check("dead:3,hum:5,noisy:7,weak:2,drop")
    v = {c["ch"]: c for c in r["channels"]}
    expect(v[3]["verdict"] == "FAIL", "dead channel 3 fails")
    expect(v[2]["verdict"] != "PASS" and v[2]["gain_db"] < 12, "weak channel 2 flagged")
    expect(v[5]["verdict"] != "PASS" and any("hum" in n for n in v[5]["notes"]), "humming channel 5 flagged")
    expect(v[7]["verdict"] != "PASS", "noisy channel 7 flagged")
    expect(all(v[c]["verdict"] == "PASS" for c in (1, 4, 6, 8)), "untouched channels still pass")
    d = {x["name"]: x for x in r["device"]}
    expect(d["Dropped samples"]["verdict"] != "PASS", "sample loss flagged")

    eng = Engine(SimSource(seed=2), data_dir=tempfile.mkdtemp())
    eng.start()
    q = eng.subscribe()
    wait_state(q, lambda m: m["t"] == "tick" and m["status"] == "streaming", 10)
    names = ["rest", "fist", "open", "wrist_in", "wrist_out"]
    eng.command({"op": "train", "gestures": names, "reps": 2, "hold": 2})
    m = wait_state(q, lambda m: m["t"] == "state" and m["model"], 120)
    acc = m["model"]["accuracy"]
    print("held-out accuracy:", acc, "confusion:", m["model"]["confusion"])
    expect(acc > 0.9, "simulated gestures are separated (>90%)")
    for pose in ("fist", "wrist_in", "rest"):
        eng.command({"op": "pose", "label": pose})
        time.sleep(1.5)
        while not q.empty():
            q.get()
        t = wait_state(q, lambda m: m["t"] == "tick" and m["pred"], 5)
        expect(t["pred"]["label"] == pose, f"live prediction follows the hand: {pose} -> {t['pred']['label']}")
    eng.stop()
    eng.join()

    # 4. Wear session, with holds and pauses shortened so it takes ~30 s.
    full_steps = wear.protocol_steps

    def short_steps(step_fn, seed=None):
        steps = full_steps(step_fn, seed)
        for st in steps:
            st["prep"], st["hold"] = 0.3, (4.0 if st["kind"] == "junk" else 1.5)
        return steps

    wear.protocol_steps = short_steps
    root = tempfile.mkdtemp()
    eng = Engine(SimSource(seed=3), data_dir=root)
    eng.start()
    q = eng.subscribe()
    wait_state(q, lambda m: m["t"] == "tick" and m["status"] == "streaming", 10)
    eng.command({"op": "wear", "note": "3"})
    m = wait_state(q, lambda m: m["t"] == "state" and m["model"] and "other" in m["model"]["names"], 120)
    eng.stop()
    eng.join()
    wear.protocol_steps = full_steps
    found = wear.find_wears(root)
    expect(len(found) == 1, "wear session saved")
    w = wear.Wear(found[0])
    expect(len(w.steps) == len(w.segs) == 33 and w.meta["note"] == "3", "wear session loads back with all 33 steps")
    print("wear model accuracy:", m["model"]["accuracy"])
    expect(m["model"]["accuracy"] > 0.8, "wear session trains a usable model")
    r = subprocess.run([sys.executable, str(Path(__file__).resolve().parent.parent / "tools" / "evaluate.py"),
                        "--data", root], capture_output=True, text=True, encoding="utf-8")
    expect(r.returncode == 0 and "within" in r.stdout, "tools/evaluate.py runs on a wear session")

    print("\nALL OK" if ok else "\nSOME CHECKS FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
