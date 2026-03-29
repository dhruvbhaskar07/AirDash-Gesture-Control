#!/usr/bin/env python3
"""Smoke-test the black + dark-black Qt theme and window startup."""

import sys
import os
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from ui.main_window import MainWindow, CLR_BG, CLR_BG_ALT, CLR_CARD, CLR_BORDER, CLR_TEXT, CLR_ACCENT


def test_black_theme():
    print("Testing Black Theme Colors:")
    print(f"Background: {CLR_BG}")
    print(f"Background Alt: {CLR_BG_ALT}")
    print(f"Card: {CLR_CARD}")
    print(f"Border: {CLR_BORDER}")
    print(f"Text: {CLR_TEXT}")
    print(f"Accent: {CLR_ACCENT}")

    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()

    # Auto-close smoke test window after 2 seconds.
    QTimer.singleShot(2000, win.close)
    QTimer.singleShot(2100, app.quit)
    app.exec()

    print("Theme smoke test finished.")


if __name__ == "__main__":
    test_black_theme()
