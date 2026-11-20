# Roadmap: 5 gestures that work on every wear

The living plan. **Status** and **Progress log** are updated as work happens; the
**Decisions** table records every choice and why, so nothing is re-argued later.
Findings about the band itself still go in [LOGBOOK.md](LOGBOOK.md).

## Goal

Recognise five classes on the MindRove Armband 2:

| Class | Hand |
|---|---|
| `rest` | everything irrelevant: relaxed, typing, holding a phone, moving the arm (a "null" class) |
| `fist` | all fingers closed |
| `open` | palm open, fingers spread |
| `wrist_in` | wrist curled, palm toward the forearm |
| `spiderman` | index, pinky and thumb out; middle and ring folded |

Each class will later trigger an action, so **false triggers matter as much as
accuracy**. It should work every time the band is put on with, at most, a few seconds of
wear-on gesture, not the current ~1 min retrain.

### Done means (targets, our own judgement)

- Accuracy on a wear the model never saw: **≥ 85-90 %** across the 5 classes.
- **≤ 1 false trigger per minute** during everyday junk movement.
- Wear-on cost: **≤ 3 s** (stretch) or **≤ 15 s** quick calibration (fallback).

## Status

| Phase | State |
|---|---|
| 0. Code: new gestures, protocol, wear-on step, evaluator | in progress |
| Checkpoint A: is spiderman separable within one wear? | waiting for 2 wears |
| 1. Data: ~8 wears over 2-3 days | not started |
| Checkpoint B: pick the approach from offline results | not started |
| 2. Live: wear-on alignment, confidence gate, dwell | not started |
| 3. Map gestures to actions | not started |

## Plan

### Phase 0: code (no band needed)
- Gesture set → rest, fist, open, wrist_in, spiderman (instructions + icons).
- Training protocol: each gesture in 3 arm positions (down, forearm level, raised);
  plus a 60-90 s **junk** step (type, phone, scratch, wave, grab a cup) labelled `rest`.
- **Wear-on step**: ~3 s of each of 2 reference gestures. Used to (1) estimate how far
  the ring is rotated, (2) normalise per-channel amplitude (strap tightness, skin).
- Recordings tagged with a **wear id** and the noted rotation of pod 1.
- `tools/evaluate.py`: leave-one-wear-out comparison of
  (a) per-wear LDA (upper reference), (b) pooled LDA, (c) pooled + rotation alignment,
  (d) pooled + circular-shift augmentation, (e) pooled + 15 s quick calibration.
  Reports per-class accuracy, confusion table, false triggers per minute on junk.
- Features: add zero crossings and slope sign changes (Hudgins time-domain set).

### Checkpoint A (after the first 2 wears)
Spiderman ≥ ~80 % within a single wear? **No** → replace it now (pinch / thumbs-up) before
cross-wear work. **Yes** → continue.

### Phase 1: data (needs the user and the band)
~8 wears, ~8 min each, over 2-3 days (day-to-day skin and sweat changes matter, so not
all on one day). Fully remove the band between wears; rotate it on purpose sometimes.
**Tape mark on pod 1**, its position noted each wear = ground truth for rotation.

### Checkpoint B (offline, decides the approach)
- ≥ target with 3 s wear-on → ship that.
- Close → ship 15 s quick calibration (adapt pooled model).
- Far → small 1D CNN on pooled data (CPU first; Kaggle GPU only if training is slow).

### Phase 2: live
Wear-on flow in the app → rotation shift → classify → reject if confidence low → fire
only after the class holds ~150-250 ms. Also works headless (`run_headless.py`).

## Decisions

| Date | Decision | Why |
|---|---|---|
| 2026-11-20 | Judge by leave-one-wear-out + false triggers/min, not within-session accuracy | Within-session hides exactly the problem we are solving |
| 2026-11-20 | `wrist_in`, not `wrist_out` | `wrist_out` shares the extensors with `open` and `spiderman`; open/wrist_out were already confused on 11-17 |
| 2026-11-20 | `rest` trained on varied junk movement + confidence gate + dwell | A plain classifier always picks a class; open-set rejection literature |
| 2026-11-20 | Rotation alignment from a short wear-on gesture before any deep learning | Cheapest method with published success on 7-8 pod rings |
| 2026-11-20 | No Kaggle GPU for now | Data is tiny (8 ch × 100 samples per window); limit is number of wears, not compute |
| 2026-11-20 | Test spiderman first (Checkpoint A) | Finger-level gesture overlapping open and fist; riskiest class |

## Prior work this plan rests on

- Rotation detection + remap, no per-session recalibration after training on 3 wearing
  positions (Myo): [Sensors 2020](https://www.mdpi.com/1424-8220/20/4/1113)
- Two-gesture orientation calibration, 93.4 % over 9 gestures, any orientation, 25 people:
  [Mongardi et al., Sensors 2025](https://pmc.ncbi.nlm.nih.gov/articles/PMC11991082/)
- Circular-shift augmentation for electrode displacement:
  [UNB](https://unbscholar.lib.unb.ca/items/aa0522d7-4672-40cf-8dfe-ba907fdace60)
- Multi-session pretraining + short recalibration:
  [Frontiers 2022](https://www.frontiersin.org/journals/bioengineering-and-biotechnology/articles/10.3389/fbioe.2022.1034672/full),
  [Côté-Allard et al.](https://arxiv.org/abs/1801.07756),
  [Long-term 3DC](https://arxiv.org/pdf/1912.09380v1.pdf)
- Open-set rejection for EMG: [arXiv 2312.02535](https://arxiv.org/abs/2312.02535),
  [PredIN](https://arxiv.org/abs/2407.19753)
- Cross-person, zero-calibration at scale (thousands of people; not our route):
  Kaifosh & Reardon, Nature 2025, doi:10.1038/s41586-025-09255-w

## Progress log

Newest at the bottom. One line per meaningful step; results with numbers.

- 2026-11-20: Plan written. Real recordings from 11-17/11-18 are not on this laptop
  (`data/` holds only simulator output), so cross-wear data starts fresh.
