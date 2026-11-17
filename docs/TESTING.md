# First real-armband test

About 20 minutes. Do the parts in order and fill in the **record sheet** at the bottom
as you go. Each part has a clear **PASS** line: if you see that, move on. If not, follow
"If it fails" and write down what you saw. Nothing you do here can damage the band.

You need: the laptop (on Ethernet for internet), the Armband 2 (charged), a little water.

---

## Part 0. One-time setup on the laptop (5 min, needs internet)

1. Install **Python 3.10 or newer** from python.org. On the first installer screen tick
   **"Add python.exe to PATH"**. Install **Git** too if the laptop does not have it.
2. Open a terminal (Start, type `cmd`, Enter) and run:
   ```
   git clone https://github.com/euteryu/mindrove-armband2-test1.git
   cd mindrove-armband2-test1
   setup.bat
   ```
3. **PASS:** the window ends with `Setup OK. Now run run.bat`.

Already cloned before? Run `git pull` inside the folder instead, to get the latest version.

---

## Part A. Connect (3 min)

1. Make sure **MindRove Connect is closed** (not in the taskbar, not in the tray).
   Only one program can use the band at a time.
2. Switch the band on. Wet your forearm lightly, put the band on the thickest part of
   the forearm, snug but comfortable. Wait one minute for the electrodes to settle.
3. Click the Wi-Fi icon and join the network named `MindRove_...` (password `#mindrove`).
   **Keep the Ethernet cable plugged in.**
4. Double-click **`run.bat`** in the project folder. A black window opens, then a browser
   page titled **MindRove Lab**.
5. If Windows Firewall asks about Python: **tick both Private and Public, then Allow.**
6. Wait up to 20 seconds and look at the top bar.

**PASS:** the dot is green and says **Receiving data**, **Rate** is about **500 Hz**,
and **Dropped** is under **1 %**.

If it fails:
- Stuck on "No data from armband" after 30 s: close the browser tab and the black window,
  open Windows Firewall > "Allow an app through firewall", make sure every **Python**
  entry has both Private and Public ticked, then run `run.bat` again.
- Still stuck: check MindRove Connect works on this laptop (then close it again).
  If Connect works and ours does not, stop here and send the record sheet plus a
  screenshot of the black window.
- Red "Problem talking to the armband": copy that message and the black window text.

---

## Part B. Live signal tab (5 min)

Stay on **Live signal**. Leave **Scale** on Auto and **Mode** on "Muscle signal (normal)".
Rest your forearm on the table.

| # | Do this | PASS if you see |
|---|---|---|
| B1 | Relax your hand completely for 5 s | Traces mostly flat. Note the numbers inside the ring (µV) |
| B2 | Make a hard fist for 3 s, then relax | Clear bursts on most channels, ring pods light up, then calm again |
| B3 | Bend wrist back, then curl it in | Different channels light up for each direction |
| B4 | Press one pod firmly with a finger of the other hand, one pod at a time | One ring number lights up per pod. Write the mapping on the sheet |
| B5 | Tilt and turn your arm | Accelerometer and Gyroscope numbers change |

If B1 shows one channel much busier than the rest: wet that spot and press the band
against the skin. If it stays busy, note the channel number.

---

## Part C. Device check (2 min)

1. Click the **Device check** tab, then **Start device check**.
2. Follow the big prompts. **GET READY** (orange) means get into position, **HOLD IT**
   (green) means hold until the countdown ends. Keep the arm supported. It takes 45 s:
   relax, fist, wrist back, wrist in, twist forearm.
3. A **Result** card appears with one box per channel.
4. **Take a screenshot of the whole result** (Win + Shift + S).

**PASS:** it finishes and shows a result. Any mix of PASS / CHECK / FAIL is still a
successful test run. The thresholds are first guesses that we tune from your results.

If a channel says FAIL but it clearly showed bursts in B2, tell us: that means the
threshold is wrong, not the band.

---

## Part D. Gestures (optional, 3 min)

1. Click the **Gestures** tab. Leave the 5 default gestures, 3 rounds, 4 s hold.
2. Click **Record and train** and follow the prompts (about 90 s).
3. **PASS:** an accuracy % and a coloured table appear. Then make each gesture and see
   whether the big emoji follows you.
4. Screenshot the accuracy and table.

---

## Part E. Send the results

1. Fill in the sheet below and send it with the screenshots.
2. Optional but very useful: zip the `data` folder in the project and send it. It holds the
   raw recordings we use to tune the thresholds.
3. To stop the app, close the black window.

**Don't try yet:** the Impedance and Test signal modes in the Mode menu. They are
experimental and may not work on the Armband 2. If you do try one and it errors, the app
reconnects on its own after a few seconds.

---

## Record sheet

```
Date / time:
Laptop:                         Windows version:
Band battery before test (MindRove Connect or LED):

A  Connected?  yes / no      Seconds until green:
   Rate:     Hz     Dropped:     %     Battery shown:
   Firewall prompt appeared?  yes / no
   Problems / messages:

B1 Ring numbers at rest (µV):  1:   2:   3:   4:   5:   6:   7:   8:
B2 Fist gave clear bursts?  yes / no   Channels that did not react:
B3 Wrist back strongest channels:        Wrist in strongest channels:
B4 Pod mapping (start at the pod by the logo/LED, go clockwise looking at your wrist):
   pod 1 -> ch    pod 2 -> ch    pod 3 -> ch    pod 4 -> ch
   pod 5 -> ch    pod 6 -> ch    pod 7 -> ch    pod 8 -> ch
B5 IMU numbers changed?  yes / no

C  Overall result:  PASS / CHECK / FAIL    Screenshot taken?  yes / no
   Channels flagged and what it said:

D  Accuracy:    %    Gestures that got mixed up:

Anything confusing in the app (wording, buttons, what to do next):
```
