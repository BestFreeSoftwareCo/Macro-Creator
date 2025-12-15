import sys
from pathlib import Path


if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication

from PyMacroStudio.ui.app import MainWindow
from PyMacroStudio.ui.theme import apply_theme


def main() -> None:
    app = QApplication(sys.argv)
    apply_theme(app)
    window = MainWindow()
    window.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
