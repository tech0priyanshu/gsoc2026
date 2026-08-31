"""
gui/utils/npy_visualizer.py
-----------------------------
Pure rendering logic for NumPy arrays → matplotlib figures → PNG bytes.

Uses matplotlib with the Agg backend (non-interactive) to avoid
conflicts with PyQt6's event loop. All functions are stateless
and thread-safe.

Supports dark and light themes via a ``theme`` parameter.
"""
from __future__ import annotations

import io
import os
from typing import Any, Dict, Optional, Tuple

import numpy as np

# Force non-interactive backend before any pyplot import
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402


# ---------------------------------------------------------------------------
# Theme palettes for matplotlib plots
# ---------------------------------------------------------------------------

_THEMES = {
    "dark": {
        "bg": "#0d0d0d",
        "ax_bg": "#111111",
        "title": "#e2e8f0",
        "label": "#94a3b8",
        "tick": "#94a3b8",
        "grid": "#2a0e2b",
        "spine": "#2a0e2b",
        "line": "#830085",
        "cbar_outline": "#2a0e2b",
    },
    "light": {
        "bg": "#ffffff",
        "ax_bg": "#f8fafc",
        "title": "#0f172a",
        "label": "#475569",
        "tick": "#475569",
        "grid": "#e2e8f0",
        "spine": "#cbd5e1",
        "line": "#830085",
        "cbar_outline": "#cbd5e1",
    },
}


def _get_theme(theme: str) -> dict:
    """Get theme palette, defaulting to dark."""
    return _THEMES.get(theme, _THEMES["dark"])


# ---------------------------------------------------------------------------
# Metadata extraction
# ---------------------------------------------------------------------------

def get_array_metadata(arr: np.ndarray, filename: str) -> Dict[str, Any]:
    """
    Extract descriptive metadata from a NumPy array.

    Returns
    -------
    dict with keys: filename, shape, dtype, min, max, ndim, description
    """
    ndim = arr.ndim
    if ndim == 1:
        desc = f"1D signal with {arr.shape[0]} elements"
    elif ndim == 2:
        desc = f"2D image ({arr.shape[0]}×{arr.shape[1]})"
    elif ndim == 3:
        desc = f"3D volume ({arr.shape[0]}×{arr.shape[1]}×{arr.shape[2]})"
    else:
        desc = f"{ndim}D array with shape {arr.shape}"

    # Handle non-numeric dtypes gracefully
    try:
        arr_min = float(np.nanmin(arr))
        arr_max = float(np.nanmax(arr))
    except (TypeError, ValueError):
        arr_min = None
        arr_max = None

    return {
        "filename": os.path.basename(filename),
        "filepath": filename,
        "shape": arr.shape,
        "dtype": str(arr.dtype),
        "min": arr_min,
        "max": arr_max,
        "ndim": ndim,
        "description": desc,
    }


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------

def _style_ax(ax, t: dict):
    """Apply theme styling to a matplotlib Axes."""
    ax.set_facecolor(t["ax_bg"])
    ax.tick_params(colors=t["tick"], labelsize=8)
    for spine in ax.spines.values():
        spine.set_color(t["spine"])


def _render_1d(arr: np.ndarray, title: str, t: dict) -> Figure:
    """Render a 1D array as a line plot."""
    fig, ax = plt.subplots(1, 1, figsize=(8, 3), dpi=150)
    ax.plot(arr, color=t["line"], linewidth=1.2, alpha=0.9)
    ax.fill_between(range(len(arr)), arr, alpha=0.08, color=t["line"])
    ax.set_title(title, fontsize=10, fontweight="bold", color=t["title"])
    ax.set_xlabel("Index", fontsize=9, color=t["label"])
    ax.set_ylabel("Value", fontsize=9, color=t["label"])
    ax.grid(True, alpha=0.3, color=t["grid"])
    fig.patch.set_facecolor(t["bg"])
    _style_ax(ax, t)
    fig.tight_layout()
    return fig


def _render_2d(arr: np.ndarray, title: str, t: dict) -> Figure:
    """Render a 2D array as a heatmap with colorbar."""
    fig, ax = plt.subplots(1, 1, figsize=(6, 5), dpi=150)
    im = ax.imshow(arr, cmap="inferno", aspect="auto")
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.ax.tick_params(colors=t["tick"], labelsize=8)
    cbar.outline.set_edgecolor(t["cbar_outline"])
    ax.set_title(title, fontsize=10, fontweight="bold", color=t["title"])
    fig.patch.set_facecolor(t["bg"])
    _style_ax(ax, t)
    fig.tight_layout()
    return fig


def _render_3d(arr: np.ndarray, title: str, t: dict) -> Figure:
    """
    Render a 3D array as a 4-panel figure:
    - Axial slice (middle of axis 0)
    - Coronal slice (middle of axis 1)
    - Sagittal slice (middle of axis 2)
    - Maximum Intensity Projection along axis 0
    """
    fig, axes = plt.subplots(1, 4, figsize=(14, 4), dpi=150)

    mid0 = arr.shape[0] // 2
    mid1 = arr.shape[1] // 2
    mid2 = arr.shape[2] // 2

    slices = [
        (arr[mid0, :, :], f"Axial (z={mid0})"),
        (arr[:, mid1, :], f"Coronal (y={mid1})"),
        (arr[:, :, mid2], f"Sagittal (x={mid2})"),
        (np.max(arr, axis=0), "MIP (axis 0)"),
    ]

    for ax, (data, subtitle) in zip(axes, slices):
        ax.imshow(data, cmap="inferno", aspect="auto")
        ax.set_title(subtitle, fontsize=8, fontweight="bold", color=t["title"])
        _style_ax(ax, t)

    fig.suptitle(title, fontsize=10, fontweight="bold", color=t["title"], y=1.02)
    fig.patch.set_facecolor(t["bg"])
    fig.tight_layout()
    return fig


def _render_nd(arr: np.ndarray, title: str, t: dict) -> Figure:
    """
    Render a 4D+ array by extracting the first volume
    along the last dimension(s) and treating the result as 3D.
    """
    reduced = arr
    while reduced.ndim > 3:
        reduced = reduced[..., 0]
    return _render_3d(reduced, f"{title} (first volume)", t)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

import threading

_render_lock = threading.Lock()


def render_array_to_png(
    arr: np.ndarray,
    filename: str = "array",
    dpi: int = 100,
    theme: str = "dark",
) -> bytes:
    """
    Render a NumPy array to PNG image bytes.

    Parameters
    ----------
    arr : np.ndarray
        Input array (1D, 2D, 3D, or N-D).
    filename : str
        Base filename used for title annotation.
    dpi : int
        Output image resolution.
    theme : str
        Color theme: 'dark' or 'light'.

    Returns
    -------
    bytes : Raw PNG image bytes ready to pass to QPixmap.loadFromData().

    Raises
    ------
    ValueError
        If the array has 0 dimensions or is empty.
    """
    if arr.size == 0:
        raise ValueError(f"Array from '{filename}' is empty (size=0).")

    with _render_lock:
        t = _get_theme(theme)
        base = os.path.splitext(os.path.basename(filename))[0]

        if arr.ndim == 1:
            fig = _render_1d(arr, base, t)
        elif arr.ndim == 2:
            fig = _render_2d(arr, base, t)
        elif arr.ndim == 3:
            fig = _render_3d(arr, base, t)
        else:
            fig = _render_nd(arr, base, t)

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight",
                    facecolor=fig.get_facecolor(), edgecolor="none")
        plt.close(fig)
        buf.seek(0)
        return buf.read()


def save_png(png_bytes: bytes, output_path: str) -> str:
    """
    Write PNG bytes to disk.

    Parameters
    ----------
    png_bytes : bytes
        PNG image data from ``render_array_to_png``.
    output_path : str
        Full file path including .png extension.

    Returns
    -------
    str
        The absolute path of the saved file.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(png_bytes)
    return os.path.abspath(output_path)
