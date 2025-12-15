import pyautogui


def configure_safety() -> None:
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0
