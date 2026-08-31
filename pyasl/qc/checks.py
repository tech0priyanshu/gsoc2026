"""
pyasl/qc/checks.py
--------------------
Quality-control checks for preclinical ASL pipeline outputs.

Each check returns a ``QCResult`` dataclass instance that carries the
check name, pass/fail/warn status, primary metric, threshold description,
and a details dict with check-specific metadata.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class QCResult:
    """Result of a single QC check.

    Attributes
    ----------
    check     : Short identifier, e.g. ``"jacobian"``, ``"cbf_range"``.
    passed    : Overall pass/fail boolean.
    level     : ``"pass"`` | ``"warn"`` | ``"fail"``.
    value     : Primary scalar metric for this check.
    threshold : Human-readable threshold description.
    details   : Extra check-specific data (e.g. voxel counts, per-volume flags).
    """
    check: str
    passed: bool
    level: str  # "pass" | "warn" | "fail"
    value: float
    threshold: str
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# (a) Jacobian determinant check
# ---------------------------------------------------------------------------

def check_jacobian(
    affine_4x4: np.ndarray,
    det_min: float = 0.8,
    det_max: float = 1.2,
) -> QCResult:
    """Check the Jacobian determinant of a registration transform.

    For rigid registration, det(R) should be ≈ 1.0.
    Values outside ``[det_min, det_max]`` suggest a failed registration
    (excessive scaling or reflection).

    Parameters
    ----------
    affine_4x4 : 4×4 affine transform (typically ``CoregAffine``).
    det_min     : Lower bound (default 0.8).
    det_max     : Upper bound (default 1.2).
    """
    if affine_4x4.shape != (4, 4):
        raise ValueError(f"Expected 4×4 affine, got shape {affine_4x4.shape}")

    det = float(np.linalg.det(affine_4x4[:3, :3]))
    passed = det_min <= det <= det_max
    level = "pass" if passed else "fail"

    logger.info("QC jacobian: det=%.4f  range=[%.2f, %.2f]  %s",
                det, det_min, det_max, level)

    return QCResult(
        check="jacobian",
        passed=passed,
        level=level,
        value=det,
        threshold=f"det ∈ [{det_min}, {det_max}]",
        details={"det_min": det_min, "det_max": det_max},
    )


# ---------------------------------------------------------------------------
# (b) CBF physiological range check
# ---------------------------------------------------------------------------

def check_cbf_range(
    cbf_map: np.ndarray,
    min_val: float = 0.0,
    max_val: float = 200.0,
    outlier_threshold_pct: float = 5.0,
    brain_mask: Optional[np.ndarray] = None,
) -> QCResult:
    """Check that CBF values are within physiological range.

    For rodents the valid range is typically 0–200 mL/100g/min.
    The check **fails** if more than ``outlier_threshold_pct`` percent of
    voxels lie outside this range.

    Parameters
    ----------
    cbf_map              : CBF map (2-D or 3-D numpy array).
    min_val              : Lower bound of valid range (default 0).
    max_val              : Upper bound of valid range (default 200).
    outlier_threshold_pct: Fail if more than this % of voxels are outliers.
    brain_mask           : Optional boolean mask; only masked voxels are checked.
    """
    if brain_mask is not None:
        data = cbf_map[brain_mask > 0].ravel()
    else:
        data = cbf_map.ravel()

    if data.size == 0:
        return QCResult(
            check="cbf_range",
            passed=False,
            level="fail",
            value=0.0,
            threshold=f"CBF ∈ [{min_val}, {max_val}]; outlier < {outlier_threshold_pct}%",
            details={"error": "empty data or mask"},
        )

    outliers = np.sum((data < min_val) | (data > max_val))
    pct_outlier = float(outliers / data.size * 100.0)
    mean_cbf = float(np.mean(data))
    std_cbf = float(np.std(data))

    passed = pct_outlier <= outlier_threshold_pct
    level = "pass" if passed else "fail"

    logger.info("QC cbf_range: mean=%.2f  std=%.2f  outlier=%.2f%%  %s",
                mean_cbf, std_cbf, pct_outlier, level)

    return QCResult(
        check="cbf_range",
        passed=passed,
        level=level,
        value=pct_outlier,
        threshold=f"CBF ∈ [{min_val}, {max_val}]; outlier < {outlier_threshold_pct}%",
        details={
            "pct_outlier_voxels": round(pct_outlier, 4),
            "mean_cbf": round(mean_cbf, 4),
            "std_cbf": round(std_cbf, 4),
            "total_voxels": int(data.size),
            "outlier_voxels": int(outliers),
        },
    )


# ---------------------------------------------------------------------------
# (c) Motion parameter threshold check
# ---------------------------------------------------------------------------

def check_motion(
    motion_params: np.ndarray,
    translation_threshold_mm: float = 0.5,
    rotation_threshold_deg: float = 0.5,
) -> QCResult:
    """Check motion parameters against thresholds.

    Parameters
    ----------
    motion_params            : (N, 6) array where columns are
                               [tx, ty, tz, rx, ry, rz].
                               Translations in mm, rotations in degrees.
    translation_threshold_mm : Flag if any axis > this value.
    rotation_threshold_deg   : Flag if any axis > this value.

    Returns
    -------
    QCResult with ``n_flagged_volumes``, ``max_translation_mm``,
    ``max_rotation_deg`` in details.
    """
    if motion_params.ndim != 2 or motion_params.shape[1] < 6:
        raise ValueError(
            f"motion_params must be (N, 6), got shape {motion_params.shape}"
        )

    translations = np.abs(motion_params[:, :3])  # tx, ty, tz
    rotations = np.abs(motion_params[:, 3:6])     # rx, ry, rz

    max_trans = float(translations.max()) if translations.size else 0.0
    max_rot = float(rotations.max()) if rotations.size else 0.0

    # A volume is flagged if *any* translation or rotation exceeds its threshold
    trans_flagged = np.any(translations > translation_threshold_mm, axis=1)
    rot_flagged = np.any(rotations > rotation_threshold_deg, axis=1)
    flagged = trans_flagged | rot_flagged
    n_flagged = int(flagged.sum())

    n_volumes = motion_params.shape[0]
    passed = n_flagged == 0
    level = "pass" if passed else ("warn" if n_flagged <= 2 else "fail")

    logger.info("QC motion: flagged=%d/%d  max_trans=%.3fmm  max_rot=%.3f°  %s",
                n_flagged, n_volumes, max_trans, max_rot, level)

    return QCResult(
        check="motion",
        passed=passed,
        level=level,
        value=float(n_flagged),
        threshold=(f"translation < {translation_threshold_mm}mm, "
                   f"rotation < {rotation_threshold_deg}°"),
        details={
            "n_flagged_volumes": n_flagged,
            "n_total_volumes": n_volumes,
            "max_translation_mm": round(max_trans, 4),
            "max_rotation_deg": round(max_rot, 4),
            "flagged_indices": [int(i) for i in np.where(flagged)[0]],
        },
    )


# ---------------------------------------------------------------------------
# (d) SNR check on ASL difference images
# ---------------------------------------------------------------------------

def check_snr(
    control: np.ndarray,
    label: np.ndarray,
    brain_mask: Optional[np.ndarray] = None,
    snr_warn_threshold: float = 5.0,
) -> QCResult:
    """Check SNR of ASL difference images.

    SNR = mean(diff) / std(diff) within a brain mask.
    Warns if SNR < ``snr_warn_threshold`` for PASL data.

    Parameters
    ----------
    control           : Control image array (3-D or 4-D with time last).
    label             : Label image array (same shape as control).
    brain_mask        : Optional boolean mask; if None, uses all voxels.
    snr_warn_threshold: Warn if SNR is below this value (default 5.0).
    """
    if control.shape != label.shape:
        raise ValueError(
            f"control and label shapes must match: "
            f"{control.shape} vs {label.shape}"
        )

    diff = control.astype(np.float64) - label.astype(np.float64)

    # Average over time if 4-D
    if diff.ndim == 4:
        diff = diff.mean(axis=3)

    if brain_mask is not None:
        diff_masked = diff[brain_mask > 0].ravel()
    else:
        diff_masked = diff.ravel()

    if diff_masked.size == 0:
        return QCResult(
            check="snr",
            passed=False,
            level="fail",
            value=0.0,
            threshold=f"SNR ≥ {snr_warn_threshold}",
            details={"error": "empty data or mask"},
        )

    mean_diff = float(np.mean(diff_masked))
    std_diff = float(np.std(diff_masked))

    if std_diff < 1e-12:
        snr = float("inf") if abs(mean_diff) > 1e-12 else 0.0
    else:
        snr = abs(mean_diff) / std_diff

    passed = snr >= snr_warn_threshold
    level = "pass" if passed else "warn"

    logger.info("QC snr: SNR=%.2f  mean_diff=%.4f  std_diff=%.4f  %s",
                snr, mean_diff, std_diff, level)

    return QCResult(
        check="snr",
        passed=passed,
        level=level,
        value=round(snr, 4),
        threshold=f"SNR ≥ {snr_warn_threshold}",
        details={
            "snr": round(snr, 4),
            "mean_diff": round(mean_diff, 4),
            "std_diff": round(std_diff, 4),
            "n_voxels": int(diff_masked.size),
        },
    )
