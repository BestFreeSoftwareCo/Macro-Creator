import json
from pathlib import Path
from typing import Any


class MacroValidationError(ValueError):
    pass


def _require_str(obj: dict[str, Any], key: str, *, ctx: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise MacroValidationError(f"{ctx}.{key} must be a non-empty string")
    return value


def _require_int(obj: dict[str, Any], key: str, *, ctx: str) -> int:
    value = obj.get(key)
    if value is None:
        raise MacroValidationError(f"{ctx}.{key} is required")
    try:
        return int(value)
    except Exception:
        raise MacroValidationError(f"{ctx}.{key} must be an integer")


def _optional_int(obj: dict[str, Any], key: str, *, ctx: str) -> int | None:
    if key not in obj or obj.get(key) is None:
        return None
    try:
        return int(obj.get(key))
    except Exception:
        raise MacroValidationError(f"{ctx}.{key} must be an integer")


def _optional_float(obj: dict[str, Any], key: str, *, ctx: str) -> float | None:
    if key not in obj or obj.get(key) is None:
        return None
    try:
        return float(obj.get(key))
    except Exception:
        raise MacroValidationError(f"{ctx}.{key} must be a number")


def _validate_actions(actions: Any, *, ctx: str) -> None:
    if not isinstance(actions, list):
        raise MacroValidationError(f"{ctx} must be a list")

    for i, action in enumerate(actions):
        if not isinstance(action, dict):
            raise MacroValidationError(f"{ctx}[{i}] must be an object")

        action_ctx = f"{ctx}[{i}]"
        action_type = _require_str(action, "type", ctx=action_ctx)

        post_action = action.get("post_action")
        if post_action is not None:
            if not isinstance(post_action, dict):
                raise MacroValidationError(f"{action_ctx}.post_action must be an object")
            _validate_actions([post_action], ctx=f"{action_ctx}.post_action")

        if action_type == "click":
            button = action.get("button", "left")
            if not isinstance(button, str) or not button.strip():
                raise MacroValidationError(f"{action_ctx}.button must be a string")
            _optional_int(action, "x", ctx=action_ctx)
            _optional_int(action, "y", ctx=action_ctx)
            continue

        if action_type == "click_at":
            button = action.get("button", "left")
            if not isinstance(button, str) or not button.strip():
                raise MacroValidationError(f"{action_ctx}.button must be a string")
            _require_int(action, "x", ctx=action_ctx)
            _require_int(action, "y", ctx=action_ctx)
            continue

        if action_type in ("key_press", "key_down", "key_up"):
            _require_str(action, "key", ctx=action_ctx)
            continue

        if action_type == "type_text":
            text = action.get("text")
            if not isinstance(text, str):
                raise MacroValidationError(f"{action_ctx}.text must be a string")
            interval_ms = _optional_int(action, "interval_ms", ctx=action_ctx)
            if interval_ms is not None and interval_ms < 0:
                raise MacroValidationError(f"{action_ctx}.interval_ms must be >= 0")
            continue

        if action_type == "hotkey":
            keys = action.get("keys")
            if isinstance(keys, str):
                if not keys.strip():
                    raise MacroValidationError(f"{action_ctx}.keys must be a non-empty string")
            elif isinstance(keys, list):
                if not keys or not all(isinstance(k, str) and k.strip() for k in keys):
                    raise MacroValidationError(f"{action_ctx}.keys must be a list of non-empty strings")
            else:
                raise MacroValidationError(f"{action_ctx}.keys must be a string or list")
            continue

        if action_type == "wait":
            _require_int(action, "duration_ms", ctx=action_ctx)
            continue

        if action_type == "wait_random":
            _require_int(action, "min_ms", ctx=action_ctx)
            _require_int(action, "max_ms", ctx=action_ctx)
            continue

        if action_type in ("mouse_down", "mouse_up"):
            button = action.get("button", "left")
            if not isinstance(button, str) or not button.strip():
                raise MacroValidationError(f"{action_ctx}.button must be a string")
            x = _optional_int(action, "x", ctx=action_ctx)
            y = _optional_int(action, "y", ctx=action_ctx)
            if (x is None) != (y is None):
                raise MacroValidationError(f"{action_ctx}.x and .y must be provided together")
            continue

        if action_type == "move_mouse":
            _require_int(action, "x", ctx=action_ctx)
            _require_int(action, "y", ctx=action_ctx)
            if "duration_ms" in action and action.get("duration_ms") is not None:
                _require_int(action, "duration_ms", ctx=action_ctx)
            continue

        if action_type == "move_mouse_rel":
            _require_int(action, "dx", ctx=action_ctx)
            _require_int(action, "dy", ctx=action_ctx)
            if "duration_ms" in action and action.get("duration_ms") is not None:
                _require_int(action, "duration_ms", ctx=action_ctx)
            continue

        if action_type == "drag_to":
            _require_int(action, "x", ctx=action_ctx)
            _require_int(action, "y", ctx=action_ctx)
            button = action.get("button", "left")
            if not isinstance(button, str) or not button.strip():
                raise MacroValidationError(f"{action_ctx}.button must be a string")
            if "duration_ms" in action and action.get("duration_ms") is not None:
                _require_int(action, "duration_ms", ctx=action_ctx)
            continue

        if action_type == "scroll":
            _require_int(action, "amount", ctx=action_ctx)
            _optional_int(action, "x", ctx=action_ctx)
            _optional_int(action, "y", ctx=action_ctx)
            continue

        if action_type in ("wait_for_image", "click_image"):
            _require_str(action, "value", ctx=action_ctx)

            confidence = _optional_float(action, "confidence", ctx=action_ctx)
            if confidence is not None and not (0.0 <= confidence <= 1.0):
                raise MacroValidationError(f"{action_ctx}.confidence must be between 0 and 1")

            region = action.get("region")
            if region is not None:
                if not (
                    isinstance(region, (list, tuple))
                    and len(region) == 4
                    and all(isinstance(v, (int, float)) for v in region)
                ):
                    raise MacroValidationError(f"{action_ctx}.region must be [x, y, w, h]")

            timeout_ms = _optional_int(action, "timeout_ms", ctx=action_ctx)
            if timeout_ms is not None and timeout_ms < 0:
                raise MacroValidationError(f"{action_ctx}.timeout_ms must be >= 0")

            interval_ms = _optional_int(action, "interval_ms", ctx=action_ctx)
            if interval_ms is not None and interval_ms < 0:
                raise MacroValidationError(f"{action_ctx}.interval_ms must be >= 0")

            if action_type == "click_image":
                button = action.get("button", "left")
                if not isinstance(button, str) or not button.strip():
                    raise MacroValidationError(f"{action_ctx}.button must be a string")

            continue

        if action_type == "if":
            check_type = _require_str(action, "check", ctx=action_ctx)
            if check_type == "image":
                _require_str(action, "value", ctx=action_ctx)
                confidence = _optional_float(action, "confidence", ctx=action_ctx)
                if confidence is not None and not (0.0 <= confidence <= 1.0):
                    raise MacroValidationError(f"{action_ctx}.confidence must be between 0 and 1")

                region = action.get("region")
                if region is not None:
                    if not (
                        isinstance(region, (list, tuple))
                        and len(region) == 4
                        and all(isinstance(v, (int, float)) for v in region)
                    ):
                        raise MacroValidationError(f"{action_ctx}.region must be [x, y, w, h]")

            else:
                raise MacroValidationError(f"{action_ctx}.check unsupported")

            timeout_ms = _optional_int(action, "timeout_ms", ctx=action_ctx)
            if timeout_ms is not None and timeout_ms < 0:
                raise MacroValidationError(f"{action_ctx}.timeout_ms must be >= 0")

            interval_ms = _optional_int(action, "interval_ms", ctx=action_ctx)
            if interval_ms is not None and interval_ms < 0:
                raise MacroValidationError(f"{action_ctx}.interval_ms must be >= 0")

            on_true = action.get("on_true", [])
            on_false = action.get("on_false", [])
            _validate_actions(on_true, ctx=f"{action_ctx}.on_true")
            _validate_actions(on_false, ctx=f"{action_ctx}.on_false")
            continue


def validate_macro(macro: dict[str, Any]) -> None:
    if not isinstance(macro, dict):
        raise MacroValidationError("macro must be an object")

    schema_version = macro.get("schema_version")
    if schema_version != 1:
        raise MacroValidationError("unsupported schema_version")

    name = macro.get("name")
    if not isinstance(name, str) or not name.strip():
        raise MacroValidationError("macro.name must be a non-empty string")

    settings = macro.get("settings")
    if settings is not None and not isinstance(settings, dict):
        raise MacroValidationError("macro.settings must be an object")

    if isinstance(settings, dict):
        if "repeat" in settings and settings.get("repeat") is not None:
            try:
                repeat = int(settings.get("repeat"))
            except Exception:
                raise MacroValidationError("macro.settings.repeat must be an integer")
            if repeat < 0:
                raise MacroValidationError("macro.settings.repeat must be >= 0")

        if "max_steps" in settings and settings.get("max_steps") is not None:
            try:
                max_steps = int(settings.get("max_steps"))
            except Exception:
                raise MacroValidationError("macro.settings.max_steps must be an integer")
            if max_steps < 1:
                raise MacroValidationError("macro.settings.max_steps must be >= 1")

    actions = macro.get("actions")
    _validate_actions(actions, ctx="macro.actions")


def load_macro_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise MacroValidationError("macro JSON must contain an object")
    validate_macro(data)
    return data


def save_macro_json(path: Path, macro: dict[str, Any]) -> None:
    validate_macro(macro)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(macro, indent=2), encoding="utf-8")
