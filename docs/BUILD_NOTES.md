# HerPulse — Part 1 + real trained model

Website ↔ Flask backend ↔ Arduino board, with the full user journey:
splash → login → connect device → questionnaire → processing → report.

The Random Forest models are **already trained** on
`backend/data/Integrated_Menstrual_Biomarker_Dataset_300_Samples.xlsx`
and saved to `backend/models/herpulse_models.joblib`. `app.py` loads that
bundle on startup and uses it for real predictions — no more placeholder
thresholds, unless the bundle is missing, in which case it falls back
automatically so the app never breaks.

## Run it

```bash
cd backend
pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:5000/** — Flask serves the frontend directly.

**Demo login:** `demo` / `herpulse123` (seeded automatically on first run).
To create your own: `python create_user.py <username> <password>`.

**Device connect screen:** device name `HerPulse_Q`, device password `Herpulse123`
(both configurable via `HERPULSE_DEVICE_NAME` / `HERPULSE_DEVICE_PASSWORD` env vars).

## What's in each part

```
frontend/
  index.html          splash screen — logo entrance animation, auto-advances
  login.html            username + password, show/hide toggle
  connect.html           device name + password, Wi-Fi status, Connect button
  questionnaire.html     the 10 questions, one per screen, progress bar
  processing.html        animated pulse loader + step ticker while the model runs
  report.html             Hb / protein / pH results with risk levels + diagnosis banner
  css/style.css           design tokens (color, type, motion) + all component styles
  js/api.js                one shared fetch client every page uses
  assets/logo.png          your team logo

backend/
  app.py                 Flask app: auth, device connect, questionnaire,
                          model inference, report, Arduino ingest
  train_model.py          trains the 3 Random Forests + builds the diagnosis lookup
  requirements.txt        runtime deps (Flask + friends)
  requirements-train.txt  training-only deps (scikit-learn, pandas, openpyxl)
  data/
    Integrated_Menstrual_Biomarker_Dataset_300_Samples.xlsx   your labeled dataset
  models/
    herpulse_models.joblib   the trained bundle app.py loads automatically
  arduino_example/
    herpulse_wifi_post.ino   sample sketch: board -> Wi-Fi -> /api/device/data
```

## How the model actually works

Your dataset has, for each of Hb / Protein / pH, a raw sensor triplet
(`R_Hb, G_Hb, B_Hb`, etc.) plus the real lab value and a risk label
(`Label_Hb` = Normal/Low/Critical, `Label_Protein` = Normal/Abnormal,
`Label_pH` = Normal/Elevated/Infection). The RGB values turned out to
correlate ~0.99 with the lab values, so `train_model.py` trains, per
biomarker, **two** Random Forests off the same 3 RGB features:

- a **regressor** → predicts the actual value (e.g. "6.0 g/dL")
- a **classifier** → predicts the risk label (Normal/Low/Critical, etc.)

`Suggested_Health_Issue` turned out to be **fully deterministic** from
the 3 labels together (18 unique combos in your 300 rows, zero
conflicts), so instead of training a weaker 4th model on top of the
other three's predictions, `train_model.py` just saves that combination
as an exact lookup table. `app.py` uses it to attach the real diagnosis
text (e.g. *"Possible severe iron-deficiency anemia / heavy menstrual
bleeding"*) straight from your dataset's own language.

Verified against the dataset's own S0001 row (Hb=6/Critical,
Protein=2.0/Normal, pH=5.5/Elevated) — the live API reproduced the exact
values, risk levels, and diagnosis text.

**Retraining on new/updated data:**
```bash
pip install -r requirements-train.txt
python train_model.py data/Integrated_Menstrual_Biomarker_Dataset_300_Samples.xlsx
```
Restart `app.py` afterward to pick up the new bundle.

## How data actually flows

```
Arduino board  --POST /api/device/data (Wi-Fi, X-Device-Key header)-->  Flask
                    {device_id, r_hb, g_hb, b_hb, r_protein, ..., r_ph, g_ph, b_ph}
Website        --fetch() with session cookie-->                        Flask
Flask          --SQLite (herpulse.db): stores raw readings-->          storage
Flask          --Random Forest inference-->                            predictions
Flask          --JSON (metrics + risk + diagnosis)-->                  Website (report.html)
```

Auth and questionnaire progress live in the **Flask session cookie** — no
`localStorage`/`sessionStorage`, so nothing goes stale in the browser
between visits.

**Real-time calibration note:** the Arduino must send raw R/G/B values
from the *same sensor setup, same lighting/conditions* the training data
was captured under — the model only knows the relationship it was shown.
If your real sensor's raw range differs a lot from the dataset's (e.g.
different ambient light), retrain on a few real calibration samples
before trusting it for a demo.

## API quick reference

| Route | Method | Purpose |
|---|---|---|
| `/api/login` | POST | `{username, password}` → sets session |
| `/api/logout` | POST | clears session |
| `/api/me` | GET | current user (used to guard pages) |
| `/api/device/connect` | POST | `{device_id, device_password}` → handshake, returns IP |
| `/api/device/status` | GET | current device connection state |
| `/api/device/data` | POST | **Arduino calls this** — `X-Device-Key` header + `{device_id, r_hb, g_hb, b_hb, r_protein, g_protein, b_protein, r_ph, g_ph, b_ph}` |
| `/api/questions` | GET | the 10 questionnaire items |
| `/api/submit-answers` | POST | `{answers: {...}}` |
| `/api/process/start` | POST | runs the model against the latest reading in a background thread |
| `/api/process/status` | GET | `processing` / `done` / `error` — `processing.html` polls this |
| `/api/report` | GET | metrics (value + risk level) + diagnosis + suggestions |

## Report shape

```json
{
  "metrics": [
    {"label": "Hemoglobin (Hb)", "value": 6.0, "unit": " g/dL",
     "risk": "high", "risk_label": "High risk", "model_label": "Critical"},
    ...
  ],
  "overall_risk": "high",
  "see_doctor": true,
  "doctor_note": "Possible severe iron-deficiency anemia / heavy menstrual bleeding",
  "suggestions": ["Possible severe iron-deficiency anemia / heavy menstrual bleeding"]
}
```
`report.html` shows a red banner whenever `see_doctor` is true.

## Still to do

1. Wire the real pad sensor into the Arduino sketch (`arduino_example/herpulse_wifi_post.ino`)
   in place of the placeholder R/G/B values.
2. Collect a handful of real calibration samples once the hardware is
   ready, and consider blending them into the training set.
3. Add a `/api/history` route + wire up the "History" button already
   sitting on `report.html`.
4. Swap the dev server for a real WSGI server (gunicorn) before demo day.
