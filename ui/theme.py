from PySide6.QtWidgets import QApplication


def apply_theme(app: QApplication) -> None:
    app.setStyleSheet(
        """
        QWidget { font-size: 13px; }
        QMainWindow { background: #F6F7FB; }

        QLineEdit, QPlainTextEdit, QListWidget, QSpinBox, QComboBox {
            background: white;
            border: 1px solid #D7DAE5;
            border-radius: 10px;
            padding: 6px;
        }

        QPushButton {
            background: #4F46E5;
            color: white;
            border: none;
            border-radius: 12px;
            padding: 10px 14px;
            font-weight: 600;
        }
        QPushButton:disabled { background: #A7A3F2; }

        QPushButton#secondary {
            background: #EEF0F7;
            color: #111827;
            border: 1px solid #D7DAE5;
        }

        QGroupBox {
            border: 1px solid #D7DAE5;
            border-radius: 12px;
            margin-top: 10px;
            padding: 10px;
            background: rgba(255,255,255,0.7);
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 6px;
        }
        """
    )
