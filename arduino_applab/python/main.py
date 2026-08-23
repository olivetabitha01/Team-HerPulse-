"""
HerPulse — UNO Q App Lab, Python (MPU / Linux) side.

Runs alongside sketch/sketch.ino as one App Lab "App". Its two jobs:

  1. check_pad()      — called BY the sketch when it needs a yes/no on
                         whether a pad is present. Right now this is a
                         stub (always True) — this is exactly the "leave
                         space for it" hook you asked for. See the
                         WEBCAM INTEGRATION section below for how to
                         wire in real detection later, either running
                         here or on your laptop.

  2. receive_reading() — called BY the sketch once scanPad() has all 9
                         raw R/G/B values. This forwards them to your
                         existing Flask backend's /api/device/data
                         endpoint over Wi-Fi — the SAME endpoint your
                         trained model bundle already consumes, so
                         nothing on the Flask/website side changes.

Credentials used below must match backend/app.py:
  FLASK_SERVER_URL -> wherever you're running `python app.py`
  DEVICE_ID        -> HERPULSE_DEVICE_NAME env var (default HerPulse_Q)
  DEVICE_KEY       -> HERPULSE_DEVICE_KEY env var (default herpulse-device-key)
"""

import socket
import requests
from arduino.app_utils import Bridge, App

# ---- EDIT THESE THREE to match your setup -------------------------------
FLASK_SERVER_URL = "http://192.168.1.50:5000/api/device/data"  # your laptop's LAN IP
DEVICE_ID = "HerPulse_Q"
DEVICE_KEY = "herpulse-device-key"
# --------------------------------------------------------------------------

# ---- pad-image classifier (second dataset — not shared with me yet) ------
# Once you send over the image dataset, I'll write a training script for
# it (same pattern as backend/train_model.py) that saves to
# models/pad_image_model.joblib. This loads it automatically the same way
# app.py loads the biomarker model — nothing else here needs to change.
PAD_MODEL = None
try:
    import joblib
    PAD_MODEL = joblib.load("models/pad_image_model.joblib")
    print("Loaded pad-detection image model.")
except Exception:
    print("No pad-detection image model yet — check_pad() stub returns True. "
          "Share the image dataset and I'll build the training script for it.")
# ---------------------------------------------------------------------------


def get_local_ip() -> str:
    """Best-effort LAN IP of this board, for showing on the LCD at boot."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "no IP found"


def check_pad() -> bool:
    """
    Called by the sketch before starting a run.

    WEBCAM INTEGRATION — 4-5 points for wiring this in once ready:

      1. If the webcam is on your LAPTOP (as you said, for now): run a
         small Flask/FastAPI endpoint there (e.g. /pad-status) that
         opens the webcam with OpenCV, runs your friend's trained
         detection model, and returns {"pad_present": true/false}.
         Replace the `return True` below with a
         `requests.get("http://<laptop-ip>:PORT/pad-status")` call.

      2. If the webcam is plugged into the UNO Q itself instead: import
         cv2 here directly (`pip install opencv-python` in this App's
         Python environment via App Lab's package manager), open
         cv2.VideoCapture(0), grab a frame, and run the model in-process
         — no network call needed.

      3. Either way, keep the MODEL FILE separate from this glue code:
         load it once at import time (not inside check_pad(), which
         runs on every button press) so you're not reloading it per run.

      4. Keep the return type a plain bool — the sketch's
         Bridge.call("check_pad").result(detected) expects exactly that.

      5. Until then, this stub always says yes so you can test the rest
         of the sequence end-to-end without the webcam piece finished.
    """
    if PAD_MODEL is not None:
        # TODO once the image dataset is shared: capture a frame (cv2 here,
        # or an HTTP call to a laptop-hosted capture service) and call
        # PAD_MODEL.predict(...) on it. Shape of this depends entirely on
        # how that model was trained, which I don't know yet.
        pass
    return True


def receive_reading(r_hb, g_hb, b_hb, r_protein, g_protein, b_protein, r_ph, g_ph, b_ph) -> float:
    """Called by the sketch's push_reading() once scanPad() has all 9 values."""
    payload = {
        "device_id": DEVICE_ID,
        "r_hb": r_hb, "g_hb": g_hb, "b_hb": b_hb,
        "r_protein": r_protein, "g_protein": g_protein, "b_protein": b_protein,
        "r_ph": r_ph, "g_ph": g_ph, "b_ph": b_ph,
    }
    try:
        resp = requests.post(
            FLASK_SERVER_URL,
            json=payload,
            headers={"X-Device-Key": DEVICE_KEY},
            timeout=5,
        )
        print(f"Posted reading to Flask -> {resp.status_code}: {resp.text}")
        return 1.0 if resp.ok else 0.0
    except Exception as exc:
        print(f"Could not reach Flask backend: {exc}")
        return 0.0


# Expose these two Python functions to the sketch (MCU) side.
Bridge.provide("check_pad", check_pad)
Bridge.provide("receive_reading", receive_reading)

# Show this board's own IP on the LCD at boot — the answer to "IP address
# identification and display". Find the SAME IP later from the App Lab
# console (`hostname -I`) if you need it again without waiting for reboot.
my_ip = get_local_ip()
print(f"Board IP: {my_ip}")
Bridge.call("show_ip", my_ip)

App.run()
