"""
model_loader.py
 
Lazy, cached loading utilities for the BMERMS AI module artifacts:
    - transfer_model.pkl
    - recovery_model.pkl
    - duty_model.pkl
    - metrics.json
    - model_info.json
 
Each loader function is decorated with functools.lru_cache so the
underlying file is only read from disk once per process; subsequent
calls return the cached in-memory object.
"""
 
import json
from functools import lru_cache
from pathlib import Path
 
import joblib
 
BASE_DIR = Path(__file__).resolve().parent
MODELS_DIR = BASE_DIR / "models"
 
TRANSFER_MODEL_PATH = MODELS_DIR / "transfer_model.pkl"
RECOVERY_MODEL_PATH = MODELS_DIR / "recovery_model.pkl"
DUTY_MODEL_PATH = MODELS_DIR / "duty_model.pkl"
METRICS_PATH = BASE_DIR / "metrics.json"
MODEL_INFO_PATH = BASE_DIR / "model_info.json"
 
 
def _load_joblib(path: Path):
    if not path.exists():
        raise FileNotFoundError(
            f"Model file not found: {path}. Run train_models.py to generate it."
        )
    return joblib.load(path)
 
 
def _load_json(path: Path):
    if not path.exists():
        raise FileNotFoundError(
            f"Required file not found: {path}. Run train_models.py to generate it."
        )
    with open(path, "r") as f:
        return json.load(f)
 
 
@lru_cache(maxsize=1)
def load_transfer_model():
    return _load_joblib(TRANSFER_MODEL_PATH)
 
 
@lru_cache(maxsize=1)
def load_recovery_model():
    return _load_joblib(RECOVERY_MODEL_PATH)
 
 
@lru_cache(maxsize=1)
def load_duty_model():
    return _load_joblib(DUTY_MODEL_PATH)
 
 
@lru_cache(maxsize=1)
def load_metrics():
    return _load_json(METRICS_PATH)
 
 
@lru_cache(maxsize=1)
def load_model_info():
    return _load_json(MODEL_INFO_PATH)