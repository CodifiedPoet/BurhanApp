#!/usr/bin/env python3
"""Launcher for BurhanApp (PySide6 / Qt6 version)."""

import sys
import os

# Ensure the src directory is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import qInstallMessageHandler, QtMsgType
from scanmaker.qt_app import BurhanApp


def _qt_message_handler(mode, context, message):
    """Suppress harmless Qt font warnings."""
    if "Point size" in message and "must be greater than 0" in message:
        return
    if mode == QtMsgType.QtWarningMsg:
        print(f"Qt Warning: {message}")
    elif mode == QtMsgType.QtCriticalMsg:
        print(f"Qt Critical: {message}")
    elif mode == QtMsgType.QtFatalMsg:
        print(f"Qt Fatal: {message}")


def main():
    qInstallMessageHandler(_qt_message_handler)
    app = QApplication(sys.argv)
    window = BurhanApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
