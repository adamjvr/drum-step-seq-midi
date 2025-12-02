"""
main.py

Entrypoint for the extended step sequencer application.

Usage:
    python main.py
"""

import sys
from PyQt6.QtWidgets import QApplication
from main_window import MainWindow


def main():
    """
    Standard Qt application bootstrap:

        - Create QApplication
        - Instantiate MainWindow
        - Show window
        - Enter event loop
    """
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
