"""
pyasl/qc — Quality Control checks for ASL pipeline outputs.

Provides automated QC checks for:
- Jacobian determinant of registration transforms
- CBF physiological range
- Motion parameter thresholds
- SNR of ASL difference images
"""
from .checks import (
    QCResult,
    check_jacobian,
    check_cbf_range,
    check_motion,
    check_snr,
)
from .report import render_qc_matrix

__all__ = [
    "QCResult",
    "check_jacobian",
    "check_cbf_range",
    "check_motion",
    "check_snr",
    "render_qc_matrix",
]
