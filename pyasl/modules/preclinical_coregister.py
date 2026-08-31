"""
preclinical_coregister.py
--------------------------
Preclinical ASL co-registration using nibabel + scipy (no SPM/Nipype required).

Aligns the mean ASL perfusion image to an anatomical reference using
affine registration (center-of-mass initialisation → mutual-information
optimisation via scipy.optimize.minimize).

**All optimisation is performed in world coordinates (mm)** so that images
with different voxel sizes (e.g. ASL 0.3 mm, anatomical 0.1 mm) are
handled correctly.

Interface
---------
Compatible with all other preclinical modules:
    coreg = PreclinicalCoregister()
    coreg.run(ctx, **params)

Context keys consumed
~~~~~~~~~~~~~~~~~~~~~
- "ImageCtr"  : np.ndarray (X, Y, Z[, T]) — ASL control/label image
- "savedir"   : str — output directory

Optional params
~~~~~~~~~~~~~~~
- anat_path   : str — NIfTI path to anatomical reference (required unless
                      ctx["AnatImage"] is already set)
- interp_order: int — spline interpolation order (default 1 = linear)
- cost         : str — "MI" (mutual information, default) or "CC" (cross-corr)

Context keys produced
~~~~~~~~~~~~~~~~~~~~~
- "CoregASL"      : np.ndarray — resampled ASL in anatomical space
- "CoregAffine"   : np.ndarray (4,4) — estimated world-space affine transform
- "CoregRMSE"     : float — root-mean-square error after registration
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_nifti(path: str):
    """Load a NIfTI file; returns (data: np.ndarray, affine: np.ndarray)."""
    try:
        import nibabel as nib  # type: ignore
    except ImportError as e:
        raise ImportError("nibabel is required for preclinical co-registration. "
                          "Install with: pip install nibabel") from e
    img = nib.load(path)
    return np.asarray(img.dataobj, dtype=np.float32), img.affine


def _save_nifti(data: np.ndarray, affine: np.ndarray, path: str) -> None:
    try:
        import nibabel as nib  # type: ignore
    except ImportError:
        logger.warning("nibabel not available — skipping NIfTI save.")
        return
    img = nib.Nifti1Image(data.astype(np.float32), affine)
    nib.save(img, path)
    logger.debug("Saved NIfTI: %s", path)


def _center_of_mass(vol: np.ndarray) -> np.ndarray:
    """Return (x, y, z) centre-of-mass of positive voxels (legacy voxel space)."""
    vol = np.clip(vol, 0, None)
    total = vol.sum()
    if total == 0:
        return np.array(vol.shape, dtype=float) / 2.0
    idx = np.indices(vol.shape)
    com = np.array([(idx[i] * vol).sum() / total for i in range(3)])
    return com


def _center_of_mass_world(vol: np.ndarray, affine: np.ndarray) -> np.ndarray:
    """Return (x, y, z) centre-of-mass in world coordinates (mm).

    Parameters
    ----------
    vol    : 3-D volume (positive values contribute to the mass).
    affine : 4×4 voxel-to-world affine.
    """
    vol = np.clip(vol, 0, None)
    total = vol.sum()
    if total == 0:
        # Fallback: centre of the volume in world space
        centre_vox = np.array(vol.shape, dtype=float) / 2.0
        return (affine[:3, :3] @ centre_vox) + affine[:3, 3]
    idx = np.indices(vol.shape)
    com_vox = np.array([(idx[i] * vol).sum() / total for i in range(3)])
    # Convert voxel COM to world coordinates
    com_world = (affine[:3, :3] @ com_vox) + affine[:3, 3]
    return com_world


def _normalize_intensity(img: np.ndarray) -> tuple[np.ndarray, float, float]:
    """Normalize image to [0, 1] handling negative values (e.g. PASL data).

    Returns (normalized, original_min, original_range) so the caller can
    rescale back to the original data range.
    """
    img_min = float(img.min())
    img_max = float(img.max())
    img_range = img_max - img_min
    if img_range < 1e-12:
        return np.zeros_like(img, dtype=np.float32), img_min, img_range
    normalized = (img - img_min) / img_range
    return normalized.astype(np.float32), img_min, img_range


def _apply_affine(vol: np.ndarray, affine_3x3: np.ndarray,
                  offset: np.ndarray, order: int = 1) -> np.ndarray:
    """Apply a 3-D affine transform (matrix + offset) to a volume."""
    from scipy.ndimage import affine_transform  # type: ignore
    return affine_transform(vol, affine_3x3, offset=offset,
                            output_shape=vol.shape, order=order,
                            mode="constant", cval=0.0)


def _mutual_information(a: np.ndarray, b: np.ndarray, bins: int = 64) -> float:
    """Normalised mutual information between two volumes (higher = better)."""
    mask = (a > 0) & (b > 0)
    if mask.sum() < 10:
        return 0.0
    a_flat = a[mask].ravel()
    b_flat = b[mask].ravel()
    hist, _, _ = np.histogram2d(a_flat, b_flat, bins=bins)
    hist = hist / hist.sum()
    pa = hist.sum(axis=1, keepdims=True)
    pb = hist.sum(axis=0, keepdims=True)
    eps = 1e-12
    nmi = np.sum(hist * np.log((hist + eps) / (pa * pb + eps)))
    return float(nmi)


def _cross_correlation(a: np.ndarray, b: np.ndarray) -> float:
    """Normalised cross-correlation (higher = better aligned)."""
    a_f = a.ravel().astype(np.float64)
    b_f = b.ravel().astype(np.float64)
    denom = (np.linalg.norm(a_f) * np.linalg.norm(b_f))
    if denom < 1e-12:
        return 0.0
    return float(np.dot(a_f, b_f) / denom)


# ---------------------------------------------------------------------------
# Core registration — world-coordinate optimisation
# ---------------------------------------------------------------------------

def register_affine(
    moving: np.ndarray,
    fixed: np.ndarray,
    moving_affine: Optional[np.ndarray] = None,
    fixed_affine: Optional[np.ndarray] = None,
    cost: str = "MI",
    interp_order: int = 1,
    max_iter: int = 200,
) -> tuple[np.ndarray, np.ndarray, float]:
    """
    Rigid (6-DOF) affine registration of `moving` to `fixed`.

    **All optimisation is performed in world coordinates (mm)** using the
    NIfTI affine headers.  This ensures correct behaviour when ASL and
    anatomical images have different voxel sizes.

    Parameters
    ----------
    moving        : 3-D array — image to register (e.g. mean ASL)
    fixed         : 3-D array — reference image (e.g. anatomical)
    moving_affine : 4×4 voxel-to-world matrix for `moving`
    fixed_affine  : 4×4 voxel-to-world matrix for `fixed`
    cost          : similarity metric — "MI" or "CC"
    interp_order  : spline order for final resampling
    max_iter      : maximum Powell iterations

    Returns
    -------
    registered  : np.ndarray  — moving resampled into fixed space
    world_affine: np.ndarray  — 4×4 world-space transform (moving-world → fixed-world)
    rmse        : float       — root-mean-square error after registration
    """
    from scipy.optimize import minimize  # type: ignore
    from scipy.ndimage import affine_transform  # type: ignore

    fixed_f = fixed.astype(np.float32)
    moving_f = moving.astype(np.float32)

    # Positional argument backward compatibility (if 3rd pos arg was cost string)
    if isinstance(moving_affine, str):
        cost = moving_affine
        moving_affine = None

    if moving_affine is None:
        moving_affine = np.eye(4, dtype=np.float64)
    if fixed_affine is None:
        fixed_affine = np.eye(4, dtype=np.float64)

    # Normalise to [0,1] — handles negative values (PASL data)  [fix 1C]
    fixed_norm, _, _ = _normalize_intensity(fixed_f)
    moving_norm, moving_min, moving_range = _normalize_intensity(moving_f)

    # Initialise with centre-of-mass offset in WORLD coordinates (mm)  [fix 1A]
    com_fixed = _center_of_mass_world(fixed_norm, fixed_affine)
    com_moving = _center_of_mass_world(moving_norm, moving_affine)
    t0 = com_fixed - com_moving  # translation in mm

    # params: [tx, ty, tz, rx, ry, rz]  (translations in mm, rotations in radians)
    x0 = np.array([t0[0], t0[1], t0[2], 0.0, 0.0, 0.0], dtype=np.float64)

    def _params_to_world_matrix(params):
        """Build a 4×4 world-space rigid transform from 6 parameters."""
        tx, ty, tz, rx, ry, rz = params
        # Rotation matrices
        Rx = np.array([[1, 0, 0],
                       [0, np.cos(rx), -np.sin(rx)],
                       [0, np.sin(rx),  np.cos(rx)]])
        Ry = np.array([[ np.cos(ry), 0, np.sin(ry)],
                       [0,           1, 0          ],
                       [-np.sin(ry), 0, np.cos(ry)]])
        Rz = np.array([[np.cos(rz), -np.sin(rz), 0],
                       [np.sin(rz),  np.cos(rz), 0],
                       [0,           0,           1]])
        R = Rz @ Ry @ Rx
        T = np.eye(4, dtype=np.float64)
        T[:3, :3] = R
        T[:3, 3] = [tx, ty, tz]
        return T

    # Pre-compute the inverse of the fixed affine (world→voxel for fixed image)
    fixed_affine_inv = np.linalg.inv(fixed_affine)

    cost_fn = _mutual_information if cost.upper() == "MI" else _cross_correlation

    def _objective(params):
        """Evaluate cost: apply world transform, then resample moving into fixed grid."""
        T_world = _params_to_world_matrix(params)
        # Composite voxel mapping: moving_vox → moving_world → fixed_world → fixed_vox
        # For scipy.ndimage.affine_transform, we need the *inverse* mapping:
        #   fixed_vox → fixed_world → moving_world → moving_vox
        # i.e. moving_affine⁻¹ @ T_world⁻¹ @ fixed_affine
        T_world_inv = np.linalg.inv(T_world)
        vox_map = np.linalg.inv(moving_affine) @ T_world_inv @ fixed_affine
        R_vox = vox_map[:3, :3]
        t_vox = vox_map[:3, 3]
        warped = affine_transform(moving_norm, R_vox, offset=t_vox,
                                  output_shape=fixed_norm.shape, order=1,
                                  mode="constant", cval=0.0)
        score = cost_fn(warped, fixed_norm)
        return -score  # minimise negative = maximise similarity

    result = minimize(_objective, x0, method="Powell",
                      options={"maxiter": max_iter, "disp": False})

    # Build final world-space transform
    world_affine = _params_to_world_matrix(result.x)

    # Resample moving into fixed space using the final transform
    T_world_inv = np.linalg.inv(world_affine)
    vox_map_final = np.linalg.inv(moving_affine) @ T_world_inv @ fixed_affine
    R_final = vox_map_final[:3, :3]
    t_final = vox_map_final[:3, 3]
    registered_norm = affine_transform(moving_norm, R_final, offset=t_final,
                                       output_shape=fixed_norm.shape,
                                       order=interp_order, mode="constant", cval=0.0)

    score = -result.fun
    rmse = float(np.sqrt(np.mean((registered_norm - fixed_norm) ** 2)))
    logger.info("Co-registration finished. NMI=%.4f  RMSE=%.4f", score, rmse)

    # Rescale back to original data range  [fix 1C]
    registered = (registered_norm * moving_range + moving_min).astype(np.float32)

    return registered, world_affine, rmse


# ---------------------------------------------------------------------------
# Module class
# ---------------------------------------------------------------------------

class PreclinicalCoregister:
    """
    Co-register mean preclinical ASL image to anatomical reference.

    run(ctx, **p) params
    --------------------
    anat_path    : str  — path to anatomical NIfTI (required if ctx["AnatImage"]
                          not already set)
    interp_order : int  — interpolation order (default 1)
    cost         : str  — similarity metric: "MI" or "CC" (default "MI")
    save_coreg   : bool — save registered image as NIfTI (default True)
    """

    def run(self, ctx: dict, **p: Any) -> None:
        logger.info("PreclinicalCoregister: starting co-registration …")

        # --- resolve ASL moving image (mean over time if 4D) ---
        if "ImageCtr" not in ctx:
            raise KeyError("Context missing 'ImageCtr' (ASL control image)")
        asl = np.asarray(ctx["ImageCtr"], dtype=np.float32)
        if asl.ndim == 4:
            moving = asl.mean(axis=3)
        else:
            moving = asl

        # --- resolve moving affine (ASL voxel-to-world) ---
        moving_affine = ctx.get("ASLAffine", np.eye(4, dtype=np.float64))
        if isinstance(moving_affine, str):
            p["cost"] = moving_affine
            moving_affine = None

        # --- resolve anatomical fixed image ---
        if "AnatImage" in ctx:
            fixed = np.asarray(ctx["AnatImage"], dtype=np.float32)
            anat_affine = ctx.get("AnatAffine", np.eye(4))
        elif "anat_path" in p:
            fixed, anat_affine = _load_nifti(p["anat_path"])
            ctx["AnatImage"] = fixed
            ctx["AnatAffine"] = anat_affine
        else:
            raise ValueError("Either ctx['AnatImage'] or param 'anat_path' must be provided.")

        if fixed.ndim == 4:
            fixed = fixed.mean(axis=3)

        interp_order = int(p.get("interp_order", 1))
        cost = str(p.get("cost", "MI"))

        # --- run registration in world coordinates ---
        registered, world_affine, rmse = register_affine(
            moving, fixed,
            moving_affine=moving_affine,
            fixed_affine=anat_affine,
            cost=cost,
            interp_order=interp_order,
        )

        ctx["CoregASL"] = registered
        ctx["CoregAffine"] = world_affine  # now world-space (mm)
        ctx["CoregRMSE"] = rmse
        logger.info("Co-registration RMSE: %.4f", rmse)

        # --- optional save ---
        savedir = ctx.get("savedir") or p.get("root", ".")
        if p.get("save_coreg", True):
            out_path = os.path.join(savedir, "coregistered_asl.nii.gz")
            _save_nifti(registered, anat_affine, out_path)
            ctx["CoregPath"] = out_path
            logger.info("Saved co-registered ASL: %s", out_path)
