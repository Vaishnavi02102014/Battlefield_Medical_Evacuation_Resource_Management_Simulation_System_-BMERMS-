"""
train_models.py
 
Offline training script for the BMERMS AI module.
 
Trains three independent models from the battlefield casualty dataset:
    1. transfer_model.pkl  -> RandomForestClassifier -> Transfer_Required
    2. recovery_model.pkl  -> RandomForestRegressor   -> Predicted_Recovery_Days
    3. duty_model.pkl      -> RandomForestClassifier  -> Return_to_Duty
 
This module is fully offline, self-contained, and independent of the
simulation engine. It reads the dataset, trains each model in its own
sklearn Pipeline (preprocessing + estimator), evaluates it on a held-out
test split, saves the fitted pipelines with joblib, and writes evaluation
metrics to metrics.json.
"""
 
import json
import os
 
import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
 
# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
 
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE_DIR, "Battlefield_Medical_Evacuation_Synthetic_Dataset.xlsx")
MODELS_DIR = os.path.join(BASE_DIR, "models")
METRICS_PATH = os.path.join(BASE_DIR, "metrics.json")
MODEL_INFO_PATH = os.path.join(BASE_DIR, "model_info.json")
 
RANDOM_STATE = 42
TEST_SIZE = 0.2
 
# --------------------------------------------------------------------------
# Constant column groups
# --------------------------------------------------------------------------
 
DROP_COLUMNS = [
    "Casualty_ID",
    "Incident_ID",
    "Bed_ID",
    "Medical_Officer",
    "Incident_Time",
    "Arrival_Time",
    "Treatment_Start",
    "Treatment_End",
]
 
TARGET_COLUMNS = [
    "Transfer_Required",
    "Predicted_Recovery_Days",
    "Return_to_Duty",
]
 
SEVERITY_ORDER = {"Mild": 0, "Moderate": 1, "Serious": 2, "Critical": 3}
TRIAGE_ORDER = {"P3": 0, "P2": 1, "P1": 2, "P0": 3}
 
ORDINAL_COLUMNS = ["Severity", "Triage_Priority"]
 
 
# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
 
def load_dataset() -> pd.DataFrame:
    df = pd.read_excel(DATA_PATH)
    return df
 
 
def apply_ordinal_encoding(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "Severity" in df.columns:
        df["Severity"] = df["Severity"].map(SEVERITY_ORDER)
    if "Triage_Priority" in df.columns:
        df["Triage_Priority"] = df["Triage_Priority"].map(TRIAGE_ORDER)
    return df
 
 
def build_feature_frame(
    df: pd.DataFrame,
    current_target: str,
    additional_drop_columns: list = None,
) -> pd.DataFrame:
    """Return the feature matrix for a given model: drops non-feature
    identifier/timestamp columns, drops every target column except
    the one currently being predicted (which is removed separately),
    and drops any additional caller-specified leakage columns."""
    other_targets = [t for t in TARGET_COLUMNS if t != current_target]
    columns_to_drop = set(DROP_COLUMNS) | set(other_targets) | {current_target}
 
    if additional_drop_columns:
        columns_to_drop |= set(additional_drop_columns)
 
    features = df.drop(columns=[c for c in columns_to_drop if c in df.columns])
    return features
 
 
def build_preprocessor(features: pd.DataFrame) -> ColumnTransformer:
    """Ordinal columns (already numeric-encoded) pass through unchanged.
    All remaining categorical (object/string) columns are one-hot encoded.
    Numeric columns pass through unchanged."""
    ordinal_present = [c for c in ORDINAL_COLUMNS if c in features.columns]
 
    categorical_columns = [
        c
        for c in features.columns
        if not pd.api.types.is_numeric_dtype(features[c]) and c not in ordinal_present
    ]
 
    preprocessor = ColumnTransformer(
        transformers=[
            ("cat", OneHotEncoder(handle_unknown="ignore"), categorical_columns),
        ],
        remainder="passthrough",
    )
    return preprocessor
 
 
def evaluate_classifier(y_true, y_pred) -> dict:
    return {
        "accuracy": accuracy_score(y_true, y_pred),
        "precision": precision_score(y_true, y_pred, average="weighted", zero_division=0),
        "recall": recall_score(y_true, y_pred, average="weighted", zero_division=0),
        "f1": f1_score(y_true, y_pred, average="weighted", zero_division=0),
    }
 
 
def evaluate_regressor(y_true, y_pred) -> dict:
    mse = mean_squared_error(y_true, y_pred)
    return {
        "mae": mean_absolute_error(y_true, y_pred),
        "rmse": mse ** 0.5,
        "r2": r2_score(y_true, y_pred),
    }
 
 
# --------------------------------------------------------------------------
# Model training routines
# --------------------------------------------------------------------------
 
def train_transfer_model(df: pd.DataFrame) -> dict:
    target = "Transfer_Required"
    X = build_feature_frame(
        df,
        current_target=target,
        additional_drop_columns=[
            "Current_Status",
            "Return_to_Duty",
            "Predicted_Recovery_Days",
        ],
    )
    y = df[target].map({"No": 0, "Yes": 1})
 
    preprocessor = build_preprocessor(X)
    pipeline = Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            (
                "classifier",
                RandomForestClassifier(n_estimators=200, random_state=RANDOM_STATE),
            ),
        ]
    )
 
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, random_state=RANDOM_STATE, stratify=y
    )
 
    pipeline.fit(X_train, y_train)
    y_pred = pipeline.predict(X_test)
 
    metrics = evaluate_classifier(y_test, y_pred)
 
    joblib.dump(pipeline, os.path.join(MODELS_DIR, "transfer_model.pkl"))
    return metrics
 
 
def train_recovery_model(df: pd.DataFrame) -> dict:
    target = "Predicted_Recovery_Days"
    X = build_feature_frame(
        df,
        current_target=target,
        additional_drop_columns=[
            "Current_Status",
            "Transfer_Required",
            "Return_to_Duty",
        ],
    )
    y = df[target]
 
    preprocessor = build_preprocessor(X)
    pipeline = Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            (
                "regressor",
                RandomForestRegressor(n_estimators=200, random_state=RANDOM_STATE),
            ),
        ]
    )
 
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, random_state=RANDOM_STATE
    )
 
    pipeline.fit(X_train, y_train)
    y_pred = pipeline.predict(X_test)
 
    metrics = evaluate_regressor(y_test, y_pred)
 
    joblib.dump(pipeline, os.path.join(MODELS_DIR, "recovery_model.pkl"))
    return metrics
 
 
def train_duty_model(df: pd.DataFrame) -> dict:
    target = "Return_to_Duty"
    X = build_feature_frame(
        df,
        current_target=target,
        additional_drop_columns=[
            "Current_Status",
            "Predicted_Recovery_Days",
        ],
    )
    y = df[target].map({"No": 0, "Yes": 1})
 
    preprocessor = build_preprocessor(X)
    pipeline = Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            (
                "classifier",
                RandomForestClassifier(
                    n_estimators=200,
                    random_state=RANDOM_STATE,
                    class_weight="balanced",
                ),
            ),
        ]
    )
 
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, random_state=RANDOM_STATE, stratify=y
    )
 
    pipeline.fit(X_train, y_train)
    y_pred = pipeline.predict(X_test)
 
    metrics = evaluate_classifier(y_test, y_pred)
 
    joblib.dump(pipeline, os.path.join(MODELS_DIR, "duty_model.pkl"))
    return metrics
 
 
# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
 
def main():
    os.makedirs(MODELS_DIR, exist_ok=True)
    os.makedirs(BASE_DIR, exist_ok=True)
 
    df = load_dataset()
    df = apply_ordinal_encoding(df)
 
    metrics = {
        "transfer_model": train_transfer_model(df),
        "recovery_model": train_recovery_model(df),
        "duty_model": train_duty_model(df),
    }
 
    with open(METRICS_PATH, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, default=float)
 
    model_info = {
        "transfer_model": {
            "target": "Transfer_Required",
            "type": "RandomForestClassifier",
        },
        "recovery_model": {
            "target": "Predicted_Recovery_Days",
            "type": "RandomForestRegressor",
        },
        "duty_model": {
            "target": "Return_to_Duty",
            "type": "RandomForestClassifier",
        },
    }
 
    with open(MODEL_INFO_PATH, "w", encoding="utf-8") as f:
        json.dump(model_info, f, indent=2)
 
    print(json.dumps(metrics, indent=2, default=float))
 
 
if __name__ == "__main__":
    main()
 