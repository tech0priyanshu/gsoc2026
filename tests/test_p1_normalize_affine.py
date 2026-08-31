"""
tests/test_p1_normalize_affine.py
-----------------------------------
Tests for Priority 1B — affine composition correctness in normalization.
"""
from __future__ import annotations

import numpy as np
import pytest


class TestNormalizeAffineComposition:
    """Verify that PreclinicalNormalize correctly composes world-space affines."""

    def test_coreg_affine_shape_assertion(self):
        """Should raise AssertionError if CoregAffine is not 4×4."""
        from pyasl.modules.preclinical_normalize import PreclinicalNormalize

        ctx = {
            "CoregASL": np.ones((10, 10, 10), dtype=np.float32),
            "AnatAffine": np.eye(4),
            "CoregAffine": np.eye(3),  # wrong shape!
            "TemplateImage": np.ones((10, 10, 10), dtype=np.float32),
            "TemplateAffine": np.eye(4),
        }
        norm = PreclinicalNormalize()
        with pytest.raises(AssertionError, match="4×4"):
            norm.run(ctx, save_normalized=False)

    def test_identity_affines_produce_identity_composition(self):
        """When both affines are identity, source_affine should be identity."""
        from pyasl.modules.preclinical_normalize import PreclinicalNormalize

        shape = (10, 10, 10)
        ctx = {
            "CoregASL": np.ones(shape, dtype=np.float32),
            "AnatAffine": np.eye(4, dtype=np.float64),
            "CoregAffine": np.eye(4, dtype=np.float64),
            "TemplateImage": np.ones(shape, dtype=np.float32),
            "TemplateAffine": np.eye(4, dtype=np.float64),
        }
        norm = PreclinicalNormalize()
        norm.run(ctx, save_normalized=False)

        # The source_affine used internally = anat @ coreg = I @ I = I
        # With identity affines and same-shape template, output ≈ input
        assert ctx["NormalizedASL"].shape == shape
        info = ctx["NormalizationInfo"]
        source_affine = np.array(info["source_affine"])
        np.testing.assert_allclose(source_affine, np.eye(4), atol=1e-10)

    def test_world_space_composition_is_valid(self):
        """With real-valued world-space affines, composition should be correct."""
        from pyasl.modules.preclinical_normalize import PreclinicalNormalize

        shape = (10, 10, 10)
        # Anatomical affine: 0.1mm voxels
        anat_aff = np.diag([0.1, 0.1, 0.1, 1.0])
        # CoregAffine: small world-space translation (1mm, 0, 0)
        coreg_aff = np.eye(4, dtype=np.float64)
        coreg_aff[0, 3] = 1.0  # 1mm translation in x

        expected_source = anat_aff @ coreg_aff

        ctx = {
            "CoregASL": np.ones(shape, dtype=np.float32),
            "AnatAffine": anat_aff,
            "CoregAffine": coreg_aff,
            "TemplateImage": np.ones(shape, dtype=np.float32),
            "TemplateAffine": np.eye(4, dtype=np.float64),
        }
        norm = PreclinicalNormalize()
        norm.run(ctx, save_normalized=False)

        source_affine = np.array(ctx["NormalizationInfo"]["source_affine"])
        np.testing.assert_allclose(source_affine, expected_source, atol=1e-10)
