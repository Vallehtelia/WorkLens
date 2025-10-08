import json
import os
from dataclasses import dataclass, asdict
from typing import Any, Dict

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.json')
ENV_PATH = os.path.join(os.path.dirname(__file__), '.env')


@dataclass
class AppConfig:
    planned_task: str = ""
    interval_minutes: int = 10
    image_width: int = 1280
    api_key_env: str = "OPENAI_API_KEY"
    profession: str = ""


DEFAULT_CONFIG = AppConfig()


def _load_env_file(path: str = ENV_PATH) -> None:
    if not os.path.exists(path):
        return
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    os.environ.setdefault(key, value)
    except Exception:
        # Silently ignore .env issues; app can still run
        pass


def load_config() -> AppConfig:
    _load_env_file()
    if not os.path.exists(CONFIG_PATH):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            data: Dict[str, Any] = json.load(f)
        return AppConfig(**{**asdict(DEFAULT_CONFIG), **data})
    except Exception:
        return DEFAULT_CONFIG


def save_config(config: AppConfig) -> None:
    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(asdict(config), f, indent=2)
    except Exception:
        # Avoid crashing on save failure
        pass


def get_api_key(config: AppConfig) -> str:
    # Prefer environment variable from config.api_key_env
    if config and config.api_key_env:
        env_val = os.environ.get(config.api_key_env)
        if env_val:
            return env_val
    # Fallback to OPENAI_API_KEY
    return os.environ.get('OPENAI_API_KEY', '')
