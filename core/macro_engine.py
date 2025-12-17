from collections import deque
import threading
import time
from typing import Any

import pyautogui

from PyMacroStudio.core.action_runner import ActionRunner
from PyMacroStudio.core.condition_checker import find_image_center, image_found, parse_image_check
from PyMacroStudio.core.safety import configure_safety


class MacroEngine:
    def __init__(self) -> None:
        self._log_lock = threading.Lock()
        self._log_seq = 0
        self._log_buffer: deque[tuple[int, str]] = deque(maxlen=2000)
        self._runner = ActionRunner()

        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()

        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        t = self._thread
        return t is not None and t.is_alive()

    @property
    def is_paused(self) -> bool:
        return self.is_running and not self._pause_event.is_set()

    def start(self, macro: dict[str, Any]) -> None:
        with self._lock:
            if self.is_running:
                self._log("engine already running")
                return

            self._stop_event.clear()
            self._pause_event.set()

            self._thread = threading.Thread(target=self._run_macro, args=(macro,), daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._pause_event.set()

    def pause(self) -> None:
        if self.is_running:
            self._pause_event.clear()
            self._log("paused")

    def resume(self) -> None:
        if self.is_running:
            self._pause_event.set()
            self._log("resumed")

    def shutdown(self, timeout_s: float = 2.0) -> None:
        self.stop()
        t = self._thread
        if t is not None:
            t.join(timeout=timeout_s)
        with self._lock:
            if self._thread is t:
                self._thread = None

    def read_logs(self, since: int = 0) -> tuple[int, list[str]]:
        with self._log_lock:
            if since <= 0:
                messages = [m for _i, m in self._log_buffer]
            else:
                messages = [m for i, m in self._log_buffer if i > since]
            last = self._log_seq
        return last, messages

    def _run_macro(self, macro: dict[str, Any]) -> None:
        configure_safety()
        self._log("macro started")

        started_at = time.time()

        try:
            settings = macro.get("settings") or {}
            try:
                repeat = int(settings.get("repeat", 1))
            except Exception:
                repeat = 1

            actions = macro.get("actions") or []
            if not isinstance(actions, list):
                self._log("invalid macro: actions must be a list")
                return

            try:
                max_steps = int(settings.get("max_steps", 50000))
            except Exception:
                max_steps = 50000
            max_steps = max(1, max_steps)

            steps = 0
            if repeat <= 0:
                rep = 0
                self._log("repeat infinite")
                while not self._stop_event.is_set():
                    rep += 1
                    self._log(f"repeat {rep}/∞")
                    steps = self._execute_actions(actions, steps=steps, max_steps=max_steps)
                    if steps >= max_steps:
                        break
            else:
                repeat = max(1, repeat)
                for rep in range(repeat):
                    self._log(f"repeat {rep + 1}/{repeat}")
                    steps = self._execute_actions(actions, steps=steps, max_steps=max_steps)

        except pyautogui.FailSafeException:
            self._log("failsafe triggered; stopping")
        except Exception as e:
            self._log(f"error: {type(e).__name__}: {e}")
        finally:
            duration = time.time() - started_at
            self._log(f"macro finished in {duration:.2f}s")
            with self._lock:
                if self._thread is threading.current_thread():
                    self._thread = None

    def _execute_actions(self, actions: list[Any], *, steps: int, max_steps: int) -> int:
        for action in actions:
            if self._stop_event.is_set():
                self._log("stop requested")
                return steps

            self._pause_event.wait()

            if self._stop_event.is_set():
                self._log("stop requested")
                return steps

            if steps >= max_steps:
                self._log("max_steps reached; stopping")
                return steps

            if not isinstance(action, dict):
                raise ValueError("action must be an object")

            steps = self._execute_one_action(action, steps=steps, max_steps=max_steps)

        return steps

    def _execute_one_action(self, action: dict[str, Any], *, steps: int, max_steps: int) -> int:
        action_type = action.get("type")
        if action_type == "if":
            steps += 1
            steps = self._execute_if(action, steps=steps, max_steps=max_steps)
        elif action_type == "wait_for_image":
            steps += 1
            self._execute_wait_for_image(action)
        elif action_type == "click_image":
            steps += 1
            self._execute_click_image(action)
        else:
            self._runner.run_action(action, self._log)
            steps += 1

        post_action = action.get("post_action")
        if post_action is not None:
            if self._stop_event.is_set():
                self._log("stop requested")
                return steps

            self._pause_event.wait()

            if self._stop_event.is_set():
                self._log("stop requested")
                return steps

            if steps >= max_steps:
                self._log("max_steps reached; stopping")
                return steps

            if not isinstance(post_action, dict):
                raise ValueError("post_action must be an object")

            self._log("post_action")
            steps = self._execute_one_action(post_action, steps=steps, max_steps=max_steps)

        return steps

    def _execute_wait_for_image(self, action: dict[str, Any]) -> None:
        timeout_ms = action.get("timeout_ms", 0)
        interval_ms = action.get("interval_ms", 200)

        try:
            timeout_s = max(0.0, float(timeout_ms) / 1000.0)
        except Exception:
            timeout_s = 0.0

        try:
            interval_s = max(0.01, float(interval_ms) / 1000.0)
        except Exception:
            interval_s = 0.2

        check = parse_image_check(action)
        self._log(f"wait_for_image value={check.value}")

        start = time.time()
        while True:
            if self._stop_event.is_set():
                self._log("stop requested")
                return

            self._pause_event.wait()

            matched = image_found(check)
            if matched:
                self._log("wait_for_image found")
                return

            if timeout_s > 0 and (time.time() - start) >= timeout_s:
                break

            time.sleep(interval_s)

        self._log("wait_for_image not found")

    def _execute_click_image(self, action: dict[str, Any]) -> None:
        timeout_ms = action.get("timeout_ms", 0)
        interval_ms = action.get("interval_ms", 200)
        button = str(action.get("button", "left"))

        try:
            timeout_s = max(0.0, float(timeout_ms) / 1000.0)
        except Exception:
            timeout_s = 0.0

        try:
            interval_s = max(0.01, float(interval_ms) / 1000.0)
        except Exception:
            interval_s = 0.2

        check = parse_image_check(action)
        self._log(f"click_image value={check.value}")

        start = time.time()
        pos: tuple[int, int] | None = None
        while True:
            if self._stop_event.is_set():
                self._log("stop requested")
                return

            self._pause_event.wait()

            pos = find_image_center(check)
            if pos is not None:
                break

            if timeout_s > 0 and (time.time() - start) >= timeout_s:
                break

            time.sleep(interval_s)

        if pos is None:
            self._log("click_image not found")
            return

        x, y = pos
        pyautogui.click(x=int(x), y=int(y), button=button)
        self._log(f"click_image x={int(x)} y={int(y)} button={button}")

    def _execute_if(self, action: dict[str, Any], *, steps: int, max_steps: int) -> int:
        check_type = action.get("check")
        timeout_ms = action.get("timeout_ms", 0)
        interval_ms = action.get("interval_ms", 200)

        try:
            timeout_s = max(0.0, float(timeout_ms) / 1000.0)
        except Exception:
            timeout_s = 0.0

        try:
            interval_s = max(0.01, float(interval_ms) / 1000.0)
        except Exception:
            interval_s = 0.2

        self._log(f"if check={check_type}")

        start = time.time()
        matched = False

        if check_type == "image":
            check = parse_image_check(action)
            if timeout_s <= 0:
                matched = image_found(check)
            else:
                while True:
                    if self._stop_event.is_set():
                        self._log("stop requested")
                        return steps

                    self._pause_event.wait()

                    matched = image_found(check)
                    if matched:
                        break

                    if (time.time() - start) >= timeout_s:
                        break

                    time.sleep(interval_s)

        else:
            raise ValueError(f"Unsupported if.check: {check_type!r}")

        branch_key = "on_true" if matched else "on_false"
        self._log(f"if result={'true' if matched else 'false'}")

        branch_actions = action.get(branch_key) or []
        if not isinstance(branch_actions, list):
            raise ValueError(f"{branch_key} must be a list")

        return self._execute_actions(branch_actions, steps=steps, max_steps=max_steps)

    def _log(self, message: str) -> None:
        with self._log_lock:
            self._log_seq += 1
            self._log_buffer.append((self._log_seq, message))
