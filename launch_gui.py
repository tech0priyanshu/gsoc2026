"""
launch_gui.py
-------------
Standalone GUI launcher for the PyASL Pipeline GUI.

Patches the pyasl top-level __init__.py import issue (nibabel/nipype optional
dependencies not installed) so the GUI subpackages work independently.

Usage:
    python launch_gui.py
"""
import sys
import os
import types

import multiprocessing

# Suppress duplicate TensorFlow oneDNN warnings for faster startup
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

# ----------------------------------------------------------------
# 1. Ensure PyASL is on the path
# ----------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

# ----------------------------------------------------------------
# 2. Stub out the pyasl top-level to skip nibabel/nipype imports
#    The GUI only uses pyasl.pipeline.* and pyasl.batch.* which
#    have no heavy neuroimaging dependencies.
# ----------------------------------------------------------------
if "pyasl" not in sys.modules:
    fake = types.ModuleType("pyasl")
    fake.__path__ = [os.path.join(_HERE, "pyasl")]
    fake.__package__ = "pyasl"
    fake.__spec__ = None
    sys.modules["pyasl"] = fake


import logging
from pyasl.gui.utils.log_helper import setup_app_logging
from pyasl.gui.utils.process_helper import set_process_identity

logger = logging.getLogger("pyasl.launcher")


def main():
    # Call freeze_support for multiprocessing safety on Windows
    multiprocessing.freeze_support()

    # Set process identity for main application process
    set_process_identity("PyASL")

    # Initialize application logging
    setup_app_logging()

    logger.info("Starting PyASL Pipeline GUI...")

    from pyasl.gui.app import create_app
    from pyasl.gui.views.main_window import MainWindow

    app = create_app(sys.argv)
    window = MainWindow()

    def _on_shutdown():
        logger.info("Application shutting down cleanly...")
        # Terminate active worker threads or process pools if attached to window
        try:
            if hasattr(window, "_batch_panel") and hasattr(window._batch_panel, "_controller"):
                ctrl = window._batch_panel._controller
                if hasattr(ctrl, "_worker") and ctrl._worker:
                    ctrl._worker.abort()
        except Exception as e:
            logger.debug("Error during shutdown cleanup: %s", e)

    app.aboutToQuit.connect(_on_shutdown)
    window.show()
    logger.info("GUI launched successfully! Active modules: Pipeline Builder, Batch Mode, Monitor, Settings.")
    app.exec()


if __name__ == "__main__":
    main()

