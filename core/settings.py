import json
from dataclasses import dataclass
from pathlib import Path

from PyMacroStudio.core.paths import project_root


@dataclass(frozen=True)
class AppSettings:
    default_start_stop_hotkey: str
    default_stop_hotkey: str
    max_steps: int
    tos_accepted: bool
    discord_prompt_dismissed: bool


def load_settings() -> AppSettings:
    defaults = AppSettings(
        default_start_stop_hotkey="F6",
        default_stop_hotkey="ESC",
        max_steps=50000,
        tos_accepted=False,
        discord_prompt_dismissed=False,
    )

    path = project_root() / "config" / "settings.json"
    if not path.exists():
        return defaults

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return defaults

    if not isinstance(data, dict):
        return defaults

    start_stop = str(data.get("default_start_stop_hotkey", defaults.default_start_stop_hotkey)).strip() or defaults.default_start_stop_hotkey
    stop_key = str(data.get("default_stop_hotkey", defaults.default_stop_hotkey)).strip() or defaults.default_stop_hotkey

    try:
        max_steps = int(data.get("max_steps", defaults.max_steps))
    except Exception:
        max_steps = defaults.max_steps
    max_steps = max(1, max_steps)

    tos_accepted = bool(data.get("tos_accepted", defaults.tos_accepted))
    discord_prompt_dismissed = bool(data.get("discord_prompt_dismissed", defaults.discord_prompt_dismissed))

    return AppSettings(
        default_start_stop_hotkey=start_stop,
        default_stop_hotkey=stop_key,
        max_steps=max_steps,
        tos_accepted=tos_accepted,
        discord_prompt_dismissed=discord_prompt_dismissed,
    )


def save_settings(settings: AppSettings) -> None:
    path = project_root() / "config" / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "schema_version": 1,
        "default_start_stop_hotkey": settings.default_start_stop_hotkey,
        "default_stop_hotkey": settings.default_stop_hotkey,
        "max_steps": int(settings.max_steps),
        "tos_accepted": bool(settings.tos_accepted),
        "discord_prompt_dismissed": bool(settings.discord_prompt_dismissed),
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
