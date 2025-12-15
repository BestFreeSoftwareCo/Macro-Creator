import copy
import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import QEvent, QTimer, Signal, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

import pyautogui

from PyMacroStudio.core.macro_engine import MacroEngine
from PyMacroStudio.core.macro_io import MacroValidationError, load_macro_json, save_macro_json, validate_macro
from PyMacroStudio.core.paths import macros_saved_dir
from PyMacroStudio.core.settings import AppSettings


class ActionsListWidget(QListWidget):
    reordered = Signal()

    def dropEvent(self, event) -> None:  # type: ignore[override]
        super().dropEvent(event)
        self.reordered.emit()


class ActionDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        *,
        title: str,
        initial: dict[str, Any] | None = None,
        allow_post_action: bool = True,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self._allow_post_action = allow_post_action
        self._post_action: dict[str, Any] | None = None

        self._action_type = QComboBox()
        self._action_type.addItems(["click", "click_at", "key_press", "wait", "wait_random", "move_mouse", "scroll"])

        self._stack = QStackedWidget()
        self._build_pages()

        self._post_enabled = QCheckBox("Post Action")
        self._post_set_btn = QPushButton("Set Post Action")
        self._post_clear_btn = QPushButton("Clear")
        self._post_summary = QLabel("")
        self._post_summary.setStyleSheet("color: #6B7280;")

        form = QFormLayout()
        form.addRow("Action", self._action_type)
        form.addRow(self._stack)

        if self._allow_post_action:
            post_row = QHBoxLayout()
            post_row.addWidget(self._post_enabled)
            post_row.addWidget(self._post_set_btn)
            post_row.addWidget(self._post_clear_btn)
            post_row.addStretch(1)

            post_box = QVBoxLayout()
            post_box.addLayout(post_row)
            post_box.addWidget(self._post_summary)
            form.addRow(post_box)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(buttons)

        self._action_type.currentIndexChanged.connect(self._sync_stack)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        if self._allow_post_action:
            self._post_enabled.toggled.connect(self._sync_post_state)
            self._post_set_btn.clicked.connect(self._pick_post_action)
            self._post_clear_btn.clicked.connect(self._clear_post_action)

        self._apply_initial(initial)
        self._sync_stack()
        self._sync_post_state()

    def get_action(self) -> dict[str, Any] | None:
        if self.exec() != QDialog.DialogCode.Accepted:
            return None
        try:
            action = self._build_action_dict()
        except Exception as e:
            QMessageBox.warning(self, "Invalid", f"{type(e).__name__}: {e}")
            return None
        return action

    def _build_pages(self) -> None:
        self._click_button = QComboBox()
        self._click_button.addItems(["left", "right"])
        self._click_page = QWidget()
        l = QFormLayout(self._click_page)
        l.addRow("Button", self._click_button)
        self._stack.addWidget(self._click_page)

        self._click_at_x = QSpinBox()
        self._click_at_x.setRange(-100000, 100000)
        self._click_at_y = QSpinBox()
        self._click_at_y.setRange(-100000, 100000)
        self._click_at_button = QComboBox()
        self._click_at_button.addItems(["left", "right"])
        self._click_at_use_mouse = QPushButton("Use Current Mouse")
        self._click_at_page = QWidget()
        l = QFormLayout(self._click_at_page)
        l.addRow("X", self._click_at_x)
        l.addRow("Y", self._click_at_y)
        l.addRow("Button", self._click_at_button)
        l.addRow(self._click_at_use_mouse)
        self._click_at_use_mouse.clicked.connect(self._fill_click_at_from_mouse)
        self._stack.addWidget(self._click_at_page)

        self._key_text = QLineEdit()
        self._key_page = QWidget()
        l = QFormLayout(self._key_page)
        l.addRow("Key", self._key_text)
        self._stack.addWidget(self._key_page)

        self._wait_value = QDoubleSpinBox()
        self._wait_value.setRange(0.0, 3600000.0)
        self._wait_value.setDecimals(3)
        self._wait_value.setValue(0.25)
        self._wait_unit = QComboBox()
        self._wait_unit.addItems(["seconds", "ms", "minutes"])
        self._wait_page = QWidget()
        l = QFormLayout(self._wait_page)
        l.addRow("Duration", self._wait_value)
        l.addRow("Unit", self._wait_unit)
        self._stack.addWidget(self._wait_page)

        self._waitr_min = QDoubleSpinBox()
        self._waitr_min.setRange(0.0, 3600000.0)
        self._waitr_min.setDecimals(3)
        self._waitr_min.setValue(0.2)
        self._waitr_max = QDoubleSpinBox()
        self._waitr_max.setRange(0.0, 3600000.0)
        self._waitr_max.setDecimals(3)
        self._waitr_max.setValue(0.6)
        self._waitr_unit = QComboBox()
        self._waitr_unit.addItems(["seconds", "ms", "minutes"])
        self._waitr_page = QWidget()
        l = QFormLayout(self._waitr_page)
        l.addRow("Min", self._waitr_min)
        l.addRow("Max", self._waitr_max)
        l.addRow("Unit", self._waitr_unit)
        self._stack.addWidget(self._waitr_page)

        self._move_x = QSpinBox()
        self._move_x.setRange(-100000, 100000)
        self._move_y = QSpinBox()
        self._move_y.setRange(-100000, 100000)
        self._move_use_mouse = QPushButton("Use Current Mouse")
        self._move_duration = QDoubleSpinBox()
        self._move_duration.setRange(0.0, 60.0)
        self._move_duration.setDecimals(3)
        self._move_duration.setValue(0.0)
        self._move_page = QWidget()
        l = QFormLayout(self._move_page)
        l.addRow("X", self._move_x)
        l.addRow("Y", self._move_y)
        l.addRow(self._move_use_mouse)
        l.addRow("Move Duration (sec)", self._move_duration)
        self._move_use_mouse.clicked.connect(self._fill_move_from_mouse)
        self._stack.addWidget(self._move_page)

        self._scroll_amount = QSpinBox()
        self._scroll_amount.setRange(-100000, 100000)
        self._scroll_amount.setValue(240)
        self._scroll_anchor = QCheckBox("Anchor to current mouse")
        self._scroll_page = QWidget()
        l = QFormLayout(self._scroll_page)
        l.addRow("Amount (+up / -down)", self._scroll_amount)
        l.addRow(self._scroll_anchor)
        self._stack.addWidget(self._scroll_page)

    def _apply_initial(self, initial: dict[str, Any] | None) -> None:
        if not initial:
            return

        t = str(initial.get("type", ""))
        idx = self._action_type.findText(t)
        if idx >= 0:
            self._action_type.setCurrentIndex(idx)

        if t == "click":
            b = str(initial.get("button", "left"))
            i = self._click_button.findText(b)
            if i >= 0:
                self._click_button.setCurrentIndex(i)

        elif t == "click_at":
            self._click_at_x.setValue(int(initial.get("x", 0) or 0))
            self._click_at_y.setValue(int(initial.get("y", 0) or 0))
            b = str(initial.get("button", "left"))
            i = self._click_at_button.findText(b)
            if i >= 0:
                self._click_at_button.setCurrentIndex(i)

        elif t == "key_press":
            self._key_text.setText(str(initial.get("key", "")))

        elif t == "wait":
            ms = float(initial.get("duration_ms", 250) or 0)
            self._wait_unit.setCurrentText("ms")
            self._wait_value.setValue(ms)

        elif t == "wait_random":
            min_ms = float(initial.get("min_ms", 200) or 0)
            max_ms = float(initial.get("max_ms", 600) or 0)
            self._waitr_unit.setCurrentText("ms")
            self._waitr_min.setValue(min_ms)
            self._waitr_max.setValue(max_ms)

        elif t == "move_mouse":
            self._move_x.setValue(int(initial.get("x", 0) or 0))
            self._move_y.setValue(int(initial.get("y", 0) or 0))
            self._move_duration.setValue(max(0.0, float(initial.get("duration_ms", 0) or 0) / 1000.0))

        elif t == "scroll":
            self._scroll_amount.setValue(int(initial.get("amount", 240) or 0))
            self._scroll_anchor.setChecked((initial.get("x") is not None) and (initial.get("y") is not None))

        post = initial.get("post_action")
        if self._allow_post_action and isinstance(post, dict):
            self._post_action = post
            self._post_enabled.setChecked(True)
            self._post_summary.setText(self._format_action_inline(post))

    def _sync_stack(self) -> None:
        t = self._action_type.currentText()
        mapping = {
            "click": 0,
            "click_at": 1,
            "key_press": 2,
            "wait": 3,
            "wait_random": 4,
            "move_mouse": 5,
            "scroll": 6,
        }
        self._stack.setCurrentIndex(mapping.get(t, 0))

    def _sync_post_state(self) -> None:
        if not self._allow_post_action:
            return
        enabled = self._post_enabled.isChecked()
        self._post_set_btn.setEnabled(enabled)
        self._post_clear_btn.setEnabled(enabled)
        self._post_summary.setEnabled(enabled)

        if not enabled:
            self._post_action = None
            self._post_summary.setText("")

    def _pick_post_action(self) -> None:
        dlg = ActionDialog(self, title="Post Action", initial=self._post_action, allow_post_action=False)
        action = dlg.get_action()
        if action is None:
            return
        self._post_action = action
        self._post_summary.setText(self._format_action_inline(action))

    def _clear_post_action(self) -> None:
        self._post_action = None
        if self._allow_post_action:
            self._post_summary.setText("")

    def _build_action_dict(self) -> dict[str, Any]:
        t = self._action_type.currentText()
        action: dict[str, Any]

        if t == "click":
            action = {"type": "click", "button": self._click_button.currentText()}

        elif t == "click_at":
            action = {
                "type": "click_at",
                "x": int(self._click_at_x.value()),
                "y": int(self._click_at_y.value()),
                "button": self._click_at_button.currentText(),
            }

        elif t == "key_press":
            key = (self._key_text.text() or "").strip()
            if not key:
                raise ValueError("key is required")
            action = {"type": "key_press", "key": key}

        elif t == "wait":
            ms = self._duration_to_ms(self._wait_value.value(), self._wait_unit.currentText())
            action = {"type": "wait", "duration_ms": int(ms)}

        elif t == "wait_random":
            min_ms = self._duration_to_ms(self._waitr_min.value(), self._waitr_unit.currentText())
            max_ms = self._duration_to_ms(self._waitr_max.value(), self._waitr_unit.currentText())
            action = {"type": "wait_random", "min_ms": int(min_ms), "max_ms": int(max_ms)}

        elif t == "move_mouse":
            action = {
                "type": "move_mouse",
                "x": int(self._move_x.value()),
                "y": int(self._move_y.value()),
                "duration_ms": int(round(float(self._move_duration.value()) * 1000.0)),
            }

        elif t == "scroll":
            action = {"type": "scroll", "amount": int(self._scroll_amount.value())}
            if self._scroll_anchor.isChecked():
                pos = pyautogui.position()
                action["x"] = int(pos.x)
                action["y"] = int(pos.y)

        else:
            raise ValueError(f"Unknown action type: {t}")

        if self._allow_post_action and self._post_enabled.isChecked() and self._post_action is not None:
            action["post_action"] = self._post_action

        return action

    def _duration_to_ms(self, value: float, unit: str) -> int:
        unit = (unit or "").strip().lower()
        if unit == "ms":
            return int(round(value))
        if unit == "seconds":
            return int(round(value * 1000.0))
        if unit == "minutes":
            return int(round(value * 60_000.0))
        return int(round(value * 1000.0))

    def _format_action_inline(self, action: dict[str, Any]) -> str:
        t = action.get("type")
        if t == "click":
            return f"Click ({action.get('button', 'left')})"
        if t == "click_at":
            return f"Click At ({action.get('x', 0)}, {action.get('y', 0)})"
        if t == "key_press":
            return f"Key Press ({action.get('key', '')})"
        if t == "wait":
            return f"Wait ({action.get('duration_ms', 0)} ms)"
        if t == "wait_random":
            return f"Random Wait ({action.get('min_ms', 0)}-{action.get('max_ms', 0)} ms)"
        if t == "move_mouse":
            return f"Move Mouse ({action.get('x', 0)}, {action.get('y', 0)})"
        if t == "scroll":
            return f"Scroll ({action.get('amount', 0)})"
        return json.dumps(action)

    def _fill_click_at_from_mouse(self) -> None:
        pos = pyautogui.position()
        self._click_at_x.setValue(int(pos.x))
        self._click_at_y.setValue(int(pos.y))

    def _fill_move_from_mouse(self) -> None:
        pos = pyautogui.position()
        self._move_x.setValue(int(pos.x))
        self._move_y.setValue(int(pos.y))


class SimpleModeWidget(QWidget):
    request_toggle = Signal()
    request_stop = Signal()

    def __init__(self, engine: MacroEngine, settings: AppSettings) -> None:
        super().__init__()
        self._engine = engine
        self._settings = settings
        self._actions: list[dict[str, Any]] = []

        self._cleaned_up = False
        self._last_log_seq = 0

        self._keyboard = None
        self._hotkey_toggle_id = None
        self._hotkey_stop_id = None

        self._macro_name = QLineEdit()
        self._macro_name.setPlaceholderText("Macro Name")

        self._start_stop_hotkey = QLineEdit(self._settings.default_start_stop_hotkey)
        self._stop_hotkey = QLineEdit(self._settings.default_stop_hotkey)

        self._repeat = QSpinBox()
        self._repeat.setRange(1, 999999)
        self._repeat.setValue(1)

        self._repeat_forever = QCheckBox("Repeat until stopped")

        self._action_type = QComboBox()
        self._action_type.addItems(["click", "click_at", "key_press", "wait", "wait_random", "move_mouse", "scroll"])

        self._quick_delay_ms = QSpinBox()
        self._quick_delay_ms.setRange(0, 3600000)
        self._quick_delay_ms.setValue(250)
        self._quick_delay_ms.setSingleStep(50)

        self._quick_delay_100_btn = QPushButton("+0.1s")
        self._quick_delay_250_btn = QPushButton("+0.25s")
        self._quick_delay_500_btn = QPushButton("+0.5s")
        self._quick_delay_1000_btn = QPushButton("+1s")
        self._quick_delay_2000_btn = QPushButton("+2s")
        self._quick_delay_5000_btn = QPushButton("+5s")
        self._quick_delay_add_btn = QPushButton("Add Delay")

        self._add_action_btn = QPushButton("Add")
        self._insert_action_btn = QPushButton("Insert")
        self._edit_action_btn = QPushButton("Edit")
        self._duplicate_action_btn = QPushButton("Duplicate")
        self._remove_action_btn = QPushButton("Delete")
        self._remove_action_btn.setObjectName("secondary")
        self._move_up_btn = QPushButton("Up")
        self._move_up_btn.setObjectName("secondary")
        self._move_down_btn = QPushButton("Down")
        self._move_down_btn.setObjectName("secondary")

        self._actions_list = ActionsListWidget()
        self._actions_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._actions_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self._actions_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._actions_list.setDragEnabled(True)
        self._actions_list.setAcceptDrops(True)
        self._actions_list.setDropIndicatorShown(True)
        self._actions_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        self._start_btn = QPushButton("Start Macro")
        self._stop_btn = QPushButton("Stop Macro")
        self._stop_btn.setObjectName("secondary")

        self._save_btn = QPushButton("Save")
        self._save_btn.setObjectName("secondary")
        self._load_btn = QPushButton("Load")
        self._load_btn.setObjectName("secondary")

        self._clear_logs_btn = QPushButton("Clear Logs")
        self._clear_logs_btn.setObjectName("secondary")

        self._logs = QPlainTextEdit()
        self._logs.setReadOnly(True)
        self._logs.setMaximumBlockCount(2000)

        self._build_layout()
        self._wire_events()

        self._log_timer = QTimer(self)
        self._log_timer.setInterval(50)
        self._log_timer.timeout.connect(self._drain_logs)
        self._log_timer.start()

        self._state_timer = QTimer(self)
        self._state_timer.setInterval(150)
        self._state_timer.timeout.connect(self._sync_state)
        self._state_timer.start()

        self._try_register_global_hotkeys()

    def cleanup(self) -> None:
        if self._cleaned_up:
            return
        self._cleaned_up = True

        try:
            self._unregister_global_hotkeys()
        except Exception:
            pass

        try:
            self._log_timer.stop()
            self._state_timer.stop()
        except Exception:
            pass

        try:
            self._actions_list.removeEventFilter(self)
        except Exception:
            pass

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)

        header = QGroupBox("Simple Mode")
        header_l = QVBoxLayout(header)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Name"))
        row1.addWidget(self._macro_name, 1)
        row1.addWidget(QLabel("Repeat"))
        row1.addWidget(self._repeat)
        row1.addWidget(self._repeat_forever)
        header_l.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Start/Stop Hotkey"))
        row2.addWidget(self._start_stop_hotkey)
        row2.addWidget(QLabel("Emergency Stop"))
        row2.addWidget(self._stop_hotkey)
        header_l.addLayout(row2)

        root.addWidget(header)

        actions_box = QGroupBox("Actions")
        actions_l = QVBoxLayout(actions_box)

        add_row = QHBoxLayout()
        add_row.addWidget(self._action_type)
        add_row.addWidget(self._add_action_btn)
        add_row.addWidget(self._insert_action_btn)
        add_row.addWidget(self._edit_action_btn)
        add_row.addWidget(self._duplicate_action_btn)
        add_row.addWidget(self._remove_action_btn)
        add_row.addWidget(self._move_up_btn)
        add_row.addWidget(self._move_down_btn)
        actions_l.addLayout(add_row)

        delay_row = QHBoxLayout()
        delay_row.addWidget(QLabel("Quick Delay"))
        delay_row.addWidget(self._quick_delay_100_btn)
        delay_row.addWidget(self._quick_delay_250_btn)
        delay_row.addWidget(self._quick_delay_500_btn)
        delay_row.addWidget(self._quick_delay_1000_btn)
        delay_row.addWidget(self._quick_delay_2000_btn)
        delay_row.addWidget(self._quick_delay_5000_btn)
        delay_row.addSpacing(8)
        delay_row.addWidget(self._quick_delay_ms)
        delay_row.addWidget(QLabel("ms"))
        delay_row.addWidget(self._quick_delay_add_btn)
        delay_row.addStretch(1)
        actions_l.addLayout(delay_row)

        actions_l.addWidget(self._actions_list, 1)
        root.addWidget(actions_box, 2)

        controls = QHBoxLayout()
        controls.addWidget(self._start_btn)
        controls.addWidget(self._stop_btn)
        controls.addWidget(self._save_btn)
        controls.addWidget(self._load_btn)
        root.addLayout(controls)

        logs_box = QGroupBox("Logs")
        logs_l = QVBoxLayout(logs_box)
        logs_controls = QHBoxLayout()
        logs_controls.addStretch(1)
        logs_controls.addWidget(self._clear_logs_btn)
        logs_l.addLayout(logs_controls)
        logs_l.addWidget(self._logs)
        root.addWidget(logs_box, 1)

    def _wire_events(self) -> None:
        self._add_action_btn.clicked.connect(self._add_action)
        self._insert_action_btn.clicked.connect(self._insert_action)
        self._edit_action_btn.clicked.connect(self._edit_selected)
        self._duplicate_action_btn.clicked.connect(self._duplicate_selected)
        self._remove_action_btn.clicked.connect(self._remove_selected)
        self._move_up_btn.clicked.connect(lambda: self._move_selected(-1))
        self._move_down_btn.clicked.connect(lambda: self._move_selected(1))

        self._quick_delay_100_btn.clicked.connect(lambda: self._quick_add_delay(100))
        self._quick_delay_250_btn.clicked.connect(lambda: self._quick_add_delay(250))
        self._quick_delay_500_btn.clicked.connect(lambda: self._quick_add_delay(500))
        self._quick_delay_1000_btn.clicked.connect(lambda: self._quick_add_delay(1000))
        self._quick_delay_2000_btn.clicked.connect(lambda: self._quick_add_delay(2000))
        self._quick_delay_5000_btn.clicked.connect(lambda: self._quick_add_delay(5000))
        self._quick_delay_add_btn.clicked.connect(lambda: self._quick_add_delay(int(self._quick_delay_ms.value())))

        self._actions_list.reordered.connect(self._sync_actions_from_list)
        self._actions_list.itemDoubleClicked.connect(lambda _item: self._edit_selected())
        self._actions_list.customContextMenuRequested.connect(self._show_actions_context_menu)
        self._actions_list.installEventFilter(self)
        self._actions_list.currentRowChanged.connect(lambda _row: self._sync_state())

        self._start_btn.clicked.connect(self._start_macro)
        self._stop_btn.clicked.connect(self._stop_macro)
        self._save_btn.clicked.connect(self._save_macro)
        self._load_btn.clicked.connect(self._load_macro)
        self._clear_logs_btn.clicked.connect(self._clear_logs)

        self.request_toggle.connect(self._toggle_macro)
        self.request_stop.connect(self._stop_macro)

        self._start_stop_hotkey.editingFinished.connect(self._try_register_global_hotkeys)
        self._stop_hotkey.editingFinished.connect(self._try_register_global_hotkeys)

        self._repeat_forever.toggled.connect(lambda _checked: self._sync_state())

    def _add_action(self) -> None:
        action = self._prompt_action()
        if action is None:
            return
        self._actions.append(action)
        self._refresh_actions_list()
        self._actions_list.setCurrentRow(len(self._actions) - 1)

    def _quick_add_delay(self, duration_ms: int) -> None:
        if self._engine.is_running:
            return
        try:
            ms = int(duration_ms)
        except Exception:
            return
        if ms < 0:
            return

        action = {"type": "wait", "duration_ms": ms}

        row = self._actions_list.currentRow()
        insert_at = len(self._actions) if row < 0 else row + 1
        self._actions.insert(insert_at, action)
        self._refresh_actions_list()
        self._actions_list.setCurrentRow(insert_at)

    def _insert_action(self) -> None:
        action = self._prompt_action()
        if action is None:
            return

        row = self._actions_list.currentRow()
        insert_at = len(self._actions) if row < 0 else row + 1
        self._actions.insert(insert_at, action)
        self._refresh_actions_list()
        self._actions_list.setCurrentRow(insert_at)

    def _edit_selected(self) -> None:
        row = self._actions_list.currentRow()
        if row < 0 or row >= len(self._actions):
            return
        current = self._actions[row]
        updated = self._prompt_action(initial=current)
        if updated is None:
            return
        self._actions[row] = updated
        self._refresh_actions_list()
        self._actions_list.setCurrentRow(row)

    def _duplicate_selected(self) -> None:
        row = self._actions_list.currentRow()
        if row < 0 or row >= len(self._actions):
            return
        action = copy.deepcopy(self._actions[row])
        self._actions.insert(row + 1, action)
        self._refresh_actions_list()
        self._actions_list.setCurrentRow(row + 1)

    def _prompt_action(self, initial: dict[str, Any] | None = None) -> dict[str, Any] | None:
        if self._engine.is_running:
            return None
        title = "Edit Action" if initial is not None else "Add Action"
        dlg = ActionDialog(self, title=title, initial=initial, allow_post_action=True)
        return dlg.get_action()

    def _remove_selected(self) -> None:
        row = self._actions_list.currentRow()
        if row < 0 or row >= len(self._actions):
            return
        self._actions.pop(row)
        self._refresh_actions_list()

    def _move_selected(self, delta: int) -> None:
        row = self._actions_list.currentRow()
        if row < 0 or row >= len(self._actions):
            return
        new_row = row + delta
        if new_row < 0 or new_row >= len(self._actions):
            return
        self._actions[row], self._actions[new_row] = self._actions[new_row], self._actions[row]
        self._refresh_actions_list()
        self._actions_list.setCurrentRow(new_row)

    def _refresh_actions_list(self) -> None:
        self._actions_list.clear()
        for action in self._actions:
            item = QListWidgetItem(self._format_action(action))
            item.setData(Qt.ItemDataRole.UserRole, action)
            self._actions_list.addItem(item)

    def _sync_actions_from_list(self) -> None:
        actions: list[dict[str, Any]] = []
        for i in range(self._actions_list.count()):
            item = self._actions_list.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(data, dict):
                actions.append(data)
        if len(actions) == len(self._actions):
            self._actions = actions

    def _format_action(self, action: dict[str, Any]) -> str:
        t = action.get("type")
        if t == "click":
            base = f"Click ({action.get('button', 'left')})"
            return self._append_post_action(base, action)
        if t == "click_at":
            base = f"Click At ({action.get('x', 0)}, {action.get('y', 0)}) ({action.get('button', 'left')})"
            return self._append_post_action(base, action)
        if t == "key_press":
            base = f"Key Press ({action.get('key', '')})"
            return self._append_post_action(base, action)
        if t == "wait":
            base = f"Wait ({action.get('duration_ms', 0)} ms)"
            return self._append_post_action(base, action)
        if t == "wait_random":
            base = f"Random Wait ({action.get('min_ms', 0)}-{action.get('max_ms', 0)} ms)"
            return self._append_post_action(base, action)
        if t == "move_mouse":
            base = f"Move Mouse ({action.get('x', 0)}, {action.get('y', 0)}) ({action.get('duration_ms', 0)} ms)"
            return self._append_post_action(base, action)
        if t == "scroll":
            amount = action.get('amount', 0)
            if action.get('x') is not None and action.get('y') is not None:
                base = f"Scroll ({amount}) at ({action.get('x')}, {action.get('y')})"
                return self._append_post_action(base, action)
            base = f"Scroll ({amount})"
            return self._append_post_action(base, action)
        return json.dumps(action)

    def _append_post_action(self, base: str, action: dict[str, Any]) -> str:
        post = action.get("post_action")
        if isinstance(post, dict):
            return f"{base}  ->  {self._format_action_inline(post)}"
        return base

    def _format_action_inline(self, action: dict[str, Any]) -> str:
        t = action.get("type")
        if t == "click":
            return f"Click ({action.get('button', 'left')})"
        if t == "click_at":
            return f"Click At ({action.get('x', 0)}, {action.get('y', 0)})"
        if t == "key_press":
            return f"Key Press ({action.get('key', '')})"
        if t == "wait":
            return f"Wait ({action.get('duration_ms', 0)} ms)"
        if t == "wait_random":
            return f"Random Wait ({action.get('min_ms', 0)}-{action.get('max_ms', 0)} ms)"
        if t == "move_mouse":
            return f"Move Mouse ({action.get('x', 0)}, {action.get('y', 0)})"
        if t == "scroll":
            return f"Scroll ({action.get('amount', 0)})"
        return json.dumps(action)

    def _build_macro(self) -> dict[str, Any]:
        self._sync_actions_from_list()
        name = self._macro_name.text().strip() or "Untitled Macro"
        start_stop = self._start_stop_hotkey.text().strip() or "F6"
        stop_key = self._stop_hotkey.text().strip() or "ESC"

        repeat = 0 if self._repeat_forever.isChecked() else int(self._repeat.value())

        return {
            "schema_version": 1,
            "name": name,
            "hotkeys": {"start_stop": start_stop, "stop": stop_key},
            "settings": {"repeat": repeat, "max_steps": int(self._settings.max_steps)},
            "actions": list(self._actions),
        }

    def _suggest_macro_filename(self) -> str:
        raw = self._macro_name.text().strip() or "macro"
        safe = "".join(c for c in raw if c.isalnum() or c in (" ", "-", "_", ".")).strip()
        safe = safe.replace(" ", "_")
        if not safe:
            safe = "macro"
        if not safe.lower().endswith(".json"):
            safe += ".json"
        return safe

    def _start_macro(self) -> None:
        if self._engine.is_running:
            return
        macro = self._build_macro()
        try:
            validate_macro(macro)
        except MacroValidationError as e:
            QMessageBox.warning(self, "Invalid macro", str(e))
            return
        if not macro["actions"]:
            QMessageBox.information(self, "No actions", "Add at least one action.")
            return
        self._engine.start(macro)

    def _save_macro(self) -> None:
        macro = self._build_macro()
        try:
            validate_macro(macro)
        except MacroValidationError as e:
            QMessageBox.warning(self, "Invalid macro", str(e))
            return

        default_name = self._suggest_macro_filename()
        filename, ok = QInputDialog.getText(self, "Save Macro", "File name", text=default_name)
        if not ok:
            return
        filename = filename.strip()
        if not filename:
            return
        if not filename.lower().endswith(".json"):
            filename += ".json"

        path = macros_saved_dir() / filename
        try:
            save_macro_json(path, macro)
        except Exception as e:
            QMessageBox.critical(self, "Save failed", f"{type(e).__name__}: {e}")
            return
        self._logs.appendPlainText(f"saved: {path}")

    def _load_macro(self) -> None:
        start_dir = macros_saved_dir()
        start_dir.mkdir(parents=True, exist_ok=True)

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Macro",
            str(start_dir),
            "Macro JSON (*.json);;All Files (*.*)",
        )
        if not file_path:
            return

        path = Path(file_path)
        try:
            macro = load_macro_json(path)
        except Exception as e:
            QMessageBox.critical(self, "Load failed", f"{type(e).__name__}: {e}")
            return

        self._macro_name.setText(str(macro.get("name", "")))

        hotkeys = macro.get("hotkeys") or {}
        if isinstance(hotkeys, dict):
            self._start_stop_hotkey.setText(str(hotkeys.get("start_stop", "F6")))
            self._stop_hotkey.setText(str(hotkeys.get("stop", "ESC")))

        settings = macro.get("settings") or {}
        if isinstance(settings, dict):
            try:
                repeat = int(settings.get("repeat", 1))
            except Exception:
                repeat = 1

            if repeat <= 0:
                self._repeat_forever.setChecked(True)
                self._repeat.setValue(1)
            else:
                self._repeat_forever.setChecked(False)
                self._repeat.setValue(max(1, repeat))

        actions = macro.get("actions") or []
        if isinstance(actions, list):
            self._actions = [a for a in actions if isinstance(a, dict)]
        else:
            self._actions = []
        self._refresh_actions_list()
        self._try_register_global_hotkeys()
        self._logs.appendPlainText(f"loaded: {path}")

    def _stop_macro(self) -> None:
        self._engine.stop()

    def _toggle_macro(self) -> None:
        if self._engine.is_running:
            self._engine.stop()
        else:
            self._start_macro()

    def _sync_state(self) -> None:
        running = self._engine.is_running
        self._start_btn.setEnabled(not running)
        self._stop_btn.setEnabled(running)

        row = self._actions_list.currentRow()
        has_selection = 0 <= row < len(self._actions)

        self._macro_name.setEnabled(not running)
        self._repeat_forever.setEnabled(not running)
        self._repeat.setEnabled((not running) and (not self._repeat_forever.isChecked()))
        self._start_stop_hotkey.setEnabled(not running)
        self._stop_hotkey.setEnabled(not running)
        self._action_type.setEnabled(not running)
        self._add_action_btn.setEnabled(not running)
        self._insert_action_btn.setEnabled(not running)
        self._edit_action_btn.setEnabled((not running) and has_selection)
        self._duplicate_action_btn.setEnabled((not running) and has_selection)
        self._remove_action_btn.setEnabled((not running) and has_selection)
        self._move_up_btn.setEnabled((not running) and has_selection and row > 0)
        self._move_down_btn.setEnabled((not running) and has_selection and row < (len(self._actions) - 1))
        self._actions_list.setEnabled(not running)
        self._save_btn.setEnabled(not running)
        self._load_btn.setEnabled(not running)

        self._quick_delay_ms.setEnabled(not running)
        self._quick_delay_100_btn.setEnabled(not running)
        self._quick_delay_250_btn.setEnabled(not running)
        self._quick_delay_500_btn.setEnabled(not running)
        self._quick_delay_1000_btn.setEnabled(not running)
        self._quick_delay_2000_btn.setEnabled(not running)
        self._quick_delay_5000_btn.setEnabled(not running)
        self._quick_delay_add_btn.setEnabled(not running)

    def eventFilter(self, obj, event) -> bool:  # type: ignore[override]
        if obj is self._actions_list and event.type() == QEvent.Type.KeyPress:
            if self._engine.is_running:
                return False

            key = event.key()
            mods = event.modifiers()

            if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
                self._remove_selected()
                return True

            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._edit_selected()
                return True

            if (mods & Qt.KeyboardModifier.ControlModifier) and key == Qt.Key.Key_D:
                self._duplicate_selected()
                return True

            if (mods & Qt.KeyboardModifier.ControlModifier) and key == Qt.Key.Key_I:
                self._insert_action()
                return True

            if (mods & Qt.KeyboardModifier.ControlModifier) and key == Qt.Key.Key_Up:
                self._move_selected(-1)
                return True

            if (mods & Qt.KeyboardModifier.ControlModifier) and key == Qt.Key.Key_Down:
                self._move_selected(1)
                return True

        return super().eventFilter(obj, event)

    def _show_actions_context_menu(self, pos) -> None:
        if self._engine.is_running:
            return

        row = self._actions_list.currentRow()
        has_selection = 0 <= row < len(self._actions)

        menu = QMenu(self)
        act_add = menu.addAction("Add")
        act_insert = menu.addAction("Insert")
        act_edit = menu.addAction("Edit")
        act_dup = menu.addAction("Duplicate")
        act_del = menu.addAction("Delete")
        menu.addSeparator()
        act_up = menu.addAction("Move Up")
        act_down = menu.addAction("Move Down")

        act_edit.setEnabled(has_selection)
        act_dup.setEnabled(has_selection)
        act_del.setEnabled(has_selection)
        act_up.setEnabled(has_selection and row > 0)
        act_down.setEnabled(has_selection and row < (len(self._actions) - 1))

        chosen = menu.exec(self._actions_list.mapToGlobal(pos))
        if chosen is None:
            return

        if chosen is act_add:
            self._add_action()
        elif chosen is act_insert:
            self._insert_action()
        elif chosen is act_edit:
            self._edit_selected()
        elif chosen is act_dup:
            self._duplicate_selected()
        elif chosen is act_del:
            self._remove_selected()
        elif chosen is act_up:
            self._move_selected(-1)
        elif chosen is act_down:
            self._move_selected(1)

    def _clear_logs(self) -> None:
        self._logs.clear()

    def _drain_logs(self) -> None:
        last, messages = self._engine.read_logs(self._last_log_seq)
        if messages:
            for msg in messages:
                self._logs.appendPlainText(msg)
            self._last_log_seq = last

    def _try_register_global_hotkeys(self) -> None:
        self._unregister_global_hotkeys()

        try:
            import keyboard  # type: ignore

            self._keyboard = keyboard
        except Exception as e:
            self._keyboard = None
            self._logs.appendPlainText(f"hotkeys unavailable: {type(e).__name__}: {e}")
            return

        start_stop = (self._start_stop_hotkey.text() or "").strip()
        stop_key = (self._stop_hotkey.text() or "").strip()

        try:
            if start_stop:
                self._hotkey_toggle_id = self._keyboard.add_hotkey(start_stop, lambda: self.request_toggle.emit())
            if stop_key:
                self._hotkey_stop_id = self._keyboard.add_hotkey(stop_key, lambda: self.request_stop.emit())
            self._logs.appendPlainText("hotkeys registered")
        except Exception as e:
            self._logs.appendPlainText(f"hotkey registration failed: {type(e).__name__}: {e}")

    def _unregister_global_hotkeys(self) -> None:
        if not self._keyboard:
            return
        try:
            if self._hotkey_toggle_id is not None:
                self._keyboard.remove_hotkey(self._hotkey_toggle_id)
            if self._hotkey_stop_id is not None:
                self._keyboard.remove_hotkey(self._hotkey_stop_id)
        except Exception:
            pass
        finally:
            self._hotkey_toggle_id = None
            self._hotkey_stop_id = None
