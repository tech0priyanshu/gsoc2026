"""
tests/test_p1_coregister_world.py
-----------------------------------
Tests for Priority 1A (world-coordinate registration) and 1C
(negative-value normalization).

Uses synthetic NIfTI-like data at two known voxel sizes (0.3mm and 0.1mm)
to verify the output transform is geometrically correct within tolerance.
"""
from __future__ import annotations

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Helpers — build synthetic 3-D volumes with known geometry
# ---------------------------------------------------------------------------

def _make_sphere(shape, center, radius, value=1.0):
    """Create a 3D volume with a sphere of given intensity."""
    coords = np.mgrid[0:shape[0], 0:shape[1], 0:shape[2]]
    dist = np.sqrt(sum((coords[i] - center[i])**2 for i in range(3)))
    vol = np.zeros(shape, dtype=np.float32)
    vol[dist <= radius] = value
    return vol


def _make_affine(voxel_size_mm, origin_mm=(0., 0., 0.)):
    """Build a simple diagonal affine (no rotation) from voxel size."""
    aff = np.eye(4, dtype=np.float64)
    aff[0, 0] = voxel_size_mm
    aff[1, 1] = voxel_size_mm
    aff[2, 2] = voxel_size_mm
    aff[0, 3] = origin_mm[0]
    aff[1, 3] = origin_mm[1]
    aff[2, 3] = origin_mm[2]
    return aff


# ======================================================================
# 1A — World-coordinate registration
# ======================================================================

class TestWorldCoordinateRegistration:
    """Verify that register_affine operates in world coordinates."""

    def test_register_affine_accepts_affine_args(self):
        """Signature now requires moving_affine and fixed_affine."""
        from pyasl.modules.preclinical_coregister import register_affine

        shape = (20, 20, 20)
        moving = _make_sphere(shape, (10, 10, 10), 5)
        fixed = _make_sphere(shape, (10, 10, 10), 5)
        m_aff = _make_affine(0.3)
        f_aff = _make_affine(0.1)

        registered, world_aff, rmse = register_affine(
            moving, fixed,
            moving_affine=m_aff, fixed_affine=f_aff,
        )
        assert world_aff.shape == (4, 4)
        assert registered.shape == fixed.shape

    def test_identity_registration_different_voxel_sizes(self):
        """Two aligned spheres at different voxel sizes should yield ~identity transform."""
        from pyasl.modules.preclinical_coregister import register_affine

        # Both spheres centred at world position (3mm, 3mm, 3mm)
        # ASL: 0.3mm voxels → centre at voxel (10, 10, 10)
        # Anat: 0.1mm voxels → centre at voxel (30, 30, 30)
        asl_shape = (20, 20, 20)
        anat_shape = (60, 60, 60)
        asl = _make_sphere(asl_shape, (10, 10, 10), 5, value=100.0)
        anat = _make_sphere(anat_shape, (30, 30, 30), 15, value=100.0)

        asl_aff = _make_affine(0.3)
        anat_aff = _make_affine(0.1)

        _, world_aff, _ = register_affine(
            asl, anat, moving_affine=asl_aff, fixed_affine=anat_aff,
            max_iter=100,
        )

        # For rigid registration of already-aligned data, the world
        # transform should be close to identity (small translation, no rotation)
        # The rotation part (upper-left 3×3) should be close to I
        R = world_aff[:3, :3]
        assert np.allclose(R, np.eye(3), atol=0.15), (
            f"Rotation part should be near identity, got:\n{R}"
        )

    def test_world_affine_is_4x4(self):
        """Returned affine is always 4×4."""
        from pyasl.modules.preclinical_coregister import register_affine

        shape = (16, 16, 16)
        vol = _make_sphere(shape, (8, 8, 8), 4)
        aff = _make_affine(0.2)

        _, world_aff, _ = register_affine(
            vol, vol, moving_affine=aff, fixed_affine=aff, max_iter=5,
        )
        assert world_aff.shape == (4, 4)


# ======================================================================
# 1C — Negative-value normalization
# ======================================================================

class TestNegativeValueNormalization:
    """Verify that PASL data with negative values is handled correctly."""

    def test_normalize_handles_negative_values(self):
        """_normalize_intensity should map [min, max] to [0, 1]."""
        from pyasl.modules.preclinical_coregister import _normalize_intensity

        img = np.array([-50.0, 0.0, 100.0], dtype=np.float32)
        normed, orig_min, orig_range = _normalize_intensity(img)

        assert normed.min() == pytest.approx(0.0)
        assert normed.max() == pytest.approx(1.0)
        assert orig_min == pytest.approx(-50.0)
        assert orig_range == pytest.approx(150.0)

    def test_rescale_preserves_original_range(self):
        """After registration, rescaling should recover the original data range."""
        from pyasl.modules.preclinical_coregister import _normalize_intensity

        img = np.array([-100.0, -50.0, 0.0, 50.0, 200.0], dtype=np.float32)
        normed, orig_min, orig_range = _normalize_intensity(img)

        # Simulate rescaling (as done in register_affine)
        rescaled = normed * orig_range + orig_min
        np.testing.assert_allclose(rescaled, img, atol=1e-5)

    def test_register_affine_with_negative_data(self):
        """Registration should work with PASL data containing negatives."""
        from pyasl.modules.preclinical_coregister import register_affine

        shape = (16, 16, 16)
        # PASL-like data: some negative, some positive
        rng = np.random.RandomState(42)
        moving = rng.randn(*shape).astype(np.float32) * 50 - 10  # range ~ [-160, 140]
        fixed = moving.copy()  # same data — should register trivially

        aff = _make_affine(0.3)
        registered, world_aff, rmse = register_affine(
            moving, fixed, moving_affine=aff, fixed_affine=aff, max_iter=5,
        )
        assert registered.shape == fixed.shape
        # Since moving ≈ fixed, RMSE should be small
        assert rmse < 0.5

    def test_constant_image_does_not_crash(self):
        """A zero-range image should not cause division by zero."""
        from pyasl.modules.preclinical_coregister import _normalize_intensity

        img = np.ones((5, 5, 5), dtype=np.float32) * 42.0
        normed, orig_min, orig_range = _normalize_intensity(img)
        assert np.all(normed == 0.0)  # range is 0 → all zeros
        assert orig_min == pytest.approx(42.0)
        assert orig_range == pytest.approx(0.0)


# ======================================================================
# 1A + 1C combined — PreclinicalCoregister module class
# ======================================================================

class TestPreclinicalCoregisterModule:
    """Integration test for the module class with both fixes applied."""

    def test_module_produces_world_space_affine(self):
        """CoregAffine in ctx should be world-space 4×4."""
        from pyasl.modules.preclinical_coregister import PreclinicalCoregister

        shape = (16, 16, 16)
        ctx = {
            "ImageCtr": _make_sphere(shape, (8, 8, 8), 4, value=100.0),
            "ASLAffine": _make_affine(0.3),
            "AnatImage": _make_sphere(shape, (8, 8, 8), 4, value=80.0),
            "AnatAffine": _make_affine(0.1),
            "savedir": ".",
        }

        coreg = PreclinicalCoregister()
        coreg.run(ctx, save_coreg=False)

        assert "CoregAffine" in ctx
        assert ctx["CoregAffine"].shape == (4, 4)
        assert "CoregASL" in ctx
        assert isinstance(ctx["CoregRMSE"], float)
