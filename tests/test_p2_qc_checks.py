"""
tests/test_p2_qc_checks.py
----------------------------
Unit tests for Priority 2A — Quality Control (QC) module.
Tests all four QC checks:
1. Jacobian determinant check
2. CBF physiological range check
3. Motion parameter threshold check
4. SNR check on ASL difference images
5. QC matrix HTML/JSON report rendering
"""
from __future__ import annotations

import numpy as np
import pytest

from pyasl.qc.checks import (
    QCResult,
    check_jacobian,
    check_cbf_range,
    check_motion,
    check_snr,
)
from pyasl.qc.report import render_qc_matrix, qc_results_to_json


# ======================================================================
# 1. Jacobian determinant check
# ======================================================================

class TestJacobianCheck:
    def test_rigid_identity_affine_passes(self):
        affine = np.eye(4)
        res = check_jacobian(affine)
        assert res.passed is True
        assert res.level == "pass"
        assert res.value == pytest.approx(1.0)
        assert res.check == "jacobian"

    def test_excessive_scaling_fails(self):
        affine = np.eye(4)
        affine[0, 0] = 1.5  # det = 1.5 > 1.2
        res = check_jacobian(affine)
        assert res.passed is False
        assert res.level == "fail"

    def test_invalid_shape_raises(self):
        with pytest.raises(ValueError, match="4×4"):
            check_jacobian(np.eye(3))


# ======================================================================
# 2. CBF physiological range check
# ======================================================================

class TestCBFRangeCheck:
    def test_normal_cbf_range_passes(self):
        cbf = np.full((10, 10, 10), 60.0, dtype=np.float32)
        res = check_cbf_range(cbf, min_val=0, max_val=200, outlier_threshold_pct=5.0)
        assert res.passed is True
        assert res.level == "pass"
        assert res.details["pct_outlier_voxels"] == 0.0

    def test_high_outlier_count_fails(self):
        cbf = np.full((100, 1), 60.0, dtype=np.float32)
        cbf[:10] = 300.0  # 10% outliers (> 5%)
        res = check_cbf_range(cbf, min_val=0, max_val=200, outlier_threshold_pct=5.0)
        assert res.passed is False
        assert res.level == "fail"
        assert res.details["pct_outlier_voxels"] == 10.0

    def test_with_brain_mask(self):
        cbf = np.array([50.0, 500.0], dtype=np.float32)  # 500 is outlier
        mask = np.array([1, 0], dtype=np.uint8)          # ignore outlier
        res = check_cbf_range(cbf, brain_mask=mask)
        assert res.passed is True
        assert res.details["total_voxels"] == 1


# ======================================================================
# 3. Motion parameter threshold check
# ======================================================================

class TestMotionCheck:
    def test_low_motion_passes(self):
        # 5 volumes, tiny translations and rotations
        motion = np.zeros((5, 6))
        motion[:, 0] = 0.1  # tx = 0.1 mm
        res = check_motion(motion, translation_threshold_mm=0.5, rotation_threshold_deg=0.5)
        assert res.passed is True
        assert res.level == "pass"
        assert res.details["n_flagged_volumes"] == 0

    def test_high_motion_flags_volumes(self):
        motion = np.zeros((5, 6))
        motion[1, 0] = 0.8  # tx = 0.8 mm > 0.5 mm
        motion[3, 4] = 1.0  # ry = 1.0 deg > 0.5 deg
        res = check_motion(motion, translation_threshold_mm=0.5, rotation_threshold_deg=0.5)
        assert res.passed is False
        assert res.details["n_flagged_volumes"] == 2
        assert res.details["flagged_indices"] == [1, 3]

    def test_invalid_shape_raises(self):
        with pytest.raises(ValueError):
            check_motion(np.zeros((5, 5)))


# ======================================================================
# 4. SNR check on ASL difference images
# ======================================================================

class TestSNRCheck:
    def test_high_snr_passes(self):
        rng = np.random.RandomState(42)
        control = rng.normal(100, 1, (10, 10, 10))
        label = rng.normal(50, 1, (10, 10, 10))
        # diff mean ≈ 50, std ≈ sqrt(2) ≈ 1.41 → SNR ≈ 35
        res = check_snr(control, label, snr_warn_threshold=5.0)
        assert res.passed is True
        assert res.level == "pass"
        assert res.value > 5.0

    def test_low_snr_warns(self):
        rng = np.random.RandomState(42)
        control = rng.normal(100, 10, (10, 10, 10))
        label = rng.normal(99, 10, (10, 10, 10))
        # diff mean ≈ 1, std ≈ 14.1 → SNR ≈ 0.07 < 5.0
        res = check_snr(control, label, snr_warn_threshold=5.0)
        assert res.passed is False
        assert res.level == "warn"

    def test_shape_mismatch_raises(self):
        with pytest.raises(ValueError):
            check_snr(np.zeros((10, 10)), np.zeros((10, 12)))


# ======================================================================
# 5. QC Matrix HTML/JSON report
# ======================================================================

class TestQCReport:
    def test_render_qc_matrix(self):
        subj1_res = [
            QCResult(check="jacobian", passed=True, level="pass", value=1.0, threshold="det in [0.8, 1.2]"),
            QCResult(check="cbf_range", passed=False, level="fail", value=12.0, threshold="outlier < 5%"),
        ]
        subjects = ["sub-01"]
        qc_map = {"sub-01": subj1_res}

        html_out = render_qc_matrix(subjects, qc_map)
        assert "Quality Control Matrix" in html_out
        assert "sub-01" in html_out
        assert "qc-pass" in html_out
        assert "qc-fail" in html_out

    def test_qc_results_to_json(self):
        subj1_res = [
            QCResult(check="jacobian", passed=True, level="pass", value=1.0, threshold="det in [0.8, 1.2]"),
        ]
        qc_map = {"sub-01": subj1_res}
        json_dict = qc_results_to_json(qc_map)
        assert "sub-01" in json_dict
        assert json_dict["sub-01"][0]["check"] == "jacobian"
