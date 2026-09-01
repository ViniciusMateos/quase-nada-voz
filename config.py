from pathlib import Path

from dotenv import dotenv_values, load_dotenv, set_key

BASE_DIR = Path(__file__).parent
ENV_PATH = BASE_DIR / ".env"

DEFAULTS = {
    "OPENAI_EMAIL": "",
    "OPENAI_PASSWORD": "",
    "OAI_DEVICE_ID": "4735a0c5-377b-45d6-b480-85bdaf63d5d6",
    "HOTKEY": "F9",
    "AUDIO_DEVICE": "",
}


def load_config():
    if not ENV_PATH.exists():
        ENV_PATH.write_text("", encoding="utf-8")
    values = dotenv_values(ENV_PATH)
    return {key: values.get(key) or default for key, default in DEFAULTS.items()}


def save_config(values):
    if not ENV_PATH.exists():
        ENV_PATH.write_text("", encoding="utf-8")
    for key in DEFAULTS:
        if key in values:
            set_key(str(ENV_PATH), key, values[key] or "", quote_mode="never")
    load_dotenv(ENV_PATH, override=True)
