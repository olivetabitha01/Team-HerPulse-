"""
HerPulse — train on Integrated_Menstrual_Biomarker_Dataset_300_Samples.xlsx

Dataset shape confirmed on the actual file:
  Sample_ID, Flow_Type,
  Hb_actual_g_dL, Protein_actual_g_dL, pH_actual,
  R_Hb, G_Hb, B_Hb, Hb_Ratio, Label_Hb,
  R_Protein, G_Protein, B_Protein, Protein_Ratio, Label_Protein,
  R_pH, G_pH, B_pH, pH_Ratio, Label_pH,
  Suggested_Health_Issue

For each biomarker (Hb, Protein, pH) we train two models off the same
3 raw RGB features (Ratio is derived, not sent by the device — see
compute_ratio() in app.py, which mirrors G / (R+G+B) confirmed against
this dataset):

  - a RandomForestRegressor  -> predicts the actual lab value (e.g. "11.2 g/dL")
  - a RandomForestClassifier -> predicts the risk label (Normal/Low/Critical, etc.)

Suggested_Health_Issue is NOT modeled — it's a deterministic lookup off
the 3 label columns (verified: 18 unique label combos in this dataset,
zero conflicts), so we just save that lookup table instead of training
a 4th, weaker model on top of the other three's predictions.

Run:
    pip install -r requirements-train.txt
    python train_model.py data/Integrated_Menstrual_Biomarker_Dataset_300_Samples.xlsx
"""

import sys
import os
import joblib
import pandas as pd
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, accuracy_score

BIOMARKERS = {
    "hb":      {"rgb": ["R_Hb", "G_Hb", "B_Hb"],           "actual": "Hb_actual_g_dL",      "label": "Label_Hb"},
    "protein": {"rgb": ["R_Protein", "G_Protein", "B_Protein"], "actual": "Protein_actual_g_dL", "label": "Label_Protein"},
    "ph":      {"rgb": ["R_pH", "G_pH", "B_pH"],            "actual": "pH_actual",           "label": "Label_pH"},
}


def load_dataset(path):
    if path.endswith(".xlsx"):
        return pd.read_excel(path)
    return pd.read_csv(path)


def main(data_path):
    df = load_dataset(data_path)
    print(f"Loaded {len(df)} samples from {data_path}")

    bundle = {"biomarkers": {}}

    for name, cfg in BIOMARKERS.items():
        X = df[cfg["rgb"]]

        # --- regressor: predicts the real lab value ---
        y_val = df[cfg["actual"]]
        X_train, X_test, y_train, y_test = train_test_split(X, y_val, test_size=0.2, random_state=42)
        reg = RandomForestRegressor(n_estimators=200, random_state=42)
        reg.fit(X_train, y_train)
        mae = mean_absolute_error(y_test, reg.predict(X_test))
        print(f"[{name}] value regressor  — MAE on held-out test set: {mae:.3f}")

        # --- classifier: predicts the risk label ---
        y_label = df[cfg["label"]]
        X_train, X_test, y_train, y_test = train_test_split(X, y_label, test_size=0.2, random_state=42, stratify=y_label)
        clf = RandomForestClassifier(n_estimators=200, random_state=42)
        clf.fit(X_train, y_train)
        acc = accuracy_score(y_test, clf.predict(X_test))
        print(f"[{name}] risk classifier   — accuracy on held-out test set: {acc:.1%}")

        bundle["biomarkers"][name] = {
            "rgb_columns": cfg["rgb"],
            "value_model": reg,
            "label_model": clf,
        }

    # --- deterministic Suggested_Health_Issue lookup ---
    lookup_df = df.groupby(["Label_Hb", "Label_Protein", "Label_pH"])["Suggested_Health_Issue"].agg(lambda x: x.mode()[0])
    conflict_count = df.groupby(["Label_Hb", "Label_Protein", "Label_pH"])["Suggested_Health_Issue"].nunique()
    conflicts = (conflict_count > 1).sum()
    if conflicts:
        print(f"WARNING: {conflicts} label combos had more than one Suggested_Health_Issue in the data — "
              "using the most common one for those. Re-check the dataset if this number is large.")
    issue_lookup = {k: v for k, v in lookup_df.items()}
    bundle["issue_lookup"] = issue_lookup
    print(f"Built a {len(issue_lookup)}-entry health-issue lookup table from the labeled data.")

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "herpulse_models.joblib")
    joblib.dump(bundle, out_path)

    print(f"\nSaved trained models to {out_path}")
    print("Restart app.py — it loads this automatically and switches from placeholder logic to real predictions.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python train_model.py path/to/dataset.xlsx")
        sys.exit(1)
    main(sys.argv[1])
