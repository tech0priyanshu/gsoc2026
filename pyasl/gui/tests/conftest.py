import os
import sys
# pyrefly: ignore [missing-import]
import pytest
import types

# Ensure PyASL is on the Python path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Create a fixture for MainWindow using qtbot
from pyasl.gui.views.main_window import MainWindow

@pytest.fixture
def main_window(qtbot):
    """Fixture to create, show and return the MainWindow instance."""
    window = MainWindow()
    qtbot.addWidget(window)
    return window
