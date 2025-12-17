import copy
import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import QEvent, QTimer, Signal, Qt
from PySide6.QtWidgets import (
    QApplication,
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
    _favorite_types: set[str] = set()
    _recent_types: list[str] = []

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

        self._action_defs: list[dict[str, str]] = [
            {"type": "click", "label": "Click", "category": "Mouse", "description": "Click using the chosen mouse button."},
            {"type": "click_at", "label": "Click At", "category": "Mouse", "description": "Click at an exact X/Y position."},
            {"type": "mouse_down", "label": "Mouse Down", "category": "Mouse", "description": "Hold a mouse button (optionally at X/Y)."},
            {"type": "mouse_up", "label": "Mouse Up", "category": "Mouse", "description": "Release a mouse button (optionally at X/Y)."},
            {"type": "move_mouse", "label": "Move Mouse", "category": "Mouse", "description": "Move the mouse to an X/Y position."},
            {"type": "move_mouse_rel", "label": "Move Mouse (Relative)", "category": "Mouse", "description": "Move the mouse by DX/DY."},
            {"type": "drag_to", "label": "Drag To", "category": "Mouse", "description": "Click-and-drag to an X/Y position."},
            {"type": "scroll", "label": "Scroll", "category": "Mouse", "description": "Scroll up/down by an amount."},
            {"type": "key_press", "label": "Key Press", "category": "Keyboard", "description": "Press a single key."},
            {"type": "key_down", "label": "Key Down", "category": "Keyboard", "description": "Hold a key down."},
            {"type": "key_up", "label": "Key Up", "category": "Keyboard", "description": "Release a key."},
            {"type": "type_text", "label": "Type Text", "category": "Keyboard", "description": "Type a string (optionally with an interval)."},
            {"type": "hotkey", "label": "Hotkey", "category": "Keyboard", "description": "Press a key combination (e.g. ctrl+shift+x)."},
            {"type": "wait", "label": "Wait", "category": "Timing", "description": "Wait for a fixed duration."},
            {"type": "wait_random", "label": "Random Wait", "category": "Timing", "description": "Wait a random duration between min/max."},
            {"type": "wait_for_image", "label": "Wait For Image", "category": "Images", "description": "Wait until an image appears on screen."},
            {"type": "click_image", "label": "Click Image", "category": "Images", "description": "Find an image on screen and click its center."},
        ]

        self._action_search = QLineEdit()
        self._action_search.setPlaceholderText("Search actions...")

        self._action_category = QComboBox()
        self._action_category.addItems(["All", "Favorites", "Recent", "Mouse", "Keyboard", "Timing", "Images"])

        self._favorite_toggle = QPushButton("Favorite")

        self._action_list = QListWidget()
        self._action_list.setMinimumWidth(260)

        self._action_desc = QLabel("")
        self._action_desc.setWordWrap(True)
        self._action_desc.setStyleSheet("color: #6B7280;")

        self._preview = QPlainTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setMinimumHeight(140)
        self._preview.setPlaceholderText("JSON preview...")
        self._copy_json_btn = QPushButton("Copy JSON")

        self._stack = QStackedWidget()
        self._build_pages()

        self._post_enabled = QCheckBox("Post Action")
        self._post_set_btn = QPushButton("Set Post Action")
        self._post_clear_btn = QPushButton("Clear")
        self._post_summary = QLabel("")
        self._post_summary.setStyleSheet("color: #6B7280;")

        left = QVBoxLayout()
        left.addWidget(self._action_search)
        left.addWidget(self._action_category)
        left.addWidget(self._favorite_toggle)
        left.addWidget(self._action_list, 1)

        right = QVBoxLayout()
        right.addWidget(self._action_desc)
        right.addWidget(self._stack, 1)
        right.addWidget(QLabel("JSON Preview"))
        right.addWidget(self._preview)
        right.addWidget(self._copy_json_btn)

        if self._allow_post_action:
            post_row = QHBoxLayout()
            post_row.addWidget(self._post_enabled)
            post_row.addWidget(self._post_set_btn)
            post_row.addWidget(self._post_clear_btn)
            post_row.addStretch(1)

            post_box = QVBoxLayout()
            post_box.addLayout(post_row)
            post_box.addWidget(self._post_summary)
            right.addLayout(post_box)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)

        root = QVBoxLayout(self)
        content = QHBoxLayout()
        left_w = QWidget()
        left_w.setLayout(left)
        content.addWidget(left_w)

        right_w = QWidget()
        right_w.setLayout(right)
        content.addWidget(right_w, 1)
        root.addLayout(content)
        root.addWidget(buttons)

        self._action_search.textChanged.connect(self._refresh_action_list)
        self._action_category.currentIndexChanged.connect(self._refresh_action_list)
        self._action_list.currentRowChanged.connect(lambda _row: self._sync_stack())
        self._favorite_toggle.clicked.connect(self._toggle_favorite)
        self._copy_json_btn.clicked.connect(self._copy_preview_json)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        if self._allow_post_action:
            self._post_enabled.toggled.connect(self._sync_post_state)
            self._post_set_btn.clicked.connect(self._pick_post_action)
            self._post_clear_btn.clicked.connect(self._clear_post_action)

        self._apply_initial(initial)
        self._refresh_action_list()
        self._sync_stack()
        self._sync_post_state()
        self._wire_preview_events()
        self._update_preview()

    def get_action(self) -> dict[str, Any] | None:
        if self.exec() != QDialog.DialogCode.Accepted:
            return None
        try:
            action = self._build_action_dict()
        except Exception as e:
            QMessageBox.warning(self, "Invalid", f"{type(e).__name__}: {e}")
            return None

        t = str(action.get("type") or "").strip()
        if t:
            recents = [x for x in self._recent_types if x != t]
            recents.insert(0, t)
            self._recent_types = recents[:15]
        return action

    def _refresh_action_list(self) -> None:
        query = (self._action_search.text() or "").strip().lower()
        cat = (self._action_category.currentText() or "All").strip()

        def matches(defn: dict[str, str]) -> bool:
            if cat == "Favorites" and defn["type"] not in self._favorite_types:
                return False
            if cat == "Recent" and defn["type"] not in self._recent_types:
                return False
            if cat not in ("All", "Favorites", "Recent") and defn["category"] != cat:
                return False
            if not query:
                return True
            hay = (defn["type"] + " " + defn["label"] + " " + defn["category"] + " " + defn["description"]).lower()
            return query in hay

        selected_type = self._selected_action_type()
        self._action_list.blockSignals(True)
        self._action_list.clear()

        defs = [d for d in self._action_defs if matches(d)]
        if cat == "Recent":
            order = {t: i for i, t in enumerate(self._recent_types)}
            defs.sort(key=lambda d: order.get(d["type"], 9999))
        else:
            defs.sort(key=lambda d: (d["category"], d["label"]))

        for d in defs:
            star = "★ " if d["type"] in self._favorite_types else ""
            item = QListWidgetItem(f"{star}{d['label']}")
            item.setData(Qt.ItemDataRole.UserRole, d["type"])
            self._action_list.addItem(item)

        self._action_list.blockSignals(False)

        if selected_type:
            row = self._find_action_row(selected_type)
            if row >= 0:
                self._action_list.setCurrentRow(row)
                return

        if self._action_list.count() > 0:
            self._action_list.setCurrentRow(0)

    def _find_action_row(self, action_type: str) -> int:
        for i in range(self._action_list.count()):
            item = self._action_list.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == action_type:
                return i
        return -1

    def _selected_action_type(self) -> str:
        item = self._action_list.currentItem()
        if item is None:
            return ""
        t = item.data(Qt.ItemDataRole.UserRole)
        return str(t or "")

    def _toggle_favorite(self) -> None:
        t = self._selected_action_type()
        if not t:
            return
        if t in self._favorite_types:
            self._favorite_types.remove(t)
        else:
            self._favorite_types.add(t)
        self._refresh_action_list()
        self._sync_stack()

    def _set_selected_action_type(self, action_type: str) -> None:
        if not action_type:
            return
        row = self._find_action_row(action_type)
        if row >= 0:
            self._action_list.setCurrentRow(row)

    def _wire_preview_events(self) -> None:
        def safe_connect(obj: Any, signal_name: str) -> None:
            try:
                sig = getattr(obj, signal_name)
                sig.connect(self._update_preview)
            except Exception:
                pass

        widgets: list[Any] = [
            self._click_button,
            self._click_at_x,
            self._click_at_y,
            self._click_at_button,
            self._key_text,
            self._wait_value,
            self._wait_unit,
            self._waitr_min,
            self._waitr_max,
            self._waitr_unit,
            self._move_x,
            self._move_y,
            self._move_duration,
            self._scroll_amount,
            self._scroll_anchor,
            self._type_text_text,
            self._type_text_interval_ms,
            self._hotkey_keys,
            self._mouse_button,
            self._mouse_at_pos,
            self._mouse_x,
            self._mouse_y,
            self._move_rel_dx,
            self._move_rel_dy,
            self._move_rel_duration,
            self._drag_x,
            self._drag_y,
            self._drag_button,
            self._drag_duration,
            self._wfi_value,
            self._wfi_confidence,
            self._wfi_timeout_ms,
            self._wfi_interval_ms,
            self._wfi_use_region,
            self._wfi_region_x,
            self._wfi_region_y,
            self._wfi_region_w,
            self._wfi_region_h,
            self._ci_value,
            self._ci_button,
            self._ci_confidence,
            self._ci_timeout_ms,
            self._ci_interval_ms,
            self._ci_use_region,
            self._ci_region_x,
            self._ci_region_y,
            self._ci_region_w,
            self._ci_region_h,
        ]

        for w in widgets:
            safe_connect(w, "textChanged")
            safe_connect(w, "valueChanged")
            safe_connect(w, "currentIndexChanged")
            safe_connect(w, "toggled")

        if self._allow_post_action:
            safe_connect(self._post_enabled, "toggled")

    def _update_preview(self) -> None:
        try:
            action = self._build_action_dict()
            self._preview.setPlainText(json.dumps(action, indent=2))
        except Exception as e:
            self._preview.setPlainText(f"{type(e).__name__}: {e}")

    def _copy_preview_json(self) -> None:
        text = self._preview.toPlainText()
        if not text.strip():
            return
        cb = QApplication.clipboard()
        cb.setText(text)

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

        self._type_text_text = QLineEdit()
        self._type_text_interval_ms = QSpinBox()
        self._type_text_interval_ms.setRange(0, 5000)
        self._type_text_interval_ms.setValue(0)
        self._type_text_page = QWidget()
        l = QFormLayout(self._type_text_page)
        l.addRow("Text", self._type_text_text)
        l.addRow("Interval (ms)", self._type_text_interval_ms)
        self._stack.addWidget(self._type_text_page)

        self._hotkey_keys = QLineEdit()
        self._hotkey_keys.setPlaceholderText("ctrl+shift+x")
        self._hotkey_page = QWidget()
        l = QFormLayout(self._hotkey_page)
        l.addRow("Keys", self._hotkey_keys)
        self._stack.addWidget(self._hotkey_page)

        self._mouse_button = QComboBox()
        self._mouse_button.addItems(["left", "right", "middle"])
        self._mouse_at_pos = QCheckBox("At position")
        self._mouse_x = QSpinBox()
        self._mouse_x.setRange(-100000, 100000)
        self._mouse_y = QSpinBox()
        self._mouse_y.setRange(-100000, 100000)
        self._mouse_use_mouse = QPushButton("Use Current Mouse")
        self._mouse_page = QWidget()
        l = QFormLayout(self._mouse_page)
        l.addRow("Button", self._mouse_button)
        l.addRow(self._mouse_at_pos)

        mouse_pos_row = QHBoxLayout()
        mouse_pos_row.addWidget(QLabel("X"))
        mouse_pos_row.addWidget(self._mouse_x)
        mouse_pos_row.addWidget(QLabel("Y"))
        mouse_pos_row.addWidget(self._mouse_y)
        mouse_pos_row.addWidget(self._mouse_use_mouse)
        mouse_pos_w = QWidget()
        mouse_pos_w.setLayout(mouse_pos_row)
        l.addRow(mouse_pos_w)

        self._mouse_use_mouse.clicked.connect(self._fill_mouse_from_mouse)
        self._mouse_at_pos.toggled.connect(self._sync_mouse_pos_state)
        self._sync_mouse_pos_state()
        self._stack.addWidget(self._mouse_page)

        self._move_rel_dx = QSpinBox()
        self._move_rel_dx.setRange(-100000, 100000)
        self._move_rel_dy = QSpinBox()
        self._move_rel_dy.setRange(-100000, 100000)
        self._move_rel_duration = QDoubleSpinBox()
        self._move_rel_duration.setRange(0.0, 60.0)
        self._move_rel_duration.setDecimals(3)
        self._move_rel_duration.setValue(0.0)
        self._move_rel_page = QWidget()
        l = QFormLayout(self._move_rel_page)
        l.addRow("DX", self._move_rel_dx)
        l.addRow("DY", self._move_rel_dy)
        l.addRow("Move Duration (sec)", self._move_rel_duration)
        self._stack.addWidget(self._move_rel_page)

        self._drag_x = QSpinBox()
        self._drag_x.setRange(-100000, 100000)
        self._drag_y = QSpinBox()
        self._drag_y.setRange(-100000, 100000)
        self._drag_button = QComboBox()
        self._drag_button.addItems(["left", "right", "middle"])
        self._drag_use_mouse = QPushButton("Use Current Mouse")
        self._drag_duration = QDoubleSpinBox()
        self._drag_duration.setRange(0.0, 60.0)
        self._drag_duration.setDecimals(3)
        self._drag_duration.setValue(0.0)
        self._drag_page = QWidget()
        l = QFormLayout(self._drag_page)
        l.addRow("X", self._drag_x)
        l.addRow("Y", self._drag_y)
        l.addRow("Button", self._drag_button)
        l.addRow(self._drag_use_mouse)
        l.addRow("Drag Duration (sec)", self._drag_duration)
        self._drag_use_mouse.clicked.connect(self._fill_drag_from_mouse)
        self._stack.addWidget(self._drag_page)

        self._wfi_value = QLineEdit()
        self._wfi_browse = QPushButton("Browse")
        wfi_path_row = QHBoxLayout()
        wfi_path_row.addWidget(self._wfi_value, 1)
        wfi_path_row.addWidget(self._wfi_browse)
        wfi_path_w = QWidget()
        wfi_path_w.setLayout(wfi_path_row)

        self._wfi_confidence = QDoubleSpinBox()
        self._wfi_confidence.setRange(0.0, 1.0)
        self._wfi_confidence.setDecimals(2)
        self._wfi_confidence.setSingleStep(0.05)
        self._wfi_confidence.setValue(0.9)

        self._wfi_timeout_ms = QSpinBox()
        self._wfi_timeout_ms.setRange(0, 3600000)
        self._wfi_timeout_ms.setValue(0)

        self._wfi_interval_ms = QSpinBox()
        self._wfi_interval_ms.setRange(10, 60000)
        self._wfi_interval_ms.setValue(200)

        self._wfi_use_region = QCheckBox("Use region")
        self._wfi_region_x = QSpinBox()
        self._wfi_region_x.setRange(0, 100000)
        self._wfi_region_y = QSpinBox()
        self._wfi_region_y.setRange(0, 100000)
        self._wfi_region_w = QSpinBox()
        self._wfi_region_w.setRange(0, 100000)
        self._wfi_region_h = QSpinBox()
        self._wfi_region_h.setRange(0, 100000)

        wfi_region_row = QHBoxLayout()
        wfi_region_row.addWidget(QLabel("X"))
        wfi_region_row.addWidget(self._wfi_region_x)
        wfi_region_row.addWidget(QLabel("Y"))
        wfi_region_row.addWidget(self._wfi_region_y)
        wfi_region_row.addWidget(QLabel("W"))
        wfi_region_row.addWidget(self._wfi_region_w)
        wfi_region_row.addWidget(QLabel("H"))
        wfi_region_row.addWidget(self._wfi_region_h)
        wfi_region_w = QWidget()
        wfi_region_w.setLayout(wfi_region_row)

        self._wait_for_image_page = QWidget()
        l = QFormLayout(self._wait_for_image_page)
        l.addRow("Image", wfi_path_w)
        l.addRow("Confidence", self._wfi_confidence)
        l.addRow("Timeout (ms, 0=inf)", self._wfi_timeout_ms)
        l.addRow("Check Interval (ms)", self._wfi_interval_ms)
        l.addRow(self._wfi_use_region)
        l.addRow(wfi_region_w)
        self._wfi_browse.clicked.connect(self._browse_wfi)
        self._wfi_use_region.toggled.connect(self._sync_wfi_region_state)
        self._sync_wfi_region_state()
        self._stack.addWidget(self._wait_for_image_page)

        self._ci_value = QLineEdit()
        self._ci_browse = QPushButton("Browse")
        ci_path_row = QHBoxLayout()
        ci_path_row.addWidget(self._ci_value, 1)
        ci_path_row.addWidget(self._ci_browse)
        ci_path_w = QWidget()
        ci_path_w.setLayout(ci_path_row)

        self._ci_button = QComboBox()
        self._ci_button.addItems(["left", "right", "middle"])

        self._ci_confidence = QDoubleSpinBox()
        self._ci_confidence.setRange(0.0, 1.0)
        self._ci_confidence.setDecimals(2)
        self._ci_confidence.setSingleStep(0.05)
        self._ci_confidence.setValue(0.9)

        self._ci_timeout_ms = QSpinBox()
        self._ci_timeout_ms.setRange(0, 3600000)
        self._ci_timeout_ms.setValue(0)

        self._ci_interval_ms = QSpinBox()
        self._ci_interval_ms.setRange(10, 60000)
        self._ci_interval_ms.setValue(200)

        self._ci_use_region = QCheckBox("Use region")
        self._ci_region_x = QSpinBox()
        self._ci_region_x.setRange(0, 100000)
        self._ci_region_y = QSpinBox()
        self._ci_region_y.setRange(0, 100000)
        self._ci_region_w = QSpinBox()
        self._ci_region_w.setRange(0, 100000)
        self._ci_region_h = QSpinBox()
        self._ci_region_h.setRange(0, 100000)

        ci_region_row = QHBoxLayout()
        ci_region_row.addWidget(QLabel("X"))
        ci_region_row.addWidget(self._ci_region_x)
        ci_region_row.addWidget(QLabel("Y"))
        ci_region_row.addWidget(self._ci_region_y)
        ci_region_row.addWidget(QLabel("W"))
        ci_region_row.addWidget(self._ci_region_w)
        ci_region_row.addWidget(QLabel("H"))
        ci_region_row.addWidget(self._ci_region_h)
        ci_region_w = QWidget()
        ci_region_w.setLayout(ci_region_row)

        self._click_image_page = QWidget()
        l = QFormLayout(self._click_image_page)
        l.addRow("Image", ci_path_w)
        l.addRow("Button", self._ci_button)
        l.addRow("Confidence", self._ci_confidence)
        l.addRow("Timeout (ms, 0=inf)", self._ci_timeout_ms)
        l.addRow("Check Interval (ms)", self._ci_interval_ms)
        l.addRow(self._ci_use_region)
        l.addRow(ci_region_w)
        self._ci_browse.clicked.connect(self._browse_ci)
        self._ci_use_region.toggled.connect(self._sync_ci_region_state)
        self._sync_ci_region_state()
        self._stack.addWidget(self._click_image_page)

    def _apply_initial(self, initial: dict[str, Any] | None) -> None:
        if not initial:
            return

        t = str(initial.get("type", ""))
        if t:
            self._set_selected_action_type(t)

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

        elif t in ("key_press", "key_down", "key_up"):
            self._key_text.setText(str(initial.get("key", "")))

        elif t == "type_text":
            self._type_text_text.setText(str(initial.get("text", "")))
            self._type_text_interval_ms.setValue(int(initial.get("interval_ms", 0) or 0))

        elif t == "hotkey":
            keys = initial.get("keys")
            if isinstance(keys, list):
                self._hotkey_keys.setText("+".join(str(k) for k in keys))
            else:
                self._hotkey_keys.setText(str(keys or ""))

        elif t in ("mouse_down", "mouse_up"):
            b = str(initial.get("button", "left"))
            i = self._mouse_button.findText(b)
            if i >= 0:
                self._mouse_button.setCurrentIndex(i)
            x = initial.get("x")
            y = initial.get("y")
            if (x is not None) and (y is not None):
                self._mouse_at_pos.setChecked(True)
                self._mouse_x.setValue(int(x))
                self._mouse_y.setValue(int(y))
            else:
                self._mouse_at_pos.setChecked(False)

        elif t == "move_mouse_rel":
            self._move_rel_dx.setValue(int(initial.get("dx", 0) or 0))
            self._move_rel_dy.setValue(int(initial.get("dy", 0) or 0))
            self._move_rel_duration.setValue(max(0.0, float(initial.get("duration_ms", 0) or 0) / 1000.0))

        elif t == "drag_to":
            self._drag_x.setValue(int(initial.get("x", 0) or 0))
            self._drag_y.setValue(int(initial.get("y", 0) or 0))
            b = str(initial.get("button", "left"))
            i = self._drag_button.findText(b)
            if i >= 0:
                self._drag_button.setCurrentIndex(i)
            self._drag_duration.setValue(max(0.0, float(initial.get("duration_ms", 0) or 0) / 1000.0))

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

        elif t == "wait_for_image":
            self._wfi_value.setText(str(initial.get("value", "")))
            self._wfi_confidence.setValue(float(initial.get("confidence", 0.9) or 0.9))
            self._wfi_timeout_ms.setValue(int(initial.get("timeout_ms", 0) or 0))
            self._wfi_interval_ms.setValue(int(initial.get("interval_ms", 200) or 200))

            region = initial.get("region")
            if isinstance(region, (list, tuple)) and len(region) == 4:
                self._wfi_use_region.setChecked(True)
                self._wfi_region_x.setValue(int(region[0]))
                self._wfi_region_y.setValue(int(region[1]))
                self._wfi_region_w.setValue(int(region[2]))
                self._wfi_region_h.setValue(int(region[3]))
            else:
                self._wfi_use_region.setChecked(False)

        elif t == "click_image":
            self._ci_value.setText(str(initial.get("value", "")))
            b = str(initial.get("button", "left"))
            i = self._ci_button.findText(b)
            if i >= 0:
                self._ci_button.setCurrentIndex(i)

            self._ci_confidence.setValue(float(initial.get("confidence", 0.9) or 0.9))
            self._ci_timeout_ms.setValue(int(initial.get("timeout_ms", 0) or 0))
            self._ci_interval_ms.setValue(int(initial.get("interval_ms", 200) or 200))

            region = initial.get("region")
            if isinstance(region, (list, tuple)) and len(region) == 4:
                self._ci_use_region.setChecked(True)
                self._ci_region_x.setValue(int(region[0]))
                self._ci_region_y.setValue(int(region[1]))
                self._ci_region_w.setValue(int(region[2]))
                self._ci_region_h.setValue(int(region[3]))
            else:
                self._ci_use_region.setChecked(False)

        post = initial.get("post_action")
        if self._allow_post_action and isinstance(post, dict):
            self._post_action = post
            self._post_enabled.setChecked(True)
            self._post_summary.setText(self._format_action_inline(post))

    def _sync_stack(self) -> None:
        t = self._selected_action_type()
        if not t:
            t = "click"

        is_fav = t in self._favorite_types
        self._favorite_toggle.setText("Unfavorite" if is_fav else "Favorite")

        desc = ""
        for d in self._action_defs:
            if d["type"] == t:
                desc = f"{d['label']}  —  {d['description']}"
                break
        self._action_desc.setText(desc)

        mapping = {
            "click": 0,
            "click_at": 1,
            "key_press": 2,
            "key_down": 2,
            "key_up": 2,
            "wait": 3,
            "wait_random": 4,
            "move_mouse": 5,
            "scroll": 6,
            "type_text": 7,
            "hotkey": 8,
            "mouse_down": 9,
            "mouse_up": 9,
            "move_mouse_rel": 10,
            "drag_to": 11,
            "wait_for_image": 12,
            "click_image": 13,
        }
        self._stack.setCurrentIndex(mapping.get(t, 0))
        self._update_preview()

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
        self._update_preview()

    def _pick_post_action(self) -> None:
        dlg = ActionDialog(self, title="Post Action", initial=self._post_action, allow_post_action=False)
        action = dlg.get_action()
        if action is None:
            return
        self._post_action = action
        self._post_summary.setText(self._format_action_inline(action))
        self._update_preview()

    def _clear_post_action(self) -> None:
        self._post_action = None
        if self._allow_post_action:
            self._post_summary.setText("")
        self._update_preview()

    def _build_action_dict(self) -> dict[str, Any]:
        t = self._selected_action_type() or "click"
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

        elif t in ("key_press", "key_down", "key_up"):
            key = (self._key_text.text() or "").strip()
            if not key:
                raise ValueError("key is required")
            action = {"type": t, "key": key}

        elif t == "type_text":
            text = self._type_text_text.text()
            action = {
                "type": "type_text",
                "text": str(text),
                "interval_ms": int(self._type_text_interval_ms.value()),
            }

        elif t == "hotkey":
            keys = (self._hotkey_keys.text() or "").strip()
            if not keys:
                raise ValueError("keys are required")
            action = {"type": "hotkey", "keys": keys}

        elif t == "wait":
            ms = self._duration_to_ms(self._wait_value.value(), self._wait_unit.currentText())
            action = {"type": "wait", "duration_ms": int(ms)}

        elif t == "wait_random":
            min_ms = self._duration_to_ms(self._waitr_min.value(), self._waitr_unit.currentText())
            max_ms = self._duration_to_ms(self._waitr_max.value(), self._waitr_unit.currentText())
            action = {"type": "wait_random", "min_ms": int(min_ms), "max_ms": int(max_ms)}

        elif t in ("mouse_down", "mouse_up"):
            action = {"type": t, "button": self._mouse_button.currentText()}
            if self._mouse_at_pos.isChecked():
                action["x"] = int(self._mouse_x.value())
                action["y"] = int(self._mouse_y.value())

        elif t == "move_mouse":
            action = {
                "type": "move_mouse",
                "x": int(self._move_x.value()),
                "y": int(self._move_y.value()),
                "duration_ms": int(round(float(self._move_duration.value()) * 1000.0)),
            }

        elif t == "move_mouse_rel":
            action = {
                "type": "move_mouse_rel",
                "dx": int(self._move_rel_dx.value()),
                "dy": int(self._move_rel_dy.value()),
                "duration_ms": int(round(float(self._move_rel_duration.value()) * 1000.0)),
            }

        elif t == "drag_to":
            action = {
                "type": "drag_to",
                "x": int(self._drag_x.value()),
                "y": int(self._drag_y.value()),
                "button": self._drag_button.currentText(),
                "duration_ms": int(round(float(self._drag_duration.value()) * 1000.0)),
            }

        elif t == "scroll":
            action = {"type": "scroll", "amount": int(self._scroll_amount.value())}
            if self._scroll_anchor.isChecked():
                pos = pyautogui.position()
                action["x"] = int(pos.x)
                action["y"] = int(pos.y)

        elif t == "wait_for_image":
            value = (self._wfi_value.text() or "").strip()
            if not value:
                raise ValueError("image is required")
            action = {
                "type": "wait_for_image",
                "value": value,
                "confidence": float(self._wfi_confidence.value()),
                "timeout_ms": int(self._wfi_timeout_ms.value()),
                "interval_ms": int(self._wfi_interval_ms.value()),
            }
            if self._wfi_use_region.isChecked():
                action["region"] = [
                    int(self._wfi_region_x.value()),
                    int(self._wfi_region_y.value()),
                    int(self._wfi_region_w.value()),
                    int(self._wfi_region_h.value()),
                ]

        elif t == "click_image":
            value = (self._ci_value.text() or "").strip()
            if not value:
                raise ValueError("image is required")
            action = {
                "type": "click_image",
                "value": value,
                "button": self._ci_button.currentText(),
                "confidence": float(self._ci_confidence.value()),
                "timeout_ms": int(self._ci_timeout_ms.value()),
                "interval_ms": int(self._ci_interval_ms.value()),
            }
            if self._ci_use_region.isChecked():
                action["region"] = [
                    int(self._ci_region_x.value()),
                    int(self._ci_region_y.value()),
                    int(self._ci_region_w.value()),
                    int(self._ci_region_h.value()),
                ]

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
        if t == "key_down":
            return f"Key Down ({action.get('key', '')})"
        if t == "key_up":
            return f"Key Up ({action.get('key', '')})"
        if t == "type_text":
            text = str(action.get("text", ""))
            text = text.replace("\n", "\\n")
            if len(text) > 20:
                text = text[:20] + "..."
            return f"Type Text ({text})"
        if t == "hotkey":
            keys = action.get("keys")
            if isinstance(keys, list):
                keys_s = "+".join(str(k) for k in keys)
            else:
                keys_s = str(keys or "")
            return f"Hotkey ({keys_s})"
        if t == "wait":
            return f"Wait ({action.get('duration_ms', 0)} ms)"
        if t == "wait_random":
            return f"Random Wait ({action.get('min_ms', 0)}-{action.get('max_ms', 0)} ms)"
        if t == "mouse_down":
            base = f"Mouse Down ({action.get('button', 'left')})"
            if action.get("x") is not None and action.get("y") is not None:
                base += f" at ({action.get('x')}, {action.get('y')})"
            return base
        if t == "mouse_up":
            base = f"Mouse Up ({action.get('button', 'left')})"
            if action.get("x") is not None and action.get("y") is not None:
                base += f" at ({action.get('x')}, {action.get('y')})"
            return base
        if t == "move_mouse":
            return f"Move Mouse ({action.get('x', 0)}, {action.get('y', 0)})"
        if t == "move_mouse_rel":
            return f"Move Mouse Rel ({action.get('dx', 0)}, {action.get('dy', 0)})"
        if t == "drag_to":
            return f"Drag To ({action.get('x', 0)}, {action.get('y', 0)})"
        if t == "scroll":
            return f"Scroll ({action.get('amount', 0)})"
        if t == "wait_for_image":
            return f"Wait For Image ({action.get('value', '')})"
        if t == "click_image":
            return f"Click Image ({action.get('value', '')})"
        return json.dumps(action)

    def _fill_click_at_from_mouse(self) -> None:
        pos = pyautogui.position()
        self._click_at_x.setValue(int(pos.x))
        self._click_at_y.setValue(int(pos.y))

    def _fill_move_from_mouse(self) -> None:
        pos = pyautogui.position()
        self._move_x.setValue(int(pos.x))
        self._move_y.setValue(int(pos.y))

    def _sync_mouse_pos_state(self) -> None:
        enabled = self._mouse_at_pos.isChecked()
        self._mouse_x.setEnabled(enabled)
        self._mouse_y.setEnabled(enabled)
        self._mouse_use_mouse.setEnabled(enabled)

    def _fill_mouse_from_mouse(self) -> None:
        pos = pyautogui.position()
        self._mouse_x.setValue(int(pos.x))
        self._mouse_y.setValue(int(pos.y))

    def _fill_drag_from_mouse(self) -> None:
        pos = pyautogui.position()
        self._drag_x.setValue(int(pos.x))
        self._drag_y.setValue(int(pos.y))

    def _sync_wfi_region_state(self) -> None:
        enabled = self._wfi_use_region.isChecked()
        self._wfi_region_x.setEnabled(enabled)
        self._wfi_region_y.setEnabled(enabled)
        self._wfi_region_w.setEnabled(enabled)
        self._wfi_region_h.setEnabled(enabled)

    def _sync_ci_region_state(self) -> None:
        enabled = self._ci_use_region.isChecked()
        self._ci_region_x.setEnabled(enabled)
        self._ci_region_y.setEnabled(enabled)
        self._ci_region_w.setEnabled(enabled)
        self._ci_region_h.setEnabled(enabled)

    def _browse_wfi(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self, "Select Image", "", "Images (*.png *.jpg *.jpeg *.bmp);;All Files (*)"
        )
        if path:
            self._wfi_value.setText(path)

    def _browse_ci(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self, "Select Image", "", "Images (*.png *.jpg *.jpeg *.bmp);;All Files (*)"
        )
        if path:
            self._ci_value.setText(path)


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
        self._action_type.addItems(
            [
                "click",
                "click_at",
                "key_press",
                "key_down",
                "key_up",
                "type_text",
                "hotkey",
                "mouse_down",
                "mouse_up",
                "move_mouse",
                "move_mouse_rel",
                "drag_to",
                "scroll",
                "wait",
                "wait_random",
                "wait_for_image",
                "click_image",
            ]
        )

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
        if t == "key_down":
            base = f"Key Down ({action.get('key', '')})"
            return self._append_post_action(base, action)
        if t == "key_up":
            base = f"Key Up ({action.get('key', '')})"
            return self._append_post_action(base, action)
        if t == "type_text":
            text = str(action.get("text", ""))
            text = text.replace("\n", "\\n")
            if len(text) > 20:
                text = text[:20] + "..."
            base = f"Type Text ({text})"
            return self._append_post_action(base, action)
        if t == "hotkey":
            keys = action.get("keys")
            if isinstance(keys, list):
                keys_s = "+".join(str(k) for k in keys)
            else:
                keys_s = str(keys or "")
            base = f"Hotkey ({keys_s})"
            return self._append_post_action(base, action)
        if t == "mouse_down":
            base = f"Mouse Down ({action.get('button', 'left')})"
            if action.get("x") is not None and action.get("y") is not None:
                base += f" at ({action.get('x')}, {action.get('y')})"
            return self._append_post_action(base, action)
        if t == "mouse_up":
            base = f"Mouse Up ({action.get('button', 'left')})"
            if action.get("x") is not None and action.get("y") is not None:
                base += f" at ({action.get('x')}, {action.get('y')})"
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
        if t == "move_mouse_rel":
            base = (
                f"Move Mouse Rel ({action.get('dx', 0)}, {action.get('dy', 0)})"
                f" ({action.get('duration_ms', 0)} ms)"
            )
            return self._append_post_action(base, action)
        if t == "drag_to":
            base = (
                f"Drag To ({action.get('x', 0)}, {action.get('y', 0)})"
                f" ({action.get('button', 'left')}) ({action.get('duration_ms', 0)} ms)"
            )
            return self._append_post_action(base, action)
        if t == "scroll":
            amount = action.get('amount', 0)
            if action.get('x') is not None and action.get('y') is not None:
                base = f"Scroll ({amount}) at ({action.get('x')}, {action.get('y')})"
                return self._append_post_action(base, action)
            base = f"Scroll ({amount})"
            return self._append_post_action(base, action)
        if t == "wait_for_image":
            base = f"Wait For Image ({action.get('value', '')})"
            return self._append_post_action(base, action)
        if t == "click_image":
            base = f"Click Image ({action.get('value', '')})"
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
        if t == "key_down":
            return f"Key Down ({action.get('key', '')})"
        if t == "key_up":
            return f"Key Up ({action.get('key', '')})"
        if t == "type_text":
            text = str(action.get("text", ""))
            text = text.replace("\n", "\\n")
            if len(text) > 20:
                text = text[:20] + "..."
            return f"Type Text ({text})"
        if t == "hotkey":
            keys = action.get("keys")
            if isinstance(keys, list):
                keys_s = "+".join(str(k) for k in keys)
            else:
                keys_s = str(keys or "")
            return f"Hotkey ({keys_s})"
        if t == "wait":
            return f"Wait ({action.get('duration_ms', 0)} ms)"
        if t == "wait_random":
            return f"Random Wait ({action.get('min_ms', 0)}-{action.get('max_ms', 0)} ms)"
        if t == "mouse_down":
            base = f"Mouse Down ({action.get('button', 'left')})"
            if action.get("x") is not None and action.get("y") is not None:
                base += f" at ({action.get('x')}, {action.get('y')})"
            return base
        if t == "mouse_up":
            base = f"Mouse Up ({action.get('button', 'left')})"
            if action.get("x") is not None and action.get("y") is not None:
                base += f" at ({action.get('x')}, {action.get('y')})"
            return base
        if t == "move_mouse":
            return f"Move Mouse ({action.get('x', 0)}, {action.get('y', 0)})"
        if t == "move_mouse_rel":
            return f"Move Mouse Rel ({action.get('dx', 0)}, {action.get('dy', 0)})"
        if t == "drag_to":
            return f"Drag To ({action.get('x', 0)}, {action.get('y', 0)})"
        if t == "scroll":
            return f"Scroll ({action.get('amount', 0)})"
        if t == "wait_for_image":
            return f"Wait For Image ({action.get('value', '')})"
        if t == "click_image":
            return f"Click Image ({action.get('value', '')})"
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

            try:
                if hasattr(self._keyboard, "unhook_all_hotkeys"):
                    self._keyboard.unhook_all_hotkeys()
                elif hasattr(self._keyboard, "clear_all_hotkeys"):
                    self._keyboard.clear_all_hotkeys()
            except Exception:
                pass

            try:
                if hasattr(self._keyboard, "unhook_all"):
                    self._keyboard.unhook_all()
            except Exception:
                pass
        except Exception:
            pass
        finally:
            self._hotkey_toggle_id = None
            self._hotkey_stop_id = None
            self._keyboard = None
