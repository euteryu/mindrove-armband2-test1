# MindRove Lab

Check that a MindRove Armband 2 works properly, watch its signals, and teach it gestures.
Built on MindRove's official Python SDK. Background findings are in
[docs/LOGBOOK.md](docs/LOGBOOK.md).

**Testing with the real band? Follow [docs/TESTING.md](docs/TESTING.md)** step by step.

## Run it

```
.venv\Scripts\python app.py          real armband
.venv\Scripts\python app.py --sim    no hardware: a simulated band, to learn the app
```

A page opens in your browser at http://localhost:8765. It works without internet.

Before using the real band:

1. Charge it, switch it on, wear it snug on the thickest part of the forearm on slightly
   damp skin.
2. Connect this computer's Wi-Fi to the armband's network.
3. Close MindRove Connect: only one program can use the band at a time.

Fresh install on another Windows machine: double-click `setup.bat` once (needs Python and
internet), then `run.bat`. By hand: `python -m venv .venv`, then
`.venv\Scripts\pip install -r requirements.txt` (on Linux use `.venv/bin/...`).

## The three screens

- **Live signal**: the 8 channels, filtered, plus a ring showing which pods are active.
  Relaxed should look flat; squeezing should give clear bursts.
- **Device check**: a 45-second guided test (relax, fist, wrist back, wrist in, twist).
  Each channel gets PASS / CHECK / FAIL with the reason. The report and raw recording
  are saved under `data/checks/`.

- **Gestures**: pick gestures, hold each one when prompted, and it trains a model, shows
  how well it tells them apart, then recognises them live. Saved under `data/models/`.

**Recording** (panel above the tabs, works on every screen): saves every sample to
`data/sessions/<date_time>/signals.csv` as it arrives: raw EMG (8 channels, unfiltered),
accelerometer, gyroscope, the band's packet counter, the **activity** label you click,
what the app was prompting (during a check or training) and what the recogniser guessed.
Notes you type go to `markers.csv`; `meta.json` describes every column. Roughly 0.5 GB per
hour of CSV.

## How it is put together

```
emg/source.py     talks to the band (official SDK), or simulates one
emg/dsp.py        filters and features
emg/health.py     device-check verdicts
emg/gestures.py   the classifier
emg/recorder.py   continuous session recording to CSV
emg/engine.py     background loop tying it together; no UI code
app.py            small web server + web/index.html (the UI)
run_headless.py   recognition with no screen: the shape of the on-board wearable
tests/smoke.py    end-to-end test on the simulator (about 2 minutes)
```

The simulator (`--sim`) is our own synthetic signal generator in `emg/source.py`, not a
MindRove product. It only proves the software works; it says nothing about the real band.
Anything recorded or trained with `--sim` is kept apart in `data/sim/`.

Everything in `emg/` is independent of the UI, so the same code runs on a Linux
single-board computer. See the logbook for what is known about that.

Options: `--mains 60` outside 50 Hz countries, `--sim-faults dead:3,hum:5,noisy:7,weak:2,drop`
to see how faults show up, `--host 0.0.0.0 --no-browser` to serve the page to other
devices from a headless board.
