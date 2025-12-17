import random
import time
from typing import Any, Callable

import pyautogui


class ActionRunner:
    def __init__(self, min_sleep_s: float = 0.005) -> None:
        self._min_sleep_s = float(min_sleep_s)

    def run_action(self, action: dict[str, Any], log: Callable[[str], None]) -> None:
        action_type = action.get("type")

        if action_type == "click":
            button = str(action.get("button", "left"))
            x = action.get("x")
            y = action.get("y")
            if x is None or y is None:
                pyautogui.click(button=button)
            else:
                pyautogui.click(x=int(x), y=int(y), button=button)
            log(f"click button={button}")
            self._sleep_min()
            return

        if action_type == "click_at":
            button = str(action.get("button", "left"))
            x = action.get("x")
            y = action.get("y")
            if x is None or y is None:
                raise ValueError("click_at action missing 'x'/'y'")
            pyautogui.click(x=int(x), y=int(y), button=button)
            log(f"click_at x={int(x)} y={int(y)} button={button}")
            self._sleep_min()
            return

        if action_type == "key_press":
            key = str(action.get("key", ""))
            if not key:
                raise ValueError("key_press action missing 'key'")
            pyautogui.press(key)
            log(f"key_press key={key}")
            self._sleep_min()
            return

        if action_type == "key_down":
            key = str(action.get("key", ""))
            if not key:
                raise ValueError("key_down action missing 'key'")
            pyautogui.keyDown(key)
            log(f"key_down key={key}")
            self._sleep_min()
            return

        if action_type == "key_up":
            key = str(action.get("key", ""))
            if not key:
                raise ValueError("key_up action missing 'key'")
            pyautogui.keyUp(key)
            log(f"key_up key={key}")
            self._sleep_min()
            return

        if action_type == "type_text":
            text = action.get("text")
            if text is None:
                raise ValueError("type_text action missing 'text'")
            text_s = str(text)

            interval_ms = action.get("interval_ms", 0)
            try:
                interval_s = max(0.0, float(interval_ms) / 1000.0)
            except Exception:
                interval_s = 0.0

            pyautogui.write(text_s, interval=interval_s)
            log(f"type_text len={len(text_s)} interval_ms={int(round(interval_s * 1000.0))}")
            self._sleep_min()
            return

        if action_type == "hotkey":
            keys_raw = action.get("keys")
            keys: list[str]
            if isinstance(keys_raw, str):
                keys = [k.strip() for k in keys_raw.replace(",", "+").split("+") if k.strip()]
            elif isinstance(keys_raw, list):
                keys = [str(k).strip() for k in keys_raw if str(k).strip()]
            else:
                raise ValueError("hotkey action missing 'keys'")

            if not keys:
                raise ValueError("hotkey action requires at least one key")

            pyautogui.hotkey(*keys)
            log(f"hotkey keys={'+'.join(keys)}")
            self._sleep_min()
            return

        if action_type == "mouse_down":
            button = str(action.get("button", "left"))
            x = action.get("x")
            y = action.get("y")
            if x is None or y is None:
                pyautogui.mouseDown(button=button)
                log(f"mouse_down button={button}")
            else:
                pyautogui.mouseDown(x=int(x), y=int(y), button=button)
                log(f"mouse_down x={int(x)} y={int(y)} button={button}")
            self._sleep_min()
            return

        if action_type == "mouse_up":
            button = str(action.get("button", "left"))
            x = action.get("x")
            y = action.get("y")
            if x is None or y is None:
                pyautogui.mouseUp(button=button)
                log(f"mouse_up button={button}")
            else:
                pyautogui.mouseUp(x=int(x), y=int(y), button=button)
                log(f"mouse_up x={int(x)} y={int(y)} button={button}")
            self._sleep_min()
            return

        if action_type == "wait":
            duration_ms = action.get("duration_ms")
            if duration_ms is None:
                raise ValueError("wait action missing 'duration_ms'")
            duration_s = max(0.0, float(duration_ms) / 1000.0)
            log(f"wait {int(duration_ms)}ms")
            time.sleep(duration_s)
            self._sleep_min()
            return

        if action_type == "wait_random":
            min_ms = action.get("min_ms")
            max_ms = action.get("max_ms")
            if min_ms is None or max_ms is None:
                raise ValueError("wait_random action missing 'min_ms'/'max_ms'")
            min_ms_i = int(min_ms)
            max_ms_i = int(max_ms)
            if max_ms_i < min_ms_i:
                min_ms_i, max_ms_i = max_ms_i, min_ms_i
            duration_ms = random.randint(max(0, min_ms_i), max(0, max_ms_i))
            log(f"wait_random {duration_ms}ms")
            time.sleep(float(duration_ms) / 1000.0)
            self._sleep_min()
            return

        if action_type == "move_mouse":
            x = action.get("x")
            y = action.get("y")
            if x is None or y is None:
                raise ValueError("move_mouse action missing 'x'/'y'")
            duration_ms = action.get("duration_ms", 0)
            duration_s = max(0.0, float(duration_ms) / 1000.0)
            pyautogui.moveTo(x=int(x), y=int(y), duration=duration_s)
            log(f"move_mouse x={int(x)} y={int(y)} duration_ms={int(duration_ms)}")
            self._sleep_min()
            return

        if action_type == "move_mouse_rel":
            dx = action.get("dx")
            dy = action.get("dy")
            if dx is None or dy is None:
                raise ValueError("move_mouse_rel action missing 'dx'/'dy'")
            duration_ms = action.get("duration_ms", 0)
            duration_s = max(0.0, float(duration_ms) / 1000.0)
            pyautogui.moveRel(xOffset=int(dx), yOffset=int(dy), duration=duration_s)
            log(f"move_mouse_rel dx={int(dx)} dy={int(dy)} duration_ms={int(duration_ms)}")
            self._sleep_min()
            return

        if action_type == "drag_to":
            x = action.get("x")
            y = action.get("y")
            if x is None or y is None:
                raise ValueError("drag_to action missing 'x'/'y'")

            button = str(action.get("button", "left"))
            duration_ms = action.get("duration_ms", 0)
            duration_s = max(0.0, float(duration_ms) / 1000.0)

            pyautogui.dragTo(x=int(x), y=int(y), duration=duration_s, button=button)
            log(f"drag_to x={int(x)} y={int(y)} button={button} duration_ms={int(duration_ms)}")
            self._sleep_min()
            return

        if action_type == "scroll":
            amount = action.get("amount")
            if amount is None:
                raise ValueError("scroll action missing 'amount'")
            x = action.get("x")
            y = action.get("y")
            if x is None or y is None:
                pyautogui.scroll(int(amount))
                log(f"scroll amount={int(amount)}")
            else:
                pyautogui.scroll(int(amount), x=int(x), y=int(y))
                log(f"scroll amount={int(amount)} x={int(x)} y={int(y)}")
            self._sleep_min()
            return

        raise ValueError(f"Unknown action type: {action_type!r}")

    def _sleep_min(self) -> None:
        if self._min_sleep_s > 0:
            time.sleep(self._min_sleep_s)
