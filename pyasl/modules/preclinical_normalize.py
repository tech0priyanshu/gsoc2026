"""
preclinical_normalize.py
------------------------
Spatial normalisation of preclinical ASL data to a template space.

Uses nibabel for I/O and scipy for affine resampling. No SPM or FSL required.
Applies the co-registration transform (from PreclinicalCoregister) followed
by an affine rescaling to match the template voxel grid.

Interface
---------
    norm = PreclinicalNormalize()
    norm.run(ctx, **params)

Context keys consumed
~~~~~~~~~~~~~~~~~~~~~
- "CoregASL"    : np.ndarray — co-registered ASL (from PreclinicalCoregister)
- "CoregAffine" : np.ndarray (4,4) — transform from co-registration step
- "savedir"     : str — output directory

Optional params
~~~~~~~~~~~~~~~
- template_path  : str  — NIfTI template file to normalise to (required unless
                           ctx["TemplateImage"] is already set)
- interp_order   : int  — spline order (default 1)
- save_normalized: bool — save output NIfTI (default True)
- pad_value      : float — fill value for voxels outside FOV (default 0)

Context keys produced
~~~~~~~~~~~~~~~~~~~~~
- "NormalizedASL"     : np.ndarray — ASL resampled to template space
- "NormalizedPath"    : str        — path to saved NIfTI (if save_normalized)
- "NormalizationInfo" : dict       — meta (template shape, voxel sizes, etc.)
"""
from __future__ import annotations

import logging
import os
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_nifti(path: str):
    try:
        import nibabel as nib  # type: ignore
    except ImportError as exc:
        raise ImportError("nibabel required. Install: pip install nibabel") from exc
    img = nib.load(path)
    return np.asarray(img.dataobj, dtype=np.float32), img.affine, img.header


def _save_nifti(data: np.ndarray, affine: np.ndarray, path: str) -> None:
    try:
        import nibabel as nib  # type: ignore
    except ImportError:
        logger.warning("nibabel not available — skipping NIfTI save.")
        return
    nib.save(nib.Nifti1Image(data.astype(np.float32), affine), path)
    logger.debug("Saved: %s", path)


def _build_voxel_affine(source_affine: np.ndarray,
                         target_affine: np.ndarray) -> np.ndarray:
    """Compute the voxel-space transform from source to target."""
    return np.linalg.inv(target_affine) @ source_affine


def _resample_to_template(
    source: np.ndarray,
    source_affine: np.ndarray,
    target_shape: tuple,
    target_affine: np.ndarray,
    order: int = 1,
    cval: float = 0.0,
) -> np.ndarray:
    """Resample `source` into the `target_shape` voxel grid."""
    from scipy.ndimage import affine_transform  # type: ignore

    vox_to_vox = _build_voxel_affine(source_affine, target_affine)
    R = vox_to_vox[:3, :3]
    t = vox_to_vox[:3, 3]

    resampled = affine_transform(
        source, R, offset=t,
        output_shape=target_shape[:3],
        order=order,
        mode="constant",
        cval=cval,
    )
    return resampled.astype(np.float32)


# ---------------------------------------------------------------------------
# Module class
# ---------------------------------------------------------------------------

class PreclinicalNormalize:
    """
    Normalise co-registered preclinical ASL to a template space.

    Expects PreclinicalCoregister to have run first (ctx must contain
    "CoregASL" and "CoregAffine").

    run(ctx, **p) params
    --------------------
    template_path   : str   — path to template NIfTI
    interp_order    : int   — interpolation order (default 1)
    save_normalized : bool  — write NIfTI to savedir (default True)
    pad_value       : float — fill for out-of-FOV voxels (default 0)
    """

    def run(self, ctx: dict, **p: Any) -> None:
        logger.info("PreclinicalNormalize: starting normalisation …")

        # --- source image ---
        if "CoregASL" not in ctx:
            raise KeyError(
                "ctx['CoregASL'] missing. Run PreclinicalCoregister first."
            )
        source = np.asarray(ctx["CoregASL"], dtype=np.float32)
        if source.ndim == 4:
            source = source.mean(axis=3)

        # --- source affine (use coreg transform composed with anatomical affine) ---
        anat_affine = ctx.get("AnatAffine", np.eye(4, dtype=np.float64))
        coreg_affine = ctx.get("CoregAffine", np.eye(4, dtype=np.float64))
        # Guard: coreg_affine must be a proper 4×4 matrix
        assert coreg_affine.shape == (4, 4), (
            f"CoregAffine must be a 4×4 matrix, got shape {coreg_affine.shape}"
        )
        # Both matrices are in world-space (mm) after fix 1A, so composition
        # is dimensionally correct: source_world = anat_affine @ coreg_affine @ vox
        source_affine = anat_affine @ coreg_affine

        # --- template ---
        if "TemplateImage" in ctx:
            template = np.asarray(ctx["TemplateImage"], dtype=np.float32)
            tmpl_affine = ctx.get("TemplateAffine", np.eye(4))
        elif "template_path" in p:
            template, tmpl_affine, _ = _load_nifti(p["template_path"])
            ctx["TemplateImage"] = template
            ctx["TemplateAffine"] = tmpl_affine
            logger.info("Loaded template: %s  shape=%s", p["template_path"], template.shape)
        else:
            raise ValueError(
                "Either ctx['TemplateImage'] or param 'template_path' must be provided."
            )

        target_shape = template.shape[:3]
        interp_order = int(p.get("interp_order", 1))
        pad_value = float(p.get("pad_value", 0.0))

        # --- resample ---
        normalized = _resample_to_template(
            source, source_affine,
            target_shape, tmpl_affine,
            order=interp_order,
            cval=pad_value,
        )

        ctx["NormalizedASL"] = normalized
        ctx["NormalizationInfo"] = {
            "template_shape": list(target_shape),
            "template_affine": tmpl_affine.tolist(),
            "source_affine": source_affine.tolist(),
            "interp_order": interp_order,
        }
        logger.info(
            "Normalisation complete. Output shape: %s", normalized.shape
        )

        # --- optional save ---
        savedir = ctx.get("savedir") or p.get("root", ".")
        if p.get("save_normalized", True):
            out_path = os.path.join(savedir, "normalized_asl.nii.gz")
            _save_nifti(normalized, tmpl_affine, out_path)
            ctx["NormalizedPath"] = out_path
            logger.info("Saved normalized ASL: %s", out_path)
