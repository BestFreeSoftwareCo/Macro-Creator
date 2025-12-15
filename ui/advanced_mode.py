import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from PyMacroStudio.core.macro_engine import MacroEngine
from PyMacroStudio.core.macro_io import MacroValidationError, load_macro_json, save_macro_json, validate_macro
from PyMacroStudio.core.paths import macros_saved_dir
from PyMacroStudio.core.settings import AppSettings


class AdvancedModeWidget(QWidget):
    def __init__(self, engine: MacroEngine, settings: AppSettings) -> None:
        super().__init__()
        self._engine = engine
        self._settings = settings
        self._cleaned_up = False
        self._last_log_seq = 0
        self._current_path: Path | None = None

        self._editor = QPlainTextEdit()
        self._editor.setPlaceholderText("Paste or write a macro JSON here...")
        self._editor.setTabStopDistance(32)

        self._logs = QPlainTextEdit()
        self._logs.setReadOnly(True)
        self._logs.setMaximumBlockCount(4000)

        self._btn_new = QPushButton("New")
        self._btn_format = QPushButton("Format")
        self._btn_validate = QPushButton("Validate")
        self._btn_run = QPushButton("Run")
        self._btn_stop = QPushButton("Stop")
        self._btn_stop.setObjectName("secondary")
        self._btn_load = QPushButton("Load")
        self._btn_load.setObjectName("secondary")
        self._btn_save = QPushButton("Save")
        self._btn_save.setObjectName("secondary")
        self._btn_save_as = QPushButton("Save As")
        self._btn_save_as.setObjectName("secondary")
        self._btn_clear_logs = QPushButton("Clear Logs")
        self._btn_clear_logs.setObjectName("secondary")

        self._build_layout()
        self._wire_events()

        self._log_timer = QTimer(self)
        self._log_timer.setInterval(75)
        self._log_timer.timeout.connect(self._drain_logs)
        self._log_timer.start()

        self._state_timer = QTimer(self)
        self._state_timer.setInterval(150)
        self._state_timer.timeout.connect(self._sync_state)
        self._state_timer.start()

        self._set_default_macro_text()

    def cleanup(self) -> None:
        if self._cleaned_up:
            return
        self._cleaned_up = True
        try:
            self._log_timer.stop()
            self._state_timer.stop()
        except Exception:
            pass

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)

        tabs = QTabWidget()
        tabs.addTab(self._build_editor_tab(), "Editor")
        tabs.addTab(self._build_logs_tab(), "Logs")
        root.addWidget(tabs)

    def _build_editor_tab(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)

        bar = QHBoxLayout()
        bar.addWidget(self._btn_new)
        bar.addWidget(self._btn_format)
        bar.addWidget(self._btn_validate)
        bar.addSpacing(12)
        bar.addWidget(self._btn_run)
        bar.addWidget(self._btn_stop)
        bar.addStretch(1)
        bar.addWidget(self._btn_load)
        bar.addWidget(self._btn_save)
        bar.addWidget(self._btn_save_as)
        l.addLayout(bar)

        box = QGroupBox("Macro JSON")
        box_l = QVBoxLayout(box)
        box_l.addWidget(self._editor)
        l.addWidget(box, 1)
        return w

    def _build_logs_tab(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)

        top = QHBoxLayout()
        top.addStretch(1)
        top.addWidget(self._btn_clear_logs)
        l.addLayout(top)

        box = QGroupBox("Logs")
        box_l = QVBoxLayout(box)
        box_l.addWidget(self._logs)
        l.addWidget(box, 1)
        return w

    def _wire_events(self) -> None:
        self._btn_new.clicked.connect(self._new_macro)
        self._btn_format.clicked.connect(self._format_json)
        self._btn_validate.clicked.connect(self._validate_current)
        self._btn_run.clicked.connect(self._run_current)
        self._btn_stop.clicked.connect(self._stop)
        self._btn_load.clicked.connect(self._load)
        self._btn_save.clicked.connect(self._save)
        self._btn_save_as.clicked.connect(lambda: self._save(save_as=True))
        self._btn_clear_logs.clicked.connect(self._logs.clear)

    def _set_default_macro_text(self) -> None:
        macro = {
            "schema_version": 1,
            "name": "Untitled Macro",
            "hotkeys": {"start_stop": self._settings.default_start_stop_hotkey, "stop": self._settings.default_stop_hotkey},
            "settings": {"repeat": 1, "max_steps": int(self._settings.max_steps)},
            "actions": [],
        }
        self._editor.setPlainText(json.dumps(macro, indent=2))

    def _parse_editor_json(self) -> dict[str, Any]:
        raw = self._editor.toPlainText()
        try:
            data = json.loads(raw)
        except Exception as e:
            raise MacroValidationError(f"Invalid JSON: {type(e).__name__}: {e}")
        if not isinstance(data, dict):
            raise MacroValidationError("Macro JSON must be an object")
        return data

    def _new_macro(self) -> None:
        if self._engine.is_running:
            return
        self._current_path = None
        self._set_default_macro_text()

    def _format_json(self) -> None:
        try:
            data = self._parse_editor_json()
        except MacroValidationError as e:
            QMessageBox.warning(self, "Invalid JSON", str(e))
            return
        self._editor.setPlainText(json.dumps(data, indent=2))

    def _validate_current(self) -> None:
        try:
            macro = self._parse_editor_json()
            validate_macro(macro)
        except MacroValidationError as e:
            QMessageBox.warning(self, "Invalid macro", str(e))
            return
        QMessageBox.information(self, "Valid", "Macro is valid.")

    def _run_current(self) -> None:
        if self._engine.is_running:
            return
        try:
            macro = self._parse_editor_json()
            validate_macro(macro)
        except MacroValidationError as e:
            QMessageBox.warning(self, "Invalid macro", str(e))
            return
        if not macro.get("actions"):
            QMessageBox.information(self, "No actions", "Add at least one action.")
            return
        self._engine.start(macro)

    def _stop(self) -> None:
        self._engine.stop()

    def _load(self) -> None:
        if self._engine.is_running:
            return
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
        self._current_path = path
        self._editor.setPlainText(json.dumps(macro, indent=2))

    def _save(self, save_as: bool = False) -> None:
        if self._engine.is_running:
            return
        try:
            macro = self._parse_editor_json()
            validate_macro(macro)
        except MacroValidationError as e:
            QMessageBox.warning(self, "Invalid macro", str(e))
            return

        if save_as or self._current_path is None:
            start_dir = macros_saved_dir()
            start_dir.mkdir(parents=True, exist_ok=True)
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Save Macro",
                str(start_dir / "macro.json"),
                "Macro JSON (*.json);;All Files (*.*)",
            )
            if not file_path:
                return
            path = Path(file_path)
        else:
            path = self._current_path

        try:
            save_macro_json(path, macro)
        except Exception as e:
            QMessageBox.critical(self, "Save failed", f"{type(e).__name__}: {e}")
            return
        self._current_path = path
        self._editor.setPlainText(json.dumps(macro, indent=2))

    def _drain_logs(self) -> None:
        last, messages = self._engine.read_logs(self._last_log_seq)
        if messages:
            for msg in messages:
                self._logs.appendPlainText(msg)
            self._last_log_seq = last

    def _sync_state(self) -> None:
        running = self._engine.is_running
        self._btn_run.setEnabled(not running)
        self._btn_stop.setEnabled(running)

        self._btn_new.setEnabled(not running)
        self._btn_format.setEnabled(not running)
        self._btn_validate.setEnabled(not running)
        self._btn_load.setEnabled(not running)
        self._btn_save.setEnabled(not running)
        self._btn_save_as.setEnabled(not running)


def _placeholder_tab(text: str) -> QWidget:
    w = QWidget()
    l = QVBoxLayout(w)
    label = QLabel(text)
    label.setStyleSheet("color: #6B7280; font-size: 14px;")
    l.addStretch(1)
    l.addWidget(label)
    l.addStretch(2)
    return w
