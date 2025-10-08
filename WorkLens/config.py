import json
import os
import sys
from dataclasses import dataclass, asdict
from typing import Any, Dict


def get_user_config_dir() -> str:
    # Prefer %APPDATA% on Windows; fallback to home directory
    base = os.getenv('APPDATA') or os.path.expanduser('~')
    path = os.path.join(base, 'WorkLens')
    os.makedirs(path, exist_ok=True)
    return path


def get_env_path() -> str:
    return os.path.join(get_user_config_dir(), '.env')


def get_config_path() -> str:
    return os.path.join(get_user_config_dir(), 'config.json')


@dataclass
class AppConfig:
    planned_task: str = ""
    interval_minutes: int = 10
    image_width: int = 1280
    api_key_env: str = "OPENAI_API_KEY"
    profession: str = ""


DEFAULT_CONFIG = AppConfig()


def _load_env_file(path: str | None = None) -> None:
    env_path = path or get_env_path()
    if not os.path.exists(env_path):
        return
    try:
        with open(env_path, 'r', encoding='utf-8') as f:
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
    repo_env = os.path.join(os.path.dirname(__file__), '.env')
    _load_env_file(repo_env)
    cfg_path = get_config_path()
    if not os.path.exists(cfg_path):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG
    try:
        with open(cfg_path, 'r', encoding='utf-8') as f:
            data: Dict[str, Any] = json.load(f)
        return AppConfig(**{**asdict(DEFAULT_CONFIG), **data})
    except Exception:
        return DEFAULT_CONFIG


def save_config(config: AppConfig) -> None:
    try:
        with open(get_config_path(), 'w', encoding='utf-8') as f:
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


def persist_api_key(api_key: str, env_name: str = 'OPENAI_API_KEY') -> None:
    """Persist API key to the user config .env and set environment variable for current process."""
    if not api_key:
        return
    try:
        env_path = get_env_path()
        os.makedirs(os.path.dirname(env_path), exist_ok=True)
        # Merge with existing env file if present
        existing: Dict[str, str] = {}
        if os.path.exists(env_path):
            try:
                with open(env_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#') or '=' not in line:
                            continue
                        k, v = line.split('=', 1)
                        existing[k.strip()] = v.strip()
            except Exception:
                existing = {}
        existing[env_name] = api_key
        with open(env_path, 'w', encoding='utf-8') as f:
            for k, v in existing.items():
                f.write(f"{k}={v}\n")
        os.environ[env_name] = api_key
    except Exception:
        # Best effort; do not crash UI
        pass
