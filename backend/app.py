"""
HerPulse backend — Part 1 (UI/UX + device connection + data flow)

Flow this serves:
  Website (frontend/) <-> Flask (this file) <-> Arduino device (Wi-Fi POST)

Responsible for:
  - Login / session (cookie-based, no client-side storage needed)
  - Device "connect" handshake + status
  - Serving the 10 questionnaire questions + collecting answers
  - Receiving sensor readings from the Arduino board
  - Simulating the AI processing step (swap simulate_ai_model() for your
    real trained model call when Part 2 is ready)
  - Producing the final report the frontend renders

Run:
    pip install -r requirements.txt
    python app.py
Then open http://127.0.0.1:5000/ in a browser.
"""

import os
import sqlite3
import threading
import time
from datetime import datetime

from flask import Flask, request, jsonify, session, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(os.path.dirname(BASE_DIR), "frontend")
DB_PATH = os.path.join(BASE_DIR, "herpulse.db")
DEVICE_API_KEY = os.environ.get("HERPULSE_DEVICE_KEY", "herpulse-device-key")  # Arduino sends this header
DEVICE_NAME = os.environ.get("HERPULSE_DEVICE_NAME", "HerPulse_Q")            # shown + typed on connect.html
DEVICE_PASSWORD = os.environ.get("HERPULSE_DEVICE_PASSWORD", "Herpulse123")   # typed on connect.html

app = Flask(__name__, static_folder=None)
app.secret_key = os.environ.get("HERPULSE_SECRET_KEY", "dev-secret-change-me")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

# In-memory processing status per user id — fine for a hackathon build;
# move to the DB/a task queue if you need multi-process deployment.
PROCESSING_STATE = {}

QUESTIONS = [
    {"id": "cycle_regularity", "text": "Is your menstrual cycle regular?", "type": "single",
     "options": ["Yes", "No", "Sometimes"]},
    {"id": "cycle_length", "text": "How many days does your cycle usually last?", "type": "single",
     "options": ["Under 21 days", "21-35 days", "Over 35 days"]},
    {"id": "flow_intensity", "text": "How would you describe your menstrual flow?", "type": "single",
     "options": ["Light", "Medium", "Heavy"]},
    {"id": "clots", "text": "Do you notice blood clots during your period?", "type": "single",
     "options": ["Yes", "No"]},
    {"id": "pain_level", "text": "Rate your menstrual pain (cramps).", "type": "scale", "scale_max": 5},
    {"id": "conditions", "text": "Do you have any of the following?", "type": "multi",
     "options": ["Thyroid", "PCOS / PCOD", "None"]},
    {"id": "status", "text": "Which applies to you right now?", "type": "single",
     "options": ["Pregnant", "Trying to conceive", "Menopause", "None"]},
    {"id": "symptoms", "text": "Have you noticed any unusual symptoms recently?", "type": "multi",
     "options": ["Unusual odor", "Unusual discharge", "Irritation", "None"]},
    {"id": "emotional_state", "text": "How do you feel emotionally during your cycle?", "type": "single",
     "options": ["Normal", "Irritated", "Anxious", "Depressed"]},
    {"id": "energy_level", "text": "How is your energy level and appetite?", "type": "single",
     "options": ["Normal", "Low energy", "High fatigue"]},
]


# ---------------------------------------------------------------- database

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            device_id TEXT NOT NULL,
            ip TEXT,
            connected_at TEXT
        );
        CREATE TABLE IF NOT EXISTS sensor_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            r_hb REAL, g_hb REAL, b_hb REAL,
            r_protein REAL, g_protein REAL, b_protein REAL,
            r_ph REAL, g_ph REAL, b_ph REAL,
            raw_json TEXT,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            answers_json TEXT NOT NULL,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            report_json TEXT NOT NULL,
            created_at TEXT
        );
    """)
    # Seed one demo account so the frontend is usable out of the box.
    demo_exists = conn.execute("SELECT 1 FROM users WHERE username = ?", ("demo",)).fetchone()
    if not demo_exists:
        conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            ("demo", generate_password_hash("herpulse123")),
        )
    conn.commit()
    conn.close()


# ------------------------------------------------------------------ helpers

def login_required(fn):
    from functools import wraps

    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "Not logged in"}), 401
        return fn(*args, **kwargs)

    return wrapper


def latest_reading_for(device_id):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM sensor_readings WHERE device_id = ? ORDER BY id DESC LIMIT 1",
        (device_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


TRAINED_MODEL = None  # populated by load_trained_model() once train_model.py has been run

def load_trained_model():
    """
    Looks for models/herpulse_models.joblib (produced by train_model.py
    against Integrated_Menstrual_Biomarker_Dataset_300_Samples.xlsx, or
    whatever real dataset replaces it). If found, real Random Forest
    predictions replace the rule-based placeholder below automatically —
    nothing else in this file needs to change.
    """
    global TRAINED_MODEL
    bundle_path = os.path.join(BASE_DIR, "models", "herpulse_models.joblib")
    if os.path.exists(bundle_path):
        import joblib
        TRAINED_MODEL = joblib.load(bundle_path)
        print(f"Loaded trained model bundle from {bundle_path}")
    else:
        print("No trained model found yet — using placeholder threshold logic. "
              "Run train_model.py once you have a labeled dataset.")


def compute_ratio(r, g, b):
    """Matches Hb_Ratio / Protein_Ratio / pH_Ratio in the training dataset: G / (R+G+B)."""
    total = (r or 0) + (g or 0) + (b or 0)
    return (g / total) if total else 0.0


# Risk-label -> UI risk level. Dataset label sets differ per biomarker
# (Hb: Normal/Low/Critical, Protein: Normal/Abnormal, pH: Normal/Elevated/Infection)
# so each gets its own mapping.
LABEL_TO_RISK = {
    "hb":      {"Normal": "low", "Low": "medium", "Critical": "high"},
    "protein": {"Normal": "low", "Abnormal": "high"},
    "ph":      {"Normal": "low", "Elevated": "medium", "Infection": "high"},
}
RISK_TO_STATUS = {"low": "ok", "medium": "warn", "high": "risk"}
RISK_LABEL = {"low": "Low risk", "medium": "Medium risk", "high": "High risk"}

BIOMARKER_META = {
    "hb":      {"label": "Hemoglobin (Hb)", "unit": " g/dL"},
    "protein": {"label": "Protein", "unit": " g/dL"},
    "ph":      {"label": "pH level", "unit": ""},
}


def predict_with_trained_model(reading):
    """reading: dict with r_hb, g_hb, b_hb, r_protein, ... (raw device values)."""
    import numpy as np

    metrics = []
    label_by_biomarker = {}

    for name, cfg in TRAINED_MODEL["biomarkers"].items():
        r = reading.get(f"r_{name}") or 0
        g = reading.get(f"g_{name}") or 0
        b = reading.get(f"b_{name}") or 0
        x = np.array([[r, g, b]])

        value = float(cfg["value_model"].predict(x)[0])
        label = cfg["label_model"].predict(x)[0]
        label_by_biomarker[name] = label

        risk = LABEL_TO_RISK.get(name, {}).get(label, "medium")
        meta = BIOMARKER_META[name]
        metrics.append({
            "label": meta["label"],
            "value": round(value, 2),
            "unit": meta["unit"],
            "status": RISK_TO_STATUS[risk],
            "risk": risk,
            "risk_label": RISK_LABEL[risk],
            "model_label": label,
        })

    issue = TRAINED_MODEL["issue_lookup"].get(
        (label_by_biomarker.get("hb"), label_by_biomarker.get("protein"), label_by_biomarker.get("ph"))
    )
    return metrics, issue


def predict_with_placeholder(reading):
    """Fallback used only until train_model.py has produced a real model bundle."""
    hb = reading.get("hb", 11.4) if reading else 11.4
    ph = reading.get("ph", 6.6) if reading else 6.6
    protein = reading.get("protein", "Normal") if reading else "Normal"

    def hb_risk(v):
        return "high" if v < 9.5 else ("medium" if v < 11.0 else "low")

    def ph_risk(v):
        return "high" if (v < 4.0 or v > 8.0) else ("medium" if (v < 4.5 or v > 7.0) else "low")

    def protein_risk(v):
        return "high" if str(v).lower() not in ("normal",) else "low"

    metrics = []
    for name, val, risk_fn in (("hb", hb, hb_risk), ("ph", ph, ph_risk), ("protein", protein, protein_risk)):
        risk = risk_fn(val)
        meta = BIOMARKER_META[name]
        metrics.append({
            "label": meta["label"], "value": val, "unit": meta["unit"],
            "status": RISK_TO_STATUS[risk], "risk": risk, "risk_label": RISK_LABEL[risk],
        })
    return metrics, None


def simulate_ai_model(sensor_reading, answers):
    """
    Central prediction entry point. Uses the trained Random Forest bundle
    if train_model.py has been run; otherwise falls back to simple
    thresholds so the pipeline still works with dummy data.
    """
    if TRAINED_MODEL is not None and sensor_reading:
        metrics, issue = predict_with_trained_model(sensor_reading)
    else:
        metrics, issue = predict_with_placeholder(sensor_reading)

    risks = [m["risk"] for m in metrics]
    see_doctor = "high" in risks
    overall = "high" if see_doctor else ("medium" if "medium" in risks else "low")

    suggestions = []
    if issue and issue != "Within prototype reference range":
        suggestions.append(issue)
    if answers.get("pain_level") and int(answers.get("pain_level", 0)) >= 4:
        suggestions.append("High reported pain — flag it to a doctor if it recurs cycle after cycle.")
    if answers.get("energy_level") in ("Low energy", "High fatigue"):
        suggestions.append("Low energy can pair with low iron — prioritize rest and hydration this week.")
    if not suggestions:
        suggestions.append("Everything's tracking within the normal range — keep up your regular routine.")

    return {
        "metrics": metrics,
        "suggestions": suggestions,
        "overall_risk": overall,
        "see_doctor": see_doctor,
        "doctor_note": issue if (see_doctor and issue) else (
            "One or more readings are outside the normal range — please see a gynecologist for a proper check-up."
            if see_doctor else None
        ),
    }


def run_processing_job(user_id, device_id, answers):
    """Runs in a background thread so /api/process/start returns instantly."""
    try:
        time.sleep(3.5)  # stand-in for real sensor read + model inference time
        reading = latest_reading_for(device_id)
        result = simulate_ai_model(reading, answers)
        result["generated_at"] = datetime.now().strftime("%b %d, %Y - %I:%M %p")

        conn = get_db()
        conn.execute(
            "INSERT INTO reports (user_id, report_json, created_at) VALUES (?, ?, ?)",
            (user_id, str(result), datetime.utcnow().isoformat()),
        )
        conn.commit()
        conn.close()

        PROCESSING_STATE[user_id] = {"status": "done", "report": result}
    except Exception as exc:  # pragma: no cover - defensive
        PROCESSING_STATE[user_id] = {"status": "error", "error": str(exc)}


# --------------------------------------------------------------------- auth

@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if not username or not password:
        return jsonify({"error": "Username and password are required."}), 400

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()

    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Incorrect username or password."}), 401

    session["user_id"] = user["id"]
    session["username"] = user["username"]
    return jsonify({"status": "success", "username": user["username"]})


@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"status": "success"})


@app.route("/api/me", methods=["GET"])
@login_required
def me():
    return jsonify({"username": session.get("username")})


# ------------------------------------------------------------------- device

@app.route("/api/device/connect", methods=["POST"])
@login_required
def connect_device():
    data = request.get_json(silent=True) or {}
    device_id = data.get("device_id", DEVICE_NAME)
    device_password = data.get("device_password", "")

    if device_id != DEVICE_NAME or device_password != DEVICE_PASSWORD:
        return jsonify({"error": "Incorrect device name or password."}), 401

    # Real handshake would ping the device on the LAN / wait for its
    # check-in POST to /api/device/data. Simulated here for the UI build.
    fake_ip = "192.168.1." + str(20 + (session["user_id"] % 200))

    conn = get_db()
    conn.execute(
        "INSERT INTO devices (user_id, device_id, ip, connected_at) VALUES (?, ?, ?, ?)",
        (session["user_id"], device_id, fake_ip, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()

    session["device_id"] = device_id
    session["device_ip"] = fake_ip
    return jsonify({"connected": True, "device_id": device_id, "ip": fake_ip})


@app.route("/api/device/status", methods=["GET"])
@login_required
def device_status():
    if "device_id" not in session:
        return jsonify({"connected": False, "device_id": DEVICE_NAME})
    return jsonify({"connected": True, "device_id": session["device_id"], "ip": session.get("device_ip")})


@app.route("/api/device/data", methods=["POST"])
def device_data():
    """
    The Arduino board POSTs here directly over Wi-Fi with the raw RGB
    triplet from each of the 3 sensor channels — the model expects exactly
    what the training dataset provides, no pre-computed values:

        POST /api/device/data
        Headers: X-Device-Key: herpulse-device-key
        Body: {
          "device_id": "HerPulse_Q",
          "r_hb": 192, "g_hb": 65, "b_hb": 36,
          "r_protein": 171, "g_protein": 84, "b_protein": 78,
          "r_ph": 164, "g_ph": 155, "b_ph": 83
        }

    The Ratio columns used in training (G / (R+G+B)) are derived on read
    in predict_with_trained_model() — no need to send them.
    """
    if request.headers.get("X-Device-Key") != DEVICE_API_KEY:
        return jsonify({"error": "Invalid device key"}), 401

    data = request.get_json(silent=True) or {}
    device_id = data.get("device_id", DEVICE_NAME)
    fields = ["r_hb", "g_hb", "b_hb", "r_protein", "g_protein", "b_protein", "r_ph", "g_ph", "b_ph"]

    conn = get_db()
    conn.execute(
        f"INSERT INTO sensor_readings (device_id, {', '.join(fields)}, raw_json, created_at) "
        f"VALUES (?, {', '.join(['?'] * len(fields))}, ?, ?)",
        (device_id, *[data.get(f) for f in fields], str(data), datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()
    return jsonify({"status": "received"})


# ------------------------------------------------------------- questionnaire

@app.route("/api/questions", methods=["GET"])
def get_questions():
    return jsonify({"questions": QUESTIONS})


@app.route("/api/submit-answers", methods=["POST"])
@login_required
def submit_answers():
    data = request.get_json(silent=True) or {}
    answers = data.get("answers")
    if not isinstance(answers, dict):
        return jsonify({"error": "answers must be an object"}), 400

    conn = get_db()
    conn.execute(
        "INSERT INTO answers (user_id, answers_json, created_at) VALUES (?, ?, ?)",
        (session["user_id"], str(answers), datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()

    session["latest_answers"] = answers
    return jsonify({"status": "success"})


# ------------------------------------------------------------------ pipeline

@app.route("/api/process/start", methods=["POST"])
@login_required
def process_start():
    user_id = session["user_id"]
    device_id = session.get("device_id", DEVICE_NAME)
    answers = session.get("latest_answers", {})

    PROCESSING_STATE[user_id] = {"status": "processing"}
    thread = threading.Thread(target=run_processing_job, args=(user_id, device_id, answers), daemon=True)
    thread.start()
    return jsonify({"status": "processing"})


@app.route("/api/process/status", methods=["GET"])
@login_required
def process_status():
    state = PROCESSING_STATE.get(session["user_id"], {"status": "idle"})
    return jsonify({"status": state.get("status", "idle"), "error": state.get("error")})


@app.route("/api/report", methods=["GET"])
@login_required
def get_report():
    state = PROCESSING_STATE.get(session["user_id"])
    if state and state.get("status") == "done":
        return jsonify(state["report"])

    conn = get_db()
    row = conn.execute(
        "SELECT report_json, created_at FROM reports WHERE user_id = ? ORDER BY id DESC LIMIT 1",
        (session["user_id"],),
    ).fetchone()
    conn.close()

    if not row:
        return jsonify({"error": "No report yet. Run an analysis first."}), 404

    import ast
    report = ast.literal_eval(row["report_json"])
    return jsonify(report)


# --------------------------------------------------------- serve the frontend

@app.route("/")
@app.route("/<path:filename>")
def serve_frontend(filename="index.html"):
    return send_from_directory(FRONTEND_DIR, filename)


if __name__ == "__main__":
    init_db()
    load_trained_model()
    app.run(debug=True, host="0.0.0.0", port=5000)
