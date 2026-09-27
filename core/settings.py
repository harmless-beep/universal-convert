"""Settings: shipped defaults + per-user overrides.

Precedence:  config/settings.json (shipped, read-only)
          -> user config dir     (writable, remembers last_used + changes)

User config locations:
  Windows:  %APPDATA%\\UniversalConvert\\settings.json
  macOS:    ~/Library/Application Support/UniversalConvert/settings.json
  Linux:    $XDG_CONFIG_HOME/universal-convert/settings.json (default ~/.config/...)

Only *modified* keys are written to the user file, so new shipped defaults
keep working after upgrades. All reads are defensive: a corrupt user config
falls back to defaults instead of crashing the menu entry.
"""

from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path
from typing import Any

from .errors import PROJECT_ROOT, get_logger

DEFAULTS_FILE = PROJECT_ROOT / "config" / "settings.json"


def user_config_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "UniversalConvert"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "UniversalConvert"
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "universal-convert"


USER_CONFIG_FILE = user_config_dir() / "settings.json"


def _read_json(path: Path) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data
        get_logger().warning("Config %s is not a JSON object; ignoring", path)
    except FileNotFoundError:
        pass
    except (json.JSONDecodeError, OSError) as exc:
        get_logger().warning("Could not read config %s (%s); using defaults", path, exc)
    return {}


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if key in out and isinstance(out[key], dict) and isinstance(value, dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


class Settings:
    def __init__(self, data: dict):
        self.data = data

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, dotted: str, value: Any) -> None:
        parts = dotted.split(".")
        node = self.data
        for part in parts[:-1]:
            node = node.setdefault(part, {})
            if not isinstance(node, dict):
                raise ValueError(f"Cannot set {dotted}: {part} is not an object")
        node[parts[-1]] = value

    def remember_last(self, action: str, options: dict) -> None:
        """Persist the options used for an action so the dialog pre-fills next time."""
        clean = {
            k: v for k, v in options.items() if isinstance(v, (str, int, float, bool))
        }
        self.data.setdefault("last_used", {})[action] = clean

    def last_for(self, action: str) -> dict:
        value = self.get(f"last_used.{action}")
        return value if isinstance(value, dict) else {}

    def save(self) -> None:
        try:
            USER_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(USER_CONFIG_FILE, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh, indent=2, sort_keys=False)
                fh.write("\n")
        except OSError as exc:
            get_logger().warning("Could not save settings to %s: %s", USER_CONFIG_FILE, exc)


def load_settings() -> Settings:
    defaults = _read_json(DEFAULTS_FILE)
    if not defaults:
        # Shipped defaults missing/corrupt: hard minimal fallback so the tool still runs.
        defaults = {
            "output": {
                "folder_mode": "subfolder",
                "subfolder_name": "Converted",
                "open_when_done": True,
                "notify": True,
            },
            "aggregation": {"debounce_ms": 500, "max_wait_ms": 1500},
            "presets": {"thumbnail": 256, "email": 1024, "web": 1920, "print": "A4@300"},
            "last_used": {},
        }
    user = _read_json(USER_CONFIG_FILE)
    merged = _deep_merge(defaults, user)
    if not user:
        # First run: seed the user config so later edits persist.
        return Settings(merged)  # saved lazily on first change
    return Settings(merged)
