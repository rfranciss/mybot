import json
from pathlib import Path

SETTINGS_PATH = Path("settings.json")

DEFAULTS = {
    "entry": 2.0,
    "stop_win": 20.0,
    "stop_loss": -15.0,
    "profile": "Moderado",
    "timeframe": "1 Minuto",
    "pairs": ["EURUSD-OTC", "GBPUSD-OTC", "USDJPY-OTC"],
    "account_mode": "PRACTICE",
}


def load_settings():
    if not SETTINGS_PATH.exists():
        return DEFAULTS.copy()
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        merged = DEFAULTS.copy()
        merged.update(data if isinstance(data, dict) else {})
        return merged
    except Exception:
        return DEFAULTS.copy()


def save_settings(settings: dict):
    try:
        SETTINGS_PATH.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False
