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
