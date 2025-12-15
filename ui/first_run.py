from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from PyMacroStudio.core.settings import AppSettings


DISCORD_INVITE_URL = "https://discord.com/invite/498tyUUaBw"


def ensure_terms_accepted(parent: QWidget, settings: AppSettings) -> AppSettings | None:
    if settings.tos_accepted:
        return settings

    dlg = TermsOfServiceDialog(parent)
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return None

    return replace(settings, tos_accepted=True)


def maybe_show_discord_prompt(parent: QWidget, settings: AppSettings) -> AppSettings:
    if settings.discord_prompt_dismissed:
        return settings

    box = QMessageBox(parent)
    box.setWindowTitle("Join the Discord")
    box.setText("Want to join the Discord server for updates and support?")

    join_btn = box.addButton("Join Discord", QMessageBox.ButtonRole.AcceptRole)
    not_now_btn = box.addButton("Not now", QMessageBox.ButtonRole.RejectRole)
    dont_show_btn = box.addButton("Don't show again", QMessageBox.ButtonRole.DestructiveRole)

    box.exec()
    clicked = box.clickedButton()

    if clicked is join_btn:
        QDesktopServices.openUrl(QUrl(DISCORD_INVITE_URL))
        return replace(settings, discord_prompt_dismissed=True)

    if clicked is dont_show_btn:
        return replace(settings, discord_prompt_dismissed=True)

    _ = not_now_btn
    return settings


class TermsOfServiceDialog(QDialog):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("Terms of Service")
        self.setModal(True)

        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setPlainText(
            "PyMacro Studio - Terms of Service\n"
            "\n"
            "By using this software you agree to the following:\n"
            "\n"
            "1) You are responsible for how you use macros.\n"
            "   - Only automate things you have permission to automate.\n"
            "   - Do not use this tool to cheat, harass, or violate a service's rules/laws.\n"
            "\n"
            "2) No warranty.\n"
            "   - This software is provided 'as is' without warranties of any kind.\n"
            "   - You accept all risk for any damage, data loss, bans, or account issues.\n"
            "\n"
            "3) Ownership / attribution.\n"
            "   - The creator owns this project and its original content.\n"
            "   - If you share/redistribute it, you must give credit to the creator.\n"
            "   - Unauthorized redistribution without attribution may result in DMCA takedown requests.\n"
        )

        self._agree_checkbox = QCheckBox("I have read and agree to the Terms of Service")

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setText("I Agree")
        self._buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Exit")

        root = QVBoxLayout(self)
        root.addWidget(QLabel("You must accept these terms to use the app."))
        root.addWidget(self._text)
        root.addWidget(self._agree_checkbox)
        root.addWidget(self._buttons)

        self._buttons.accepted.connect(self._on_accept)
        self._buttons.rejected.connect(self.reject)

    def _on_accept(self) -> None:
        if not self._agree_checkbox.isChecked():
            QMessageBox.warning(self, "Required", "You must check the box to agree.")
            return
        self.accept()
