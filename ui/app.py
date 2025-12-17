from PySide6.QtCore import QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QTabWidget

from PyMacroStudio.core.macro_engine import MacroEngine
from PyMacroStudio.core.settings import load_settings, save_settings
from PyMacroStudio.ui.advanced_mode import AdvancedModeWidget
from PyMacroStudio.ui.first_run import ensure_access_key, ensure_terms_accepted, maybe_show_discord_prompt
from PyMacroStudio.ui.simple_mode import SimpleModeWidget


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("PyMacro Studio")
        self.resize(980, 720)

        self._settings = load_settings()

        updated = ensure_terms_accepted(self, self._settings)
        if updated is None:
            QTimer.singleShot(0, lambda: (QApplication.instance() and QApplication.instance().quit()))
            return
        if updated != self._settings:
            self._settings = updated
            save_settings(self._settings)

        updated = ensure_access_key(self, self._settings)
        if updated is None:
            QTimer.singleShot(0, lambda: (QApplication.instance() and QApplication.instance().quit()))
            return
        if updated != self._settings:
            self._settings = updated
            save_settings(self._settings)

        self._engine = MacroEngine()
        self._simple_mode = SimpleModeWidget(self._engine, self._settings)
        self._advanced_mode = AdvancedModeWidget(self._engine, self._settings)

        tabs = QTabWidget()
        tabs.addTab(self._simple_mode, "Simple")
        tabs.addTab(self._advanced_mode, "Advanced")
        self.setCentralWidget(tabs)

        self._status_label = QLabel()
        self.statusBar().addPermanentWidget(self._status_label)

        self._status_timer = QTimer(self)
        self._status_timer.setInterval(200)
        self._status_timer.timeout.connect(self._sync_status)
        self._status_timer.start()
        self._sync_status()

        QTimer.singleShot(0, self._maybe_show_discord)

    def _maybe_show_discord(self) -> None:
        updated = maybe_show_discord_prompt(self, self._settings)
        if updated != self._settings:
            self._settings = updated
            save_settings(self._settings)

    def _sync_status(self) -> None:
        if self._engine.is_running:
            self._status_label.setText("Status: Running")
        else:
            self._status_label.setText("Status: Idle")

    def closeEvent(self, event: QCloseEvent) -> None:
        try:
            self._status_timer.stop()
        except Exception:
            pass
        try:
            self._advanced_mode.cleanup()
        except Exception:
            pass
        self._simple_mode.cleanup()
        self._engine.shutdown()
        super().closeEvent(event)
