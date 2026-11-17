# MindRove Armband 2: project logbook

Findings about the device, the SDK and prior work, kept for future developers.
Newest entries go at the bottom. Every finding is tagged with how sure we are:

- **[verified]** checked first-hand on this machine, with the method stated
- **[read]** read in official source code or examples, not yet run against the band
- **[carried over]** from earlier research chats, not re-checked here; treat as leads
- **[assumed]** a working assumption the code relies on; confirm on the real band

## Project goal

1. **Now:** prove the Armband 2 works properly (all 8 electrodes, link, motion sensor)
   with a clear desktop visualisation.
2. **Next:** gesture recognition with a simple UI.
3. **End goal:** a self-contained wearable. A single-board computer (Raspberry Pi,
   Rock Pi or similar) does all the processing on board, with no PC and no internet.

---

## 2026-11-16: SDK inspection and first build

Status at the end of this entry: the software is built and tested against a simulator.
**It has not yet been run against the real armband.** The band has so far only been
seen working in MindRove's own Windows app.

### 1. The SDK

| Finding | Status |
|---|---|
| `pip install mindrove` gives version 5.3.0. It imports and opens a session on Windows 11, Python 3.13, numpy 2.5.5, scipy 1.18.1. | [verified] |
| No separate driver. The package bundles the native libraries in `site-packages/mindrove/lib/`. | [verified] |
| The API is a fork of BrainFlow: `BoardShim`, `MindRoveInputParams`, `BoardIds`, `DataFilter`. BrainFlow documentation mostly applies. | [read] |
| Official repo is `github.com/MindRove/MindRoveSDK` (no underscore). Python examples: `examples/python/boardconfig/boardconfig.py` and `examples/python/plot_real_time/*.py`. | [verified] by listing the repo |
| MindRove's own gesture project is `github.com/MindRove/NaviFlame`. | [verified] it exists; contents not reviewed |

### 2. ARM single-board computers are supported by the pip package

This overturns the earlier belief that a Raspberry Pi would need a special build.

- `mindrove/lib/` contains `aarch64/` and `arm32/` folders, each with
  `libBoardController.so`, `libDataHandler.so`, `libMLModule.so`, `libMindRoveWrapper.so`. **[verified]**
- `aarch64/libBoardController.so` is a genuine `ELF 64-bit LSB shared object, ARM aarch64`
  (checked with `file`). **[verified]**
- `board_shim.py` picks the folder from `platform.machine()` on Linux: `aarch64` for
  64-bit ARM, `arm32` for 32-bit ARM, otherwise the x64 `.so`. **[read]**
- **Not yet run on an ARM board.** Possible snags: the board's glibc being older than the
  library needs, and `platform.machine()` returning an unexpected string. Test with
  `python -c "from mindrove.board_shim import BoardShim"` on the board first.
- A community repo named `mj-sam/Mindrove_rasbery_pi` exists, which suggests others have
  used the band from a Pi. Not reviewed. **[verified]** it exists

### 3. How the band talks to the computer

- The band is its own Wi-Fi access point. The computer joins that network, and so has
  **no internet while connected**. Anything used alongside the band must work offline. **[verified]** by the user's setup
- The SDK logs `Target address is set to : 192.168.4.1::4210`. **[verified]** from SDK log output
- With no band reachable, `prepare_session()` and `start_stream()` still succeed and
  return instantly. No samples arrive, and about 3 s later the SDK logs
  `Network problem, with socket error 10060` and releases the board by itself. So
  "session opened" does not mean "band connected": judge by whether samples arrive, and
  reopen the session to retry. **[verified]** on Windows with no band
- Only one program can use the band at a time (close MindRove Connect first). **[carried over]**
- On Windows, the firewall may block Python from receiving the data. **[carried over]** from MindRove's troubleshooting page

### 4. Data layout for the Wi-Fi armband

From `BoardShim.get_board_descr(BoardIds.MINDROVE_WIFI_BOARD)` (board id `0`). **[verified]**

| Row(s) | Content |
|---|---|
| 0-7 | EMG channels (also reported as `eeg_channels` and `exg_channels`) |
| 8-17 | "resistance" channels, 10 values (impedance mode) |
| 18 | battery |
| 19, 29 | "other" channels; the official example reads row 19 as the trigger (beep/boop) |
| 20-22 | accelerometer |
| 23-25 | gyroscope |
| 26 | packet counter |
| 27 | timestamp |
| 28 | marker |
| 30-31, 32-34 | PPG and raw PPG (not present on the armband as far as we know) |
| 35-37 | magnetometer |
| 38 | EDA |

Sampling rate 500 Hz, 39 rows. `get_board_data()` returns `(rows, samples)` and empties
the buffer; `get_current_board_data(n)` peeks without emptying.

Other board ids: `SYNTHETIC_BOARD = -1` (BrainFlow's generic fake board: 250 Hz, 16
channels, different row layout, so not a stand-in for the armband),
`MINDROVE_SYNCBOX_BOARD = 1`, `PLAYBACK_FILE_BOARD = -3`, `STREAMING_BOARD = -2`.

### 5. Built-in device modes useful for fault-finding

`MindroveConfigMode` in `board_shim.py`, sent with `board.config_board(...)`. **[read]**

| Mode | Bytes | Meaning |
|---|---|---|
| `EEG_MODE` | `00 00 00 00 00` | normal measurement |
| `IMP_MODE` | `04 00 00 00 00` | impedance (electrode contact) measurement |
| `TEST_MODE` | `10 00 00 00 00` | internal test signal |
| `BEEP` / `BOOP` | `01…` / `02…` | sync triggers, echoed back on the trigger row |

The official `boardconfig.py` switches `EEG_MODE` → `IMP_MODE` → back to `EEG_MODE` then
`TEST_MODE`, sleeping ~2 s after a switch. That example targets the SyncBox board;
**whether the Armband 2 honours impedance and test modes is unconfirmed.** Both are
exposed in our app as "experimental" for that reason. If the test signal works, it
separates electronics faults from skin-contact problems, which is exactly what a
"is my band broken?" check needs.

### 6. Open questions to settle on the first real-band run

| Question | Why it matters | How to settle it |
|---|---|---|
| Are EMG values in microvolts? | Absolute numbers in the UI are labelled µV. Verdicts use ratios, so they hold either way. **[assumed]** µV, as in BrainFlow | Rest should read a few µV, a hard fist tens to hundreds |
| How does the packet counter step, and does it wrap? | Used to count dropped samples. The code learns the step from the stream and ignores wrap-around | Compare "Dropped" in the UI with the sample rate |
| What unit is the battery row? | Shown raw, not judged. An old manual gives volts: 3.7-4.25 full, under 3.3 nearly empty **[carried over]** | Read it after a full charge |
| Order and units of the 10 resistance values | Shown raw as "Value 1-10" | Lift one pod off the skin in impedance mode |
| Which pod is which channel? | Needed to interpret per-channel faults | Press each pod in the Live view |
| Do the ARM libraries load on the chosen board? | End goal | See section 2 |

### 7. Signal processing choices (and why)

- Band-pass 20-200 Hz, 4th-order Butterworth. Below 20 Hz is mostly motion artefact;
  the 500 Hz rate caps usable content at 250 Hz.
- Notch at mains and its harmonics (50/100/150 Hz for UK/EU, `--mains 60` for US).
- Filters run sample-stream style with carried state, initialised to the first sample so
  the electrode DC offset does not ring at start-up.
- Gesture features: per channel log-RMS and log waveform length over 200 ms windows
  every 50 ms. Classifier: regularised LDA in plain numpy. Scored by leaving one whole
  recording round out, so the number reflects unseen data.
- Health thresholds are our own engineering judgement, not MindRove's or any paper's:
  response under 6 dB above rest fails, 6-12 dB warns; rest noise over 3x the other
  channels' median and over 10 µV warns; mains over half of rest power warns; a flat
  channel fails. Expect to tune these after the first real recordings.

### 8. Prior work using this band  **[carried over, not re-verified]**

From an earlier research chat. Titles are as given there; check before citing.

- Papers reported to use the MindRove armband: SRM cross-day gesture recognition (uses
  the Python SDK); a systematic evaluation of sEMG pipelines (10 subjects, 8 ch, 500 Hz);
  a novel sEMG dataset for hand movement classification; finger-motion decoding with
  Riemannian features (EMG-FK dataset, 20 participants); MotorSense video-EMG dataset;
  a multimodal EMG + Leap Motion benchmark; Kollod et al. 2022; Oña, Bandini & Jardón
  2024 (DOI 10.1007/978-3-031-77584-0_77), which found the bracelet noisier than a
  conventional electrode system; an iScience review of EMG armbands.
- Papers that name a model reportedly use `ARB.210901`; whether that is the "Armband 2"
  is unknown.
- Takeaways reported there: everyone records 8 channels at 500 Hz over Wi-Fi; mains hum
  is normal without a notch; some noise is normal for dry electrodes; fit matters a lot
  and loose bands give unusable data; 5-7 gestures is the realistic range for an
  8-channel band.
- One public bug report (SDK GitHub issue #17): signal gaps on Ubuntu, attributed by
  MindRove to Wi-Fi packet loss or low battery.
- Community code seen in a GitHub search today (names only, not reviewed):
  `mj-sam/Mindrove_rasbery_pi`, `m00nwtchr/mindrove-rs`,
  `roboticslab-uc3m/mindrove-ros2-driver`, `gkouretas/ros2_mindrove`,
  `xukristenyan/mindrove-toolbox`, `roboticslab-uc3m/mindrove-gesture-recognition`.

### 9. Notes for the single-board-computer stage

- Dependencies are only `mindrove`, `numpy`, `scipy`. No GUI toolkit, no scikit-learn.
- `emg/` has no UI code. `run_headless.py` runs recognition with no screen or browser.
- The board's Wi-Fi will be taken by the armband's network. To view the web UI from
  another device, the board needs a second interface (Ethernet, USB gadget mode or a
  second Wi-Fi adapter), then `python app.py --host 0.0.0.0 --no-browser`. The page has
  no login, so only do this on a network you trust.
- Models are trained per wearing session. On a headless wearable, calibration needs a
  prompt channel that is not a browser (LED, buzzer, button); not designed yet.

### 10. The simulator is ours, and what has actually been tested

- `--sim` uses `SimSource` in `emg/source.py`: random noise shaped per channel and per
  pose, plus fake mains hum, DC offset and optional planted faults. **We wrote it.
  MindRove did not release it**, and it is not based on recordings from a real band.
  (The SDK's own `SYNTHETIC_BOARD` is BrainFlow's generic fake board, see section 4,
  and is not used.)
- What the simulator proves: the app runs end to end, the device check catches planted
  faults on the right channels, and training/recognition works mechanically.
  `tests/smoke.py` passes (13 of 13 checks, re-run 2026-11-16). **[verified]**
- What it does not prove: anything about the real band. The 100% gesture accuracy on the
  simulator is meaningless for real muscle signals, which overlap far more.
- Real-band mode with no band reachable was run for 20 s: the app stays up, reports
  "No data from armband", shows a checklist and keeps retrying. **[verified]**
- Simulator output goes to `data/sim/`, real-band output to `data/`, so a model trained
  on the simulator is never loaded for the real band.
- **Still not done: any run against the real armband.** Section 6 lists what to look at
  on that first run.
