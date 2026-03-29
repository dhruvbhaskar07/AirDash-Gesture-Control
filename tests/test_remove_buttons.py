#!/usr/bin/env python3
"""
Test script to verify remove button functionality for newly created gestures.
This script runs the application and checks if remove buttons are properly created.
"""

import sys
import os
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from ui.main_window import MainWindow

def test_remove_buttons():
    """Test that remove buttons are created for all gestures"""
    print("Testing remove button functionality...")

    qt_app = QApplication(sys.argv)
    app = MainWindow()
    app.show()
    
    # Check existing mappings
    print(f"Found {len(app.action_mapper.mappings)} existing mappings:")
    for gesture_name in app.action_mapper.mappings.keys():
        print(f"  - {gesture_name}")
    
    # Add a test gesture
    print("\nAdding test gesture...")
    app.action_mapper.add_mapping(
        "Test_Gesture", 
        ["ctrl", "t"], 
        "shortcut", 
        "Test Description"
    )
    
    # Refresh mappings to trigger UI update
    print("Refreshing mappings...")
    app.refresh_mappings()
    
    # Check if the test gesture was added
    print(f"\nAfter refresh - Found {len(app.action_mapper.mappings)} mappings:")
    for gesture_name in app.action_mapper.mappings.keys():
        print(f"  - {gesture_name}")
    
    print("\nTest completed! Check the UI quickly for remove buttons.")

    QTimer.singleShot(2500, app.close)
    QTimer.singleShot(2600, qt_app.quit)
    qt_app.exec()

    app.action_mapper.delete_mapping("Test_Gesture")
    print("Cleanup complete: Test_Gesture removed.")

if __name__ == "__main__":
    test_remove_buttons()
