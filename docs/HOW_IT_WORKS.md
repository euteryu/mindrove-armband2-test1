# How MindRove Lab works

A walk through the whole system, from the armband to the screen. Written to be read top
to bottom by someone new to the project. For *what we found* on the real band, see
[LOGBOOK.md](LOGBOOK.md); for *how to test*, see [TESTING.md](TESTING.md).

Everything here is our own code on top of MindRove's official Python SDK (`mindrove`
on pip). No pretrained models, no cloud, no internet needed at run time.

---

## 1. The big picture

```
 Armband 2 ──Wi-Fi──▶ MindRove SDK ──▶ emg/source.py ──▶ emg/engine.py ──▶ app.py ──▶ browser
 (8 EMG + IMU,         (BrainFlow     (gets new samples) (filters, checks,  (tiny web   (web/index.html:
  500 Hz)               fork)                              gestures, record)  server)     draws it all)
                                                                │
                                                                ├──▶ emg/recorder.py  → data/sessions/
                                                                ├──▶ emg/health.py    → data/checks/
                                                                └──▶ emg/gestures.py  → data/models/
```

- **One background thread** (`Engine`) owns the band. Every 50 ms it pulls whatever
  samples have arrived, processes them and publishes one JSON message.
- The **browser page** listens to those messages (Server-Sent Events on `/events`) and
  sends commands back (`POST /api/cmd`), e.g. "start device check".
- `emg/` has **no UI code at all**, so the same engine runs headless on a Raspberry
  Pi-type board (`run_headless.py`). That is the path to the wearable end goal.

---

## 2. Connecting to the band

- The band is its **own Wi-Fi access point** (`MindRove_...`, password `#mindrove`). The
  laptop joins it; the SDK talks to `192.168.4.1` port `4210`.
- `MindRoveSource.start()` opens a session with board id `MINDROVE_WIFI_BOARD`. The SDK
  returns success **even when no band is there**, so the engine judges the link only by
  whether samples actually arrive:
  - no samples for 1 s → status **"No data from armband"** (the banner checklist appears)
  - no samples for 4 s → the SDK has given up its socket by then, so the engine closes
    and reopens the session. This repeats until data arrives; nothing to click.
- Only one program can hold the band, so MindRove Connect must be closed.

### What one sample contains
Rows from the SDK's board description: 8 EMG channels, 3 accelerometer, 3 gyroscope, a
packet counter, battery, and 10 impedance ("resistance") values. Full table in the
logbook, section 4.

### Link quality (top bar)
- **Rate**: samples received per second over the last 3 s. Should be ~500 Hz.
- **Dropped**: from the band's own **packet counter**. The engine learns the counter's
  normal step, and any bigger jump is counted as lost samples. Loss points at Wi-Fi or
  battery, not electrodes.

---

## 3. Filtering (`emg/dsp.py`)

Raw EMG from dry electrodes is a large DC offset (tens of mV) plus mains hum plus the
small muscle signal you want. The `StreamFilter` cleans it:

| Stage | Setting | Why |
|---|---|---|
| Band-pass | 20-200 Hz, 4th-order Butterworth | Surface EMG lives here; below 20 Hz is mostly movement artefact and electrode drift |
| Notches | 50, 100, 150 Hz (or 60/120/180 with `--mains 60`) | Mains hum and its harmonics |

It filters **chunk by chunk with the filter state carried over**, so there are no
glitches where chunks meet, and it starts from the first sample's value so the DC offset
does not "ring" at start-up. The filtered signal drives the live view, the device check
and gestures. Recordings store the **raw** signal so any filter can be applied later.

---

## 4. The Live signal screen

- **Traces**: the last 5 s of filtered EMG, one row per channel. Auto scale follows the
  current peak amplitude smoothly.
- **Ring**: brightness = RMS (signal strength) of each channel over the last 200 ms. RMS
  is the square root of the mean of the squared signal: a single number for "how hard is
  the muscle under this pod firing right now".
- **Motion sensor**: latest accelerometer and gyroscope readings.
- **Mode menu**: normal EMG, plus two experimental modes the SDK offers (impedance,
  internal test signal) that may not be supported by the Armband 2.

---

## 5. Device check (`emg/health.py`)

A guided recording, then verdicts per channel. Steps: **rest 6 s, fist 5 s, wrist back
5 s, wrist in 5 s, twist forearm 5 s**, each with 3 s "get ready" first (~45 s total).
The first 0.8 s of each hold (your reaction time) and last 0.2 s are thrown away.

### How the numbers are measured
- **Signal level** of a step = the **median of 200 ms window RMS values**. A median
  means one twitch or bump cannot dominate the result.
- **Rest baseline uses only the still part of the rest step.** The gyroscope shows when
  the arm moved; those parts are left out. This was added after the first real run,
  where moving during "rest" made 7 of 8 channels falsely FAIL (logbook section 11).
  If less than 2 s was still, the "Still at rest" row fails and asks for a rerun.
- **Response (dB)** = how much stronger the channel is during its best effort step than
  at rest: `20 × log10(effort / rest)`. +6 dB is 2x, +12 dB is 4x, +20 dB is 10x.

### Verdict rules (our own engineering judgement, not MindRove's spec)

| Check | Result |
|---|---|
| Channel flat or stuck on one value | FAIL |
| Response under 6 dB | FAIL |
| Response 6-12 dB | CHECK (WARN) |
| Rest noise over 3x the other channels' median and over 10 µV | CHECK: usually poor skin contact |
| 50 Hz hum over 5x the other channels' median and over 50 µV | CHECK: usually poor skin contact |
| Sample rate within 2% of 500 Hz (8% for CHECK) | PASS |
| Dropped samples under 0.5% (3% for CHECK) | PASS |
| Accelerometer / gyroscope move 3x more during twist than at rest | PASS |

**Telling a broken pod from bad contact:** rotate the band by one pod and rerun. A fault
that follows the *channel number* is the hardware; a fault that stays at the *same spot
on your arm* is skin contact. (This is how channel 7's failure on 2026-11-17 was shown to
be contact, logbook section 12.)

Saved to `data/checks/<date_time>/`: `report.txt`, `report.json`, `recording.npz` (raw and
filtered signal per step).

---

## 6. Gesture recognition (`emg/gestures.py`, `emg/dsp.py`)

**Classical signal processing plus a simple statistical classifier.** No neural network,
no pretrained weights: every model is trained from scratch on your own data, in
milliseconds.

### The pipeline
1. **Filter** as in section 3.
2. **Cut into windows** of 200 ms, a new one every 50 ms (windows overlap).
3. **Features**: each window becomes **16 numbers**, two per channel:
   - **RMS**: how hard the muscle under that pod is firing.
   - **Waveform length** (mean absolute sample-to-sample change): how "busy" the signal
     is, a cheap stand-in for frequency content.
   - Both are log-scaled, which makes them roughly bell-shaped, the assumption LDA makes.
4. **Classifier: LDA** (linear discriminant analysis). It learns one average 16-number
   pattern per gesture, plus one shared measure of how much those numbers naturally
   wobble (a covariance matrix). A new window is assigned to the gesture whose pattern it
   is closest to, allowing for that wobble. Training is one matrix inversion.
   - **Shrinkage**: the wobble estimate is blended 90/10 with a plain average, which keeps
     the model stable when data is limited (`gestures.py`, line 20).
5. **Live smoothing**: every 50 ms the latest 200 ms is classified, and probabilities are
   blended with the previous ones (60% old, 40% new) so the display does not flicker.

### Why only 3 rounds is enough
- Each 4 s hold, after trimming reaction time, leaves 3 s = 1500 samples, which gives
  **~57 overlapping windows**. Three rounds = **~170 examples per gesture**.
- LDA has very few parameters (5 x 16 averages plus one shared 16 x 16 matrix), so it
  needs far less data than a neural network.
- This is the standard baseline in armband-EMG research.

### How the accuracy is measured honestly
**Leave one round out**: train on rounds 1-2, test on round 3; then each other
combination. The model is always graded on a round it never saw. The **confusion table**
shows, for each gesture you made (row), what it was recognised as (columns).

### Real results so far (from the logbook)
| Session | Accuracy (5 gestures, chance = 20%) | Mixed up |
|---|---|---|
| 2026-11-17 | 84% | open vs wrist out (both use the forearm extensors) |
| 2026-11-18 | 72% | rest vs wrist in |

The simulator's 100% means nothing; real muscle signals overlap far more.

### Limits to know about
- **Per wearing session.** Re-seating the band moves pods over different muscles:
  retrain each time you put it on.
- **Static postures only** (held fist, held pinch), not movements like a wave.
- **Arm position and fatigue matter.** Trained with the arm resting, it flickers when the
  arm moves (seen on 2026-11-17). Training in several positions helps.
- **5-7 gestures** is the realistic ceiling for 8 dry channels.

### If accuracy needs to go up, in order of effort
1. Train in more arm positions and over more rounds.
2. More features (zero crossings, slope sign changes, spectral bands).
3. Combine data from several sessions.
4. A small neural network. MindRove's own **NaviFlame** does this (pretrained feature
   extractor + per-user network, TensorFlow, Python 3.10). See logbook section 12 and
   the project report.

Saved to `data/models/latest.npz` (loaded on next start) plus a timestamped copy. The file
stores the training windows themselves, so the model is re-fitted when loaded.

---

## 6b. Wear sessions and cross-wear evaluation (`emg/wear.py`, `tools/evaluate.py`)

The goal is gestures that work every time the band goes on, not only right after a
retrain ([ROADMAP.md](ROADMAP.md)). The unit of data is a **wear session**: one fixed
~4.5 min recording per time you put the band on (Gestures tab → Wear session).

- **Wear-on reference**: 3 s wrist in, 3 s open. Their pattern of which pods fire is
  compared with earlier wears at all 8 rotations of the ring; the best match says how far
  the band is turned. Their strength per pod is used to even out skin contact.
- **Classes**: rest, fist, open, wrist in, Spider-Man, each held 4 s, in 3 arm positions
  × 2 rounds (order shuffled). Each round is a "group" for testing.
- **Junk**: 60 s of everyday movement, stored as the internal class `other`. It teaches
  the model what must *not* trigger anything; `other` counts as rest.
- **Decider** (`emg/decide.py`): only fires a gesture when its smoothed probability is
  ≥ 0.7 for 4 windows in a row (200 ms).
- The app trains a model on the new wear immediately (same LDA as section 6).
- `tools/evaluate.py` tests on a wear the model never saw, trained on all the others,
  with and without rotation alignment, strength normalisation, rotation augmentation and
  a 30 s quick calibration. It reports window accuracy, hold accuracy (decider fired the
  right gesture and nothing else) and false triggers per minute of junk.
- Saved to `data/wears/<date_time>/` (`wear.npz`: raw + filtered signal per step;
  `meta.json`: steps, your pod note). Simulated wears: `tools/sim_wears.py`.

## 7. Session recording (`emg/recorder.py`)

The Recording panel above the tabs saves **every sample** as it arrives, on any screen.

`data/sessions/<date_time>/`:
- `signals.csv`: one row per sample with the **raw** EMG (8 channels, DC offset
  included), accelerometer, gyroscope, the band's packet counter, the **activity** label
  you click (your ground truth), what the app was prompting during a check or training,
  and what the recogniser guessed.
- `markers.csv`: notes you type, tied to a sample number.
- `meta.json`: sample rate, start/stop time, the app's filter settings and the meaning of
  every column.

About 0.5 GB per hour. The file is flushed to disk every second, so a crash loses at most
about a second of data.

---

## 8. The simulator (`--sim`)

`SimSource` in `emg/source.py` is **our own fake band**: shaped random noise per channel
and pose, fake mains hum and DC offset, and optional planted faults
(`--sim-faults dead:3,hum:5,noisy:7,weak:2,drop`). It proves the software works end to
end (`tests/smoke.py`), and says nothing about the real band. Simulator output goes to
`data/sim/` so it is never mixed with real results.

---

## 9. Where to change things

| You want to... | Look at |
|---|---|
| Change filter band or notches | `emg/dsp.py`: `BAND`, `StreamFilter` |
| Change window size / features | `emg/dsp.py`: `WIN`, `HOP`, `features()` |
| Change pass/fail thresholds | `emg/health.py`: `analyze()` |
| Change device-check steps or timings | `emg/engine.py`: `CHECK_STEPS`, `TRIM_START`, `TRIM_END` |
| Add a gesture with its own picture/instruction | `emg/engine.py`: `STEP_INFO` |
| Swap the classifier | `emg/gestures.py`: keep the `GestureModel` interface |
| Change what is recorded | `emg/recorder.py`: `COLUMNS` |
| Change the screens | `web/index.html` (plain HTML/JS, no build step) |
| Run without a screen | `run_headless.py` |
