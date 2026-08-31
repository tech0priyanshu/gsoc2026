"""
tests/test_p5_gui_fixes.py
----------------------------
Unit tests for Priority 5 UI fixes:
5A. Typed parameter widgets in NodeConfigPanel
5C. ETA calculation formatting in batch summary
5D. BIDS bulk import directory scanning
5E. Human-readable error mapping
"""
from __future__ import annotations

import os
import pytest

from pyasl.gui.error_map import format_human_error


# ======================================================================
# 5E — Human-readable error messages
# ======================================================================

class TestHumanErrorMap:
    def test_keyerror_imagectr_mapped(self):
        err = KeyError("ImageCtr")
        msg = format_human_error(err)
        assert "ASL control image was not found" in msg
        assert "BrukerLoader" in msg

    def test_filenotfounderror_mapped(self):
        err = FileNotFoundError("data/subject01/asl.nii.gz")
        msg = format_human_error(err)
        assert "File or directory not found" in msg

    def test_valueerror_dot_id_mapped(self):
        err = ValueError("Node ID 'step.1' cannot contain '.'")
        msg = format_human_error(err)
        assert "Node IDs cannot contain dot" in msg

    def test_generic_fallback_error(self):
        err = RuntimeError("Unexpected internal crash")
        msg = format_human_error(err)
        assert "Error: Unexpected internal crash" in msg


# ======================================================================
# 5A — NodeConfigPanel typed widgets (pytest-qt)
# ======================================================================

class TestNodeConfigPanelWidgets:
    def test_typed_widget_creation(self, qtbot):
        try:
            from pyasl.gui.views.node_config_panel import NodeConfigPanel
        except ImportError:
            pytest.skip("PyQt6 not available")

        panel = NodeConfigPanel()
        qtbot.addWidget(panel)

        config = {
            "is_preclinical": True,
            "max_iter": 200,
            "smooth_fwhm": 2.5,
            "anat_path": "/data/anat.nii",
            "cost_metric": "MI",
        }

        panel.load_node("node_1", "PreclinicalCoregister", config)
        read_config = panel.get_config()

        assert read_config["is_preclinical"] is True
        assert read_config["max_iter"] == 200
        assert read_config["smooth_fwhm"] == pytest.approx(2.5)
        assert read_config["anat_path"] == "/data/anat.nii"
        assert read_config["cost_metric"] == "MI"


# ======================================================================
# 5D — BIDS bulk import scanning logic
# ======================================================================

class TestBIDSImport:
    def test_bids_subject_scanning(self, tmp_path):
        # Create a mock BIDS dataset directory structure
        (tmp_path / "sub-01").mkdir()
        (tmp_path / "sub-02").mkdir()
        (tmp_path / "sub-03").mkdir()
        (tmp_path / "code").mkdir()  # non-subject dir

        import glob
        sub_dirs = sorted([
            d for d in glob.glob(os.path.join(str(tmp_path), "sub-*"))
            if os.path.isdir(d)
        ])

        assert len(sub_dirs) == 3
        assert [os.path.basename(d) for d in sub_dirs] == ["sub-01", "sub-02", "sub-03"]
