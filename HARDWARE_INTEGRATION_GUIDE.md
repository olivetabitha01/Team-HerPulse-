# HerPulse — Full Build Guide (Hardware + AI + Website) — v2

Updated against your actual circuit diagram. One file, every step —
read top to bottom in order.

---

## 0. What the diagram confirmed — and corrected from before

I zoomed into every region of the diagram you sent. Two things in my first
pass were wrong, now fixed in `arduino_applab/`:

1. **3 motor drivers / 5 motors, not 2 drivers / 4 motors.** Driver A (2
   motors) runs your syringe + rack-and-pinion. Driver B — which I'd missed
   entirely — runs a **single motor**: the RGB sensor's scan carriage that
   moves it across the 3 pad zones. Driver C runs the 2 yellow TT gearbox
   disposal motors.
2. **Your LCD is a parallel HD44780-style display** (a full pin row across
   the top), not an I2C backpack — the sketch now uses `LiquidCrystal`
   instead of `LiquidCrystal_I2C`.

**Power, confirmed:** one 3-cell battery pack → rocker switch → buck
converter (steps down to 5V for logic) → raw battery voltage runs the
motor drivers and MOSFET-switched fan/LEDs directly. This is simpler than
what I assumed earlier (no split USB-C/12V needed) — everything shares one
ground because it's one battery.

**What I genuinely could not read, even at 8x zoom directly on the pin
header:** the actual pin numbers. The diagram's text is below the
resolution it was exported at — this isn't something a tighter crop fixes,
the detail isn't in the file. Every `#define` in `sketch/sketch.ino` is a
placeholder flagged for you to fill in. **Fastest way to fix this:** just
type out the pin list as text, the way you did the first time over voice —
that's unambiguous, reading colored wires in a diagram isn't.

---

## 1. Architecture

```
┌──────────────────────┐   Bridge (RPC)   ┌────────────────────────────┐
│  Sketch (MCU)         │ <──────────────> │  Python (MPU/Linux)          │
│  arduino_applab/       │                  │  arduino_applab/python/       │
│  sketch/sketch.ino      │                  │  main.py                       │
│  - button, LCD, LED     │                  │  - relay RGB data to Flask     │
│  - 3 drivers / 5 motors │                  │  - pad-detection hook (stub)   │
│  - RGB sensor read      │                  │  - shows board IP on LCD       │
└──────────────────────┘                  └───────────┬────────────────┘
                                                        │ Wi-Fi (HTTP POST)
                                                        ▼
                                          ┌────────────────────────────┐
                                          │  Flask backend (VS Code)     │
                                          │  backend/app.py                │
                                          │  - trained Random Forest      │
                                          │  - login, questionnaire,       │
                                          │    report                       │
                                          └───────────┬────────────────┘
                                                        │ Wi-Fi (browser)
                                                        ▼
                                          ┌────────────────────────────┐
                                          │  Website (phone browser)     │
                                          └────────────────────────────┘
```

---

## 2. Stage-by-stage execution — do this in order

### Stage 1 — Wire it (hardware first, no code yet)
1. Wire per section 0 above, filling in the real pin numbers.
2. Power-on check with no code running: confirm the rocker switch turns
   the whole board on, and check for 0Ω continuity between the battery's
   ground and the UNO Q's GND pin (confirms common ground).

### Stage 2 — Open App Lab, create the App
1. Launch **App Lab** (desktop app, or the SBC web UI if the board is in
   standalone mode) and connect to your UNO Q.
2. Create a **New App**. App Lab generates a default `sketch/` and
   `python/` folder plus an `app.yaml` — this is the project tree you'll
   see on the left side of the editor.
3. **Delete the generated sketch and python file contents** and paste in
   `arduino_applab/sketch/sketch.ino` and `arduino_applab/python/main.py`
   from this delivery. Copy `arduino_applab/app.yaml`'s content into the
   App's own `app.yaml` too (App Lab may auto-manage some of this — if it
   complains, just make sure the `sketch:` and `python:` paths point at
   your actual files).

### Stage 3 — What "Bricks" actually are, and how to check one
You asked how to "see what brick files say" — here's exactly that:
1. In App Lab's left sidebar there's a **Bricks** panel. Click it to browse
   available ones (web UI, database, AI/vision models, etc.).
2. Click on **any Brick** to open its documentation, usage example, and
   API reference right inside App Lab — this is how you'd confirm a
   Brick's exact Python import path and function signatures before using
   it, rather than guessing.
3. You aren't using any Bricks yet in this build (the sketch/python pair
   above is plain Bridge code) — but when you're ready to add the webcam
   step, check the Bricks panel for a camera/vision Brick before writing
   raw OpenCV code, in case one already does what you need.
4. If you click on an already-used Brick, App Lab also shows you *which of
   your Apps use it* — useful once you have more than one App.

### Stage 4 — Edit the two config lines
In `arduino_applab/python/main.py`, before running anything:
```python
FLASK_SERVER_URL = "http://<your-laptop-IP>:5000/api/device/data"
```
Get `<your-laptop-IP>` per section 3 below.

### Stage 5 — Run the App
1. Press **Run** in App Lab. It compiles the sketch, uploads it to the
   STM32, sets up the Python environment, and starts both sides together.
2. The first run downloads a Docker container for the Python environment
   — this is slow once, fast after.
3. Watch the LCD: it should show `BOOTING`, then briefly the board's own
   **IP address** (this is the "IP display" you asked for — `main.py`
   sends it over on startup), then settle on `IDLE`.

### Stage 6 — Start Flask (separate terminal, VS Code)
```bash
cd backend
pip install -r requirements.txt
python app.py
```

### Stage 7 — Open the website on your phone
Same Wi-Fi network as the laptop and the board. Browse to
`http://<laptop-IP>:5000/`, log in, go to Connect, enter the device
name/password (section 4), connect.

### Stage 8 — Run a full cycle
Press the physical button. Watch the LCD walk through:
`DETECTING → INJECTING → REACTING → SCANNING → PROCESSING → DISPOSING → DONE`.

### Stage 9 — Confirm the data actually landed
```bash
sqlite3 backend/herpulse.db "SELECT * FROM sensor_readings ORDER BY id DESC LIMIT 1;"
```

### Stage 10 — Finish on the phone
Answer the 10 questions, submit, watch processing, check the report —
real Hb/Protein/pH values, risk levels, and a diagnosis pulled from your
dataset's own language.

---

## 3. Finding IP addresses — both directions

**Laptop's IP** (so the board and phone know where Flask is):
```bash
ipconfig       # Windows — look for "IPv4 Address"
ifconfig       # Mac/Linux, or: ip addr
```

**Board's own IP** (so you know where to find/monitor the board itself):
- **Shown automatically on the LCD** at boot (added in this update).
- Or manually: in App Lab, click the **console** button (bottom-left),
  enter your password, and you're in a full Debian shell on the board —
  run `hostname -I` there any time.

All three devices — laptop, board, phone — must be on the **same Wi-Fi**.

---

## 4. Credentials — everything in one place

| What | Value | Where it's checked |
|---|---|---|
| Website login | `demo` / `herpulse123` | `backend/app.py` (seeded on first run) |
| Create your own website login | `python create_user.py <username> <password>` | run from `backend/` |
| Device name (connect screen) | `HerPulse_Q` | `HERPULSE_DEVICE_NAME` env var |
| Device password (connect screen) | `Herpulse123` | `HERPULSE_DEVICE_PASSWORD` env var |
| Device→backend data key (not user-facing) | `herpulse-device-key` | `HERPULSE_DEVICE_KEY` env var — must match `DEVICE_KEY` in `main.py` |

---

## 5. The second dataset — pad/image detection (webcam)

You mentioned a **separate dataset for the app/processor side**, for
webcam-based pad detection/identification, run on the MPU. I haven't seen
that dataset yet — once you share it, I'll write a training script for it
exactly the way I did for the biomarker Excel file (`backend/train_model.py`):
inspect its actual shape first (image folders? labeled CSV of file paths?
how many classes — just pad/no-pad, or pad *type* identification too?),
then build a matching training script that saves to
`models/pad_image_model.joblib`.

`arduino_applab/python/main.py`'s `check_pad()` already has the loading
hook wired in (mirrors how `app.py` loads the biomarker bundle) — right
now it prints "no pad-detection image model yet" and falls back to always
returning `True`, so the rest of the sequence runs end-to-end while you
wait on that dataset, exactly as you asked ("leave space").

Once shared, tell me:
- how many images, and how they're organized (folder-per-class is easiest)
- what the webcam will actually be looking at (just presence/absence of a
  pad, or also distinguishing pad types/conditions)

---

## 6. Files in this delivery

```
arduino_applab/
  app.yaml
  sketch/sketch.ino      MCU code — 3 drivers/5 motors, parallel LCD, IP display
  python/main.py          MPU code — Bridge relay to Flask, pad-model hook, IP push

backend/                 unchanged — trained model, Flask, website all as before
frontend/                unchanged
```
