import sys
import os
from PySide6.QtWidgets import QApplication

# Ensure paths correctly resolve local modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ui.main_window import MainWindow

def main():
    qt_app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(qt_app.exec())

if __name__ == "__main__":
    main()
