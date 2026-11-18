"""Builds the MindRove project report PDF."""
import sys
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

OUT = sys.argv[1]
F = "C:/Windows/Fonts/"
pdfmetrics.registerFont(TTFont("Body", F + "arial.ttf"))
pdfmetrics.registerFont(TTFont("Body-B", F + "arialbd.ttf"))
pdfmetrics.registerFont(TTFont("Body-I", F + "ariali.ttf"))
pdfmetrics.registerFont(TTFont("Body-BI", F + "arialbi.ttf"))
pdfmetrics.registerFontFamily("Body", normal="Body", bold="Body-B", italic="Body-I", boldItalic="Body-BI")

INK = colors.HexColor("#1f2933")
DIM = colors.HexColor("#5f6b7a")
ACC = colors.HexColor("#0b6fb8")
LINE = colors.HexColor("#d5dbe3")
PALE = colors.HexColor("#f2f5f9")
OK = colors.HexColor("#e3f3ea")
WARN = colors.HexColor("#fdf3dc")
BAD = colors.HexColor("#fbe6e6")

S = {
    "title": ParagraphStyle("title", fontName="Body-B", fontSize=26, leading=31, textColor=INK, spaceAfter=6),
    "sub": ParagraphStyle("sub", fontName="Body", fontSize=13, leading=18, textColor=DIM, spaceAfter=18),
    "h1": ParagraphStyle("h1", fontName="Body-B", fontSize=17, leading=22, textColor=ACC, spaceBefore=4, spaceAfter=8),
    "h2": ParagraphStyle("h2", fontName="Body-B", fontSize=12.5, leading=16, textColor=INK, spaceBefore=10, spaceAfter=4),
    "p": ParagraphStyle("p", fontName="Body", fontSize=10, leading=14.2, textColor=INK, spaceAfter=6, alignment=TA_LEFT),
    "small": ParagraphStyle("small", fontName="Body", fontSize=8.6, leading=11.5, textColor=DIM, spaceAfter=4),
    "cell": ParagraphStyle("cell", fontName="Body", fontSize=8.8, leading=11.6, textColor=INK),
    "cellb": ParagraphStyle("cellb", fontName="Body-B", fontSize=8.8, leading=11.6, textColor=INK),
    "box": ParagraphStyle("box", fontName="Body", fontSize=10, leading=14.2, textColor=INK),
    "bul": ParagraphStyle("bul", fontName="Body", fontSize=10, leading=14, textColor=INK, leftIndent=14,
                          bulletIndent=3, spaceAfter=3),
}

story = []
P = lambda t, s="p": story.append(Paragraph(t, S[s]))
H1 = lambda t: story.append(Paragraph(t, S["h1"]))
H2 = lambda t: story.append(Paragraph(t, S["h2"]))


def bullets(items):
    for it in items:
        story.append(Paragraph(it, S["bul"], bulletText="•"))
    story.append(Spacer(1, 4))


def numbered(items):
    for i, it in enumerate(items, 1):
        story.append(Paragraph(it, S["bul"], bulletText=f"{i}."))
    story.append(Spacer(1, 4))


def box(text, bg=PALE):
    t = Table([[Paragraph(text, S["box"])]], colWidths=[170 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), bg), ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                           ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                           ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    story.append(t)
    story.append(Spacer(1, 8))


def table(rows, widths, shade=None, header=True):
    data = [[Paragraph(str(c), S["cellb"] if (header and r == 0) else S["cell"]) for c in row]
            for r, row in enumerate(rows)]
    t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1 if header else 0)
    st = [("GRID", (0, 0), (-1, -1), 0.5, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
          ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]
    if header:
        st.append(("BACKGROUND", (0, 0), (-1, 0), PALE))
    for (c, r, bg) in (shade or []):
        st.append(("BACKGROUND", (c, r), (c, r), bg))
    t.setStyle(TableStyle(st))
    story.append(t)
    story.append(Spacer(1, 8))


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Body", 8)
    canvas.setFillColor(DIM)
    canvas.drawString(20 * mm, 12 * mm, "MindRove Armband 2 project report · 18 November 2026")
    canvas.drawRightString(190 * mm, 12 * mm, f"Page {doc.page}")
    canvas.restoreState()


# ---------------------------------------------------------------- cover + summary
story.append(Spacer(1, 30 * mm))
P("MindRove Armband 2", "title")
P("Is the device sound, what the tests showed, and how to reach reliable gesture-to-action control", "sub")
P("Prepared for Minseok Ryu · 18 November 2026 · based on recordings made on 17–18 November 2026 with "
  "the MindRove Lab app (our own) and MindRove’s NaviFlame", "small")
story.append(Spacer(1, 10 * mm))
H2("The short version")
table([
    ["Question", "Answer"],
    ["Is the band faulty? Return it?", "<b>No, keep it.</b> All 8 channels, the link and the motion sensors work. "
     "The one channel that failed on day 1 recovered after reseating, so it was skin contact."],
    ["Is my goal realistic?", "<b>Yes.</b> Fist / spiderman / everything-else is a well-sized goal. Fist will be "
     "the easiest; spiderman is a finger gesture and needs firmer, deliberate holding."],
    ["What actually limits accuracy?", "Not the model. The signal changes between training and use: strap "
     "slip, electrode settling, arm position and effort level. Within a single take, gestures were 99% separable."],
    ["Does arm position matter?", "<b>Yes</b>, a well-documented effect (error 3.8% to 18% in Fougner et al., 2011). "
     "Train in every position you will use, or gate on the accelerometer."],
    ["Was NaviFlame’s 98% real?", "No. Its validation mixes overlapping slices of the same take. An honest split of "
     "your own NaviFlame data gave 84%."],
], [45, 125])
story.append(PageBreak())

# ---------------------------------------------------------------- goal
H1("1. The goal")
P("Build a wearable control in which a few deliberate hand gestures each trigger a distinct action on screen, "
  "while everything else the hand does stays silent. First version:")
table([
    ["Class", "Action", "Notes"],
    ["Spiderman (index + pinky out, middle + ring curled)", "Fire webs / show the web image",
     "Finger gesture: smaller, deeper muscles, so a weaker and less distinct signal than fist. Hold firmly."],
    ["Fist", "Open a different image", "Strongest, most separable signal on this band (91–99% so far)."],
    ["Everything else", "Nothing", "Rest, typing, open hand, pointing, thumbs up, moving the arm, scratching… "
     "This class decides whether the system feels reliable."],
], [55, 40, 75])
H2("What makes it feel reliable")
P("The danger is not missing a gesture; it is firing an action by accident. Four standard defences:")
bullets([
    "<b>Train “everything else” on lots of variety</b>: record a minute of normal activity and label it as "
    "the silent class, not just one rest pose.",
    "<b>Reject low-confidence decisions</b>: if the model is not clearly sure, output nothing "
    "(confidence-based rejection, Scheme et al., 2013).",
    "<b>Require a hold</b>: the gesture must be recognised continuously for about 0.3–0.5 s before the action fires.",
    "<b>Add a cooldown</b> of about 1 s after each action so one gesture fires once.",
])
P("Measure success with two numbers: <b>hit rate</b> (how often a deliberate gesture fires its action) and "
  "<b>false triggers per minute</b> during ordinary activity. Both matter more than an offline accuracy figure.")

# ---------------------------------------------------------------- hardware
H1("2. Is the hardware sound?")
P("The device check in our app records rest, fist, wrist out, wrist in and a forearm twist, then judges each "
  "channel by its noise at rest and how much it responds to effort (response in dB; 12 dB or more passes, "
  "under 6 dB fails). These thresholds are our own engineering judgement, not a MindRove specification.")
table([
    ["Check", "Result", "Rest noise", "Response", "Interpretation"],
    ["17 Nov, first check", "7 FAIL, 1 WARN", "28–265 µV", "−17 to +7 dB",
     "Misleading: the arm moved during the rest step, so “rest” looked louder than effort. "
     "Our check then had no protection against that (fixed)."],
    ["Same data, fixed check", "2 FAIL, 3 WARN", "8–16 µV (ch7 39 µV)", "−2 to 16 dB",
     "Ch7 noisy with heavy mains pickup: poor skin contact at that pod."],
    ["18 Nov, after reseating", "0 FAIL", "4–13 µV", "11.5–28 dB", "All channels respond; healthy."],
    ["18 Nov, band rotated one pod", "0 FAIL", "6–15 µV", "11–19 dB",
     "Ch7 problem did not return: it was contact, not the pod."],
], [33, 25, 27, 22, 63],
    shade=[(1, 1, BAD), (1, 2, WARN), (1, 3, OK), (1, 4, OK)])
P("Sample rate (500 Hz), dropped samples (0.00%), battery, accelerometer and gyroscope passed in every run.")
box("<b>Verdict:</b> the band works as intended. Every electrode carries a clean signal (a few µV at rest, which "
    "is good for dry electrodes) and responds to muscle effort. There is no hardware reason to return it. "
    "Caveat: this is as far as testing at home can go; it cannot rule out a fault that appears later, so note "
    "the seller’s return deadline.", OK)
H2("Two bugs in our own check, now fixed")
bullets([
    "<b>Movement during rest</b> inflated the baseline. Fix: levels are now medians of 200 ms windows, and parts "
    "of the rest step where the gyroscope shows movement are left out (reported as “Still at rest”).",
    "<b>Mains hum warning on every channel.</b> Once rest was truly quiet (~5 µV), the 10–290 µV of 50 Hz pickup "
    "was naturally “most of the signal”. The filter removes hum anyway. Fix: hum now warns only when one channel "
    "picks up far more than the others, which is what points to a bad contact.",
])

# ---------------------------------------------------------------- stability
H1("3. Why recognition drifts: strap, electrodes, arm position")
H2("What the recording showed")
P("A 70-second labelled recording (18 Nov) was clean at rest (4–12 µV per channel). Two kinds of disturbance:")
bullets([
    "<b>All channels jumping together</b> (1000–3000 µV for about 1 s, with a gyroscope spike). A disturbance "
    "common to every channel points at the shared reference/bias contact, matching your observation that the "
    "reference electrode lifted off the skin.",
    "<b>Large baseline swings</b> (20–80 mV within half a second) during open hand and wrist movements: the "
    "electrodes sliding or changing pressure as the forearm changes shape. The filter removes most of it, but "
    "leftovers appear as bursts that confuse the classifier.",
])
H2("Arm position: yes, it matters")
P("Holding the arm up, flat or down changes recognition for three reasons: different muscles work against "
  "gravity, the muscle bellies move under the electrodes, and turning the forearm (palm up/down) rotates the "
  "muscles relative to the band. This is the <b>limb position effect</b>; Fougner et al. (2011) measured the "
  "classification error rising from 3.8% to 18% when the arm position changed.")
bullets([
    "<b>Train in the positions you will use</b>: record each gesture with the arm on the desk, held up, and "
    "hanging down. This removes most of the effect.",
    "<b>Use the band’s accelerometer</b>: it knows the arm’s orientation. Add it as an input, or train one model "
    "per position, or simply ignore gestures while the arm is moving (gyroscope gating).",
    "If the action only needs to work at a desk, keep the arm in one posture and say so in your methods.",
])
H2("Wearing the band")
numbered([
    "Thickest part of the forearm, a few cm below the elbow; the cone shape stops it sliding toward the wrist.",
    "Tight, as you have now worked out. A self-adhesive bandage (Coban-type) over the band helps further.",
    "Dampen the skin under every pod <b>including the reference</b>; shave if the arm is hairy.",
    "Same orientation every time (mark the skin or note which pod sits on top). Wait 1–2 minutes to settle.",
    "Run the device check: every channel should show a few µV at rest and respond to effort.",
])

# ---------------------------------------------------------------- recognition results
story.append(PageBreak())
H1("4. Recognition results so far")
table([
    ["Run", "Gestures", "How it was scored", "Result"],
    ["Our app, 17 Nov", "rest, fist, open, wrist in, wrist out", "Rounds the model never trained on", "<b>84%</b> "
     "(rest 99, fist 91, wrist in 94; open and wrist out confused: same extensor muscles)"],
    ["Our app, 18 Nov", "same five", "Same", "<b>72%</b> (rest and wrist in confused; band moving between rounds)"],
    ["NaviFlame, 18 Nov", "7 (rest, thumbs up, peace, fist, point, wrist up, wrist down)",
     "Its own random split", "98% reported"],
    ["NaviFlame, same data", "same seven", "First 60% of each take to train, last 30% to test",
     "<b>84%</b> (thumbs up taken as rest 46%, peace as wrist up 51%)"],
    ["Simple features, same data", "same seven", "Same honest split", "<b>99%</b>"],
], [30, 42, 45, 53])
H2("Why NaviFlame’s 98% is inflated")
P("NaviFlame records one 8-second take per gesture, cuts it into 100-sample windows that start every 10 "
  "samples (90% overlap), and then picks validation windows at random. Almost every validation window has "
  "near-identical neighbours in the training set, so the test checks memory of that take, not recognition of "
  "the gesture. Two further issues:")
bullets([
    "<b>One take per gesture</b>: nothing teaches the model how the signal varies from attempt to attempt.",
    "<b>Start-of-take contamination</b>: in your data the first fifth of the rest take averaged 38 µV and the end "
    "4 µV (filter start-up plus the movement of pressing Enter). The model learns that glitch as part of the gesture.",
])
H2("Fixes")
bullets([
    "Record several short takes per gesture (3–5), ideally with the band reseated between some of them.",
    "Validate on whole takes the model never saw (“leave one take out”), never on random overlapping windows.",
    "Drop the first ~0.5–1 s of every take; our app already trims reaction time from each hold.",
    "Judge the system live, with hit rate and false triggers per minute.",
])
H2("Are the MindRove developers incompetent?")
P("No. NaviFlame is a quick-start demo, and a demo is tuned to look good within two minutes of setup. Random "
  "splits of overlapping windows are among the most common mistakes in published EMG work too, which is "
  "exactly why it is worth knowing. Their pretrained-features-plus-small-classifier design is reasonable; it "
  "needs better training data and an honest test, not a different model.")
box("<b>Key insight:</b> within one take, even the simplest method separated your 7 gestures 99% of the time. "
    "The information is in the signal. Live failures come from the signal changing between training and use. "
    "So the upgrade path is better data and decision rules first; bigger models only help once you have many "
    "sessions of varied data.")

# ---------------------------------------------------------------- tips
story.append(PageBreak())
H1("5. Practical checklist")
H2("Every session")
numbered([
    "Wear the band as in section 3, wait 1–2 minutes, run the device check.",
    "Retrain (about 2 minutes): several short rounds per gesture, in the arm positions you will use, plus a "
    "minute of ordinary activity for the silent class.",
    "Start the recorder, label what you do with the activity buttons, add notes for anything unusual "
    "(band slipped, sweaty, coffee).",
])
H2("Gestures")
bullets([
    "Make them deliberate and consistent: same hand shape, same firmness, held still.",
    "Choose actionable gestures that use different muscles. Fist (flexors) and spiderman (finger extensors) are a "
    "good pair; avoid two gestures that both mainly bend the wrist back, like open hand and wrist out.",
    "Include confusable lookalikes (point, thumbs up, open hand) in the silent class so the model learns to "
    "reject them.",
])
H2("Software rules (planned for our app)")
bullets([
    "Confidence threshold: no action unless the model is clearly sure.",
    "Hold time (~0.4 s) and cooldown (~1 s) per action.",
    "Gyroscope gating: ignore decisions while the arm is moving fast.",
    "Short majority vote over the last few decisions to stop flicker.",
])
H2("For research")
bullets([
    "Score on held-out rounds, sessions or days, never on random overlapping windows.",
    "Report the per-session calibration, arm postures, electrode placement and the number of sessions.",
    "Keep the raw recordings (data/sessions/…): raw EMG, motion, labels and notes, so any later method can be "
    "re-tested on the same data. Back the data folder up; it is not stored in git.",
    "Cross-session robustness of a low-cost dry-electrode band is itself an open research question you are "
    "well placed to study.",
])

# ---------------------------------------------------------------- roadmap
H1("6. Roadmap")
table([
    ["Step", "What", "Done when"],
    ["1", "Actions tab in our app: map spiderman and fist to images/keys; silent class; rejection, hold, cooldown, "
     "gyroscope gating.", "Spiderman and fist fire their actions; ordinary use stays silent."],
    ["2", "Training mode with several short rounds, arm positions and a guided “normal activity” minute.",
     "Live hit rate above 90% at the desk."],
    ["3", "Measure: 5 minutes of ordinary use per session, count false triggers.", "Fewer than 1 per minute."],
    ["4", "Collect labelled sessions over several days with the recorder.", "10+ sessions on file."],
    ["5", "Cross-session models: pooled training, adaptation, then deep models (as in the papers below).",
     "Less or no per-session retraining."],
], [12, 98, 60])

# ---------------------------------------------------------------- benchmark paper
story.append(PageBreak())
H1("7. The method to aim for: Kaifosh &amp; Reardon, Nature 2025")
P("<b>A generic non-invasive neuromotor interface for human-computer interaction.</b> Reality Labs at Meta. "
  "Nature 645:702–711, 2025. doi:10.1038/s41586-025-09255-w. Code and data are public.", "small")
P("This is the best methodological model for your project. It tackles exactly your problem (discrete hand "
  "gestures that trigger actions, with everything else ignored) using a dry-electrode band, and its "
  "evaluation is the most rigorous in the field. You cannot copy its scale, but you can copy its design.")
H2("What they did")
table([
    ["Part", "Their approach"],
    ["Device", "Dry-electrode wristband: 48 electrode pins forming 16 bipolar channels, sampled at 2 kHz, "
     "noise 2.46 µV rms, four band sizes, put on or taken off in seconds."],
    ["Data", "162 to 6,627 participants depending on the task. Gestures were prompted by laptop software that logged "
     "the prompt times; an alignment step then found when each gesture actually happened, because people react "
     "late and unevenly."],
    ["Variation built in", "The band was taken off and slightly repositioned between sessions, so the model "
     "learns to cope with electrode shift. Handwriting was also recorded in several postures (seated and standing)."],
    ["Discrete gestures", "Nine: index and middle finger press/release, thumb tap, thumb swipes in four directions, "
     "prompted in random order with random gaps between them."],
    ["Turning output into actions", "A gesture fires only when the model’s probability rises above a threshold "
     "(0.5 online), followed by debouncing and a state machine so that one gesture produces one event."],
    ["Offline test", "Participants never seen in training: 100 for discrete gestures (22 for the wrist task, "
     "50 for handwriting). The headline offline figure is over 90% classification accuracy."],
    ["Online test (closed loop)", "New, untrained people used the live system: 24 for discrete gestures. "
     "Measured: first-hit probability, completions per second, confusion rate and early releases. Result: "
     "0.88 gesture detections per second."],
    ["Same code online and offline", "One processing engine was used both while recording and while running "
     "models, so offline results transfer to live use."],
    ["Scaling and personalisation", "Performance improved steadily with more training participants. Fine-tuning "
     "on one person with 1–20 minutes of data improved handwriting by 16%. When a model is trained on a single "
     "person, tested on a held-out session, the person’s own model beat other people’s models for 98% of people."],
], [38, 132])
H2("The principles to copy")
numbered([
    "<b>Test on what the model has never seen</b>: whole sessions or days, ideally whole people. Never "
    "random windows from the same take.",
    "<b>Build variation into training</b>: take the band off and put it back between sessions, vary posture, "
    "randomise gesture order and timing.",
    "<b>Label carefully</b>: log when you prompted, then align to when the muscle actually fired.",
    "<b>Judge the live system</b>, with people in the loop, using event metrics (hits, misses, wrong gestures, "
    "time to complete) rather than offline accuracy alone.",
    "<b>Turn probabilities into events deliberately</b>: threshold, debounce, one event per gesture.",
    "<b>Use one code path</b> for recording, training and live use.",
    "<b>Report how performance scales</b> with the amount of data, and what personalisation adds.",
])
H2("Scaled down for one person with one MindRove band")
table([
    ["Their practice", "Your version"],
    ["Thousands of participants", "You, over many sessions and days (later a few volunteers). Report "
     "within-session, across-session and across-day results separately."],
    ["Band repositioned between sessions", "Take the band off and back on between some training rounds; "
     "record on different days."],
    ["Randomised prompts, logged times, alignment", "Our app prompts and logs every sample with the prompt; it "
     "already trims reaction time. Add random order and random gaps."],
    ["Lots of non-gesture data", "A guided minute of ordinary activity per session as the silent class."],
    ["Threshold, debounce, state machine", "Confidence threshold, hold time, cooldown (section 5)."],
    ["Closed-loop test with event metrics", "Hit rate, wrong-gesture rate and false triggers per minute "
     "during a fixed 5-minute routine."],
    ["Public data and code", "Keep your recordings and scripts; publish them with your results."],
], [55, 115])
P("Note: their device (16 channels at 2 kHz at the wrist) differs from MindRove (8 channels at 500 Hz on the "
  "forearm), so their models and data cannot be used directly with your band, but the methods carry over. "
  "Their data is licensed for non-commercial use (CC BY-NC-SA 4.0). This summary was checked against the "
  "article’s full text; architecture details are left out because they could not be confirmed.", "small")

# ---------------------------------------------------------------- papers
story.append(PageBreak())
H1("8. Reading list")
P("Checked against the publisher or preprint pages on 18 November 2026, except where marked "
  "<i>[via review]</i>: those details come from the iScience review’s description and the original was not "
  "opened. Start with the items marked [Start here].", "small")


def paper(title, cite, did, take):
    story.append(KeepTogether([
        Paragraph(title, S["h2"]),
        Paragraph(cite, S["small"]),
        Paragraph("<b>What they did:</b> " + did, S["p"]),
        Paragraph("<b>Take-away for you:</b> " + take, S["p"]),
    ]))


H2("Studies using the MindRove armband")
paper("<font color='#0b6fb8'>[Start here]</font> SRM: a source-reprojection module for cross-day sEMG gesture recognition",
      "Li D. et al., Sensors 26(12):3870, 2026. doi:10.3390/s26123870",
      "4 participants wore the MindRove armband on at least 5 separate days, performing fist, open hand, scissors, "
      "index pointing, thumbs up and rest. A temporal convolutional network trained on earlier days was adapted "
      "to new days by transforming the new day’s signals rather than retraining the classifier.",
      "Closest to your situation. Even with adaptation, new-day accuracy was only about 71–73% (62–90% per person); "
      "the authors blame electrode displacement and skin-contact changes. Confirms that per-session calibration is "
      "normal and that cross-day robustness is an open problem.")
paper("<font color='#0b6fb8'>[Start here]</font> Decoding high-dimensional finger motion from EMG using Riemannian features and RNNs (EMG-FK dataset)",
      "Colot M. et al., arXiv:2604.22499, 2026 (preprint). Dataset on Zenodo (record 19453843)",
      "20 participants, 30 minutes each, MindRove 8-channel armband; a webcam with MediaPipe tracked 15 finger "
      "joint angles as ground truth. Covariance-based (Riemannian) features fed a recurrent network to "
      "predict the joint angles continuously.",
      "Shows this band can track individual fingers, which is relevant for spiderman. Error about 10° within a "
      "person and 17° across people, and it runs on a Raspberry Pi 5 (useful for a wearable). The camera-labelling "
      "idea gives you automatic labels without clicking buttons. Limitation: single-session recordings only.")
paper("Use of a wearable electromyography armband to detect lift-lower tasks and classify hand loads",
      "Taori and Lim, Applied Ergonomics, 2024 <i>[via review]</i>",
      "Used the MindRove armband to detect when lifts start and end and to classify the load in the hand.",
      "Average detection accuracy 79.2–86.9%, described by the authors as leaving “substantial scope for "
      "improvement”. An example of a non-gesture use.")
paper("Classification of semi-automated labeled MindRove armband recorded EMG data",
      "Köllőd et al., CINTI-MACRo, 2022 <i>[via review]</i>",
      "6 participants, 7 static gestures, classical classifiers versus EEGNet.",
      "Only about 57–60% accuracy: an early, sobering baseline. Comparing their protocol with yours shows how much "
      "wearing, training and testing choices matter.")
paper("Physical exertion recognition using surface electromyography and inertial measurements for occupational "
      "ergonomics", "Concha-Pérez et al., Sensors, 2023 <i>[via review]</i>",
      "Combined MindRove EMG with motion sensors to recognise physical exertion at work.",
      "The review cites this study for the remark that the band “shows mediocre performance in hand gesture "
      "recognition at the current stage”. Worth reading to see exactly which conditions led to that judgement.")

H2("Background and methods")
paper("<font color='#0b6fb8'>[Start here]</font> Advances in electromyography armbands for gesture recognition and multimodal fusion (review)",
      "Zhang R. et al., iScience 29(1):114517, 2025. doi:10.1016/j.isci.2025.114517",
      "Surveys commercial and research EMG armbands, including MindRove (8 channels, 24-bit, 500 Hz, Wi-Fi, "
      "4–6 h battery, about $729), and how they are combined with motion and other sensors.",
      "The best map of the field. Recurring themes: electrode displacement, sweat and fatigue reduce accuracy over "
      "time; future systems need adaptation and little per-user calibration.")
paper("<font color='#0b6fb8'>[Start here]</font> Resolving the limb position effect in myoelectric pattern recognition",
      "Fougner A. et al., IEEE Trans. Neural Syst. Rehabil. Eng. 19(6):644–651, 2011",
      "Measured how arm posture changes EMG recognition and tested two fixes: training in several positions, and "
      "adding accelerometers that sense the arm’s orientation.",
      "Directly answers your arm-position question. Error rose from 3.8% to 18% with posture changes; training in "
      "multiple positions and adding accelerometer data both helped. Your band already has an accelerometer.")
paper("<font color='#0b6fb8'>[Start here]</font> Confidence-based rejection for improved pattern recognition myoelectric control",
      "Scheme E., Hudgins B., Englehart K., IEEE Trans. Biomed. Eng. 60(6):1563–1570, 2013. "
      "doi:10.1109/TBME.2013.2238939",
      "Extended the standard LDA classifier (the one our app uses) to output a confidence score and to reject "
      "decisions below a per-class threshold.",
      "The textbook basis for keeping “everything else” silent. A follow-up (Robertson et al., IEEE JBHI, 2019) "
      "found thresholds around 0.60–0.75 worked best.")
paper("A new strategy for multifunction myoelectric control",
      "Hudgins B., Parker P., Scott R., IEEE Trans. Biomed. Eng. 40(1):82–94, 1993. doi:10.1109/10.204774",
      "Introduced the classic short-window time-domain features (mean absolute value, waveform length, zero "
      "crossings, slope sign changes) for EMG pattern recognition.",
      "The origin of the simple features our app uses, which gave 99% within a take. Good to cite as the baseline.")
paper("Deep learning for electromyographic hand gesture signal classification using transfer learning",
      "Côté-Allard U. et al., IEEE Trans. Neural Syst. Rehabil. Eng. 27(4):760–771, 2019. "
      "doi:10.1109/TNSRE.2019.2896269",
      "Pre-trained convolutional networks on data pooled from many Myo-armband users, then fine-tuned on each new "
      "user with little data. 98.3% for 7 gestures over 17 people offline; real-time feedback let users adapt and "
      "reduced degradation over time.",
      "The same idea as NaviFlame (pretrained features plus a small per-user part), done and evaluated properly. "
      "Also shows that a person learning from live feedback is part of the system.")
paper("<font color='#0b6fb8'>[Start here]</font> A generic non-invasive neuromotor interface for human-computer interaction (see section 7)",
      "Kaifosh P., Reardon T. R. (Reality Labs, Meta), Nature 645:702–711, 2025. doi:10.1038/s41586-025-09255-w",
      "Built a dry-electrode EMG wristband and trained models on data from a very large number of people, so "
      "gestures, cursor control and handwriting worked for new users without calibration. Code is public.",
      "Where the field is heading for your exact use case (discrete gestures that trigger actions). It shows that "
      "working without calibration is achievable, but only with very large datasets.")
paper("FORS-EMG: a novel sEMG dataset for hand gesture recognition across multiple forearm orientations",
      "Rumman M. et al., arXiv:2409.07484, 2024",
      "A public dataset recording the same gestures with the forearm in three orientations.",
      "Ready-made data to study the arm-position effect before collecting your own.")

doc = SimpleDocTemplate(OUT, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm,
                        bottomMargin=20 * mm, title="MindRove Armband 2 project report", author="Minseok Ryu")
doc.build(story, onFirstPage=footer, onLaterPages=footer)
print("wrote", OUT)
