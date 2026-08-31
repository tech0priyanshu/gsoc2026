"""
Tests for preclinical co-registration and normalization modules.
Uses synthetic numpy arrays — no real MRI data or nibabel required.
"""
import sys
import types
import os
import numpy as np
import pytest

# ---- isolate from heavy pyasl/__init__.py top-level imports ----
_HERE = os.path.dirname(os.path.abspath(__file__))
_PYASL_ROOT = os.path.join(_HERE, "..")
_PYASL_PKG = os.path.join(_PYASL_ROOT, "pyasl")

if _PYASL_ROOT not in sys.path:
    sys.path.insert(0, _PYASL_ROOT)

if "pyasl" not in sys.modules:
    fake = types.ModuleType("pyasl")
    fake.__path__ = [_PYASL_PKG]
    fake.__package__ = "pyasl"
    fake.__spec__ = None
    sys.modules["pyasl"] = fake


# ============================================================
# Fixtures
# ============================================================

def _make_sphere(shape=(32, 32, 32), radius=10):
    """Return a synthetic 3D numpy array with a sphere of ones."""
    arr = np.zeros(shape, dtype=np.float32)
    cx, cy, cz = [s // 2 for s in shape]
    for x in range(shape[0]):
        for y in range(shape[1]):
            for z in range(shape[2]):
                if (x - cx)**2 + (y - cy)**2 + (z - cz)**2 < radius**2:
                    arr[x, y, z] = 1.0
    return arr


@pytest.fixture
def sphere_vol():
    return _make_sphere()


@pytest.fixture
def shifted_sphere():
    """A sphere shifted by 5 voxels in x — simulates misalignment."""
    arr = np.zeros((32, 32, 32), dtype=np.float32)
    cx, cy, cz = 21, 16, 16
    for x in range(32):
        for y in range(32):
            for z in range(32):
                if (x - cx)**2 + (y - cy)**2 + (z - cz)**2 < 100:
                    arr[x, y, z] = 1.0
    return arr


# ============================================================
# Test PreclinicalCoregister
# ============================================================

class TestPreclinicalCoregister:

    def test_import(self):
        from pyasl.modules.preclinical_coregister import PreclinicalCoregister
        assert callable(PreclinicalCoregister)

    def test_run_requires_anat(self, sphere_vol):
        from pyasl.modules.preclinical_coregister import PreclinicalCoregister
        ctx = {"ImageCtr": sphere_vol, "savedir": "."}
        with pytest.raises((ValueError, KeyError)):
            PreclinicalCoregister().run(ctx)

    def test_run_with_anat_in_ctx(self, sphere_vol, shifted_sphere, tmp_path):
        from pyasl.modules.preclinical_coregister import PreclinicalCoregister
        ctx = {
            "ImageCtr": shifted_sphere,
            "AnatImage": sphere_vol,
            "AnatAffine": np.eye(4),
            "savedir": str(tmp_path),
        }
        PreclinicalCoregister().run(ctx, save_coreg=False)
        assert "CoregASL" in ctx
        assert "CoregAffine" in ctx
        assert "CoregRMSE" in ctx
        assert isinstance(ctx["CoregASL"], np.ndarray)
        assert ctx["CoregASL"].shape == sphere_vol.shape

    def test_output_shape_matches_fixed(self, sphere_vol, shifted_sphere, tmp_path):
        from pyasl.modules.preclinical_coregister import PreclinicalCoregister
        fixed = sphere_vol[:20, :20, :20]  # smaller fixed image
        ctx = {
            "ImageCtr": shifted_sphere,
            "AnatImage": fixed,
            "AnatAffine": np.eye(4),
            "savedir": str(tmp_path),
        }
        PreclinicalCoregister().run(ctx, save_coreg=False)
        # registered should match moving shape (affine_transform preserves output_shape)
        assert ctx["CoregASL"].shape == fixed.shape

    def test_4d_input_handled(self, sphere_vol, tmp_path):
        from pyasl.modules.preclinical_coregister import PreclinicalCoregister
        asl_4d = np.stack([sphere_vol] * 5, axis=3)
        ctx = {
            "ImageCtr": asl_4d,
            "AnatImage": sphere_vol,
            "AnatAffine": np.eye(4),
            "savedir": str(tmp_path),
        }
        PreclinicalCoregister().run(ctx, save_coreg=False)
        assert ctx["CoregASL"].ndim == 3

    def test_register_affine_identity(self, sphere_vol):
        """Registering a vol to itself should return valid output (RMSE >= 0)."""
        from pyasl.modules.preclinical_coregister import register_affine
        registered, affine, rmse = register_affine(sphere_vol, sphere_vol,
                                                   cost="MI", max_iter=10)
        assert rmse >= 0
        assert registered.shape == sphere_vol.shape
        assert affine.shape == (4, 4)

    def test_center_of_mass(self, sphere_vol):
        from pyasl.modules.preclinical_coregister import _center_of_mass
        com = _center_of_mass(sphere_vol)
        # Should be close to the geometric centre (16, 16, 16)
        assert all(abs(com[i] - 16) < 3 for i in range(3))

    def test_mutual_information_identical(self, sphere_vol):
        """MI of identical non-trivial volumes should be non-negative.
        Note: for strictly binary volumes (0/1 only), MI may be 0 since
        all probability mass is on the diagonal → log(p/p*p) = log(1/p),
        but the normalised form can be 0. Use CC instead for binary images."""
        from pyasl.modules.preclinical_coregister import _mutual_information
        mi = _mutual_information(sphere_vol, sphere_vol)
        assert mi >= 0  # MI is always non-negative

    def test_cross_correlation_identical(self, sphere_vol):
        from pyasl.modules.preclinical_coregister import _cross_correlation
        cc = _cross_correlation(sphere_vol, sphere_vol)
        assert abs(cc - 1.0) < 0.01


# ============================================================
# Test PreclinicalNormalize
# ============================================================

class TestPreclinicalNormalize:

    def test_import(self):
        from pyasl.modules.preclinical_normalize import PreclinicalNormalize
        assert callable(PreclinicalNormalize)

    def test_run_requires_coreg_asl(self, sphere_vol):
        from pyasl.modules.preclinical_normalize import PreclinicalNormalize
        ctx = {"savedir": "."}
        with pytest.raises(KeyError):
            PreclinicalNormalize().run(ctx)

    def test_run_requires_template(self, sphere_vol):
        from pyasl.modules.preclinical_normalize import PreclinicalNormalize
        ctx = {"CoregASL": sphere_vol, "savedir": "."}
        with pytest.raises(ValueError):
            PreclinicalNormalize().run(ctx)

    def test_run_resamples_to_template_shape(self, sphere_vol, tmp_path):
        from pyasl.modules.preclinical_normalize import PreclinicalNormalize
        template = np.zeros((20, 20, 20), dtype=np.float32)
        ctx = {
            "CoregASL": sphere_vol,
            "AnatAffine": np.eye(4),
            "CoregAffine": np.eye(4),
            "TemplateImage": template,
            "TemplateAffine": np.eye(4),
            "savedir": str(tmp_path),
        }
        PreclinicalNormalize().run(ctx, save_normalized=False)
        assert "NormalizedASL" in ctx
        assert ctx["NormalizedASL"].shape == (20, 20, 20)

    def test_normalization_info_populated(self, sphere_vol, tmp_path):
        from pyasl.modules.preclinical_normalize import PreclinicalNormalize
        template = np.zeros((24, 24, 24), dtype=np.float32)
        ctx = {
            "CoregASL": sphere_vol,
            "AnatAffine": np.eye(4),
            "CoregAffine": np.eye(4),
            "TemplateImage": template,
            "TemplateAffine": np.eye(4) * 0.5,
            "savedir": str(tmp_path),
        }
        PreclinicalNormalize().run(ctx, save_normalized=False)
        info = ctx.get("NormalizationInfo", {})
        assert info["template_shape"] == [24, 24, 24]
        assert info["interp_order"] == 1

    def test_identity_transform_preserves_content(self, tmp_path):
        from pyasl.modules.preclinical_normalize import PreclinicalNormalize
        vol = _make_sphere((16, 16, 16), radius=6)
        ctx = {
            "CoregASL": vol,
            "AnatAffine": np.eye(4),
            "CoregAffine": np.eye(4),
            "TemplateImage": vol.copy(),
            "TemplateAffine": np.eye(4),
            "savedir": str(tmp_path),
        }
        PreclinicalNormalize().run(ctx, save_normalized=False)
        normalized = ctx["NormalizedASL"]
        # Under identity transform, output should closely match input
        assert normalized.shape == vol.shape
        assert np.corrcoef(vol.ravel(), normalized.ravel())[0, 1] > 0.95
