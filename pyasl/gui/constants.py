"""
gui/constants.py
-----------------
Single source of truth for shared colors, dimensions, and status maps
used across the GUI's models, controllers, and views.
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# Brand palette
# ---------------------------------------------------------------------------
class Colors:
    """Centralised colour constants (hex strings)."""

    # Core brand
    DARK_PURPLE = "#830085"
    BRIGHT_CORAL = "#FE565D"

    # Backgrounds
    BG_PRIMARY = "#000000"
    BG_PANEL = "#0d0d0d"
    BG_ELEVATED = "#111111"
    BG_HOVER = "#1a0a1b"
    BG_SUBTLE_HOVER = "#14081a"

    # Borders
    BORDER = "#2a0e2b"
    BORDER_SUBTLE = "#0f050f"

    # Text
    TEXT_PRIMARY = "#e2e8f0"
    TEXT_SECONDARY = "#94a3b8"
    TEXT_MUTED = "#64748b"
    TEXT_DIMMED = "#4a5568"

    # Semantic
    GREEN = "#22c55e"
    GREEN_BG = "#14532d"
    RED = "#ef4444"
    RED_BG = "#450a0a"
    YELLOW = "#f59e0b"
    YELLOW_BG = "#422006"
    STONE = "#78716c"
    STONE_BG = "#292524"
    SLATE_BG = "#1e293b"

    # Dashboard Aliases & Semantic Tokens
    ACCENT_PRIMARY = "#830085"
    ACCENT_SECONDARY = "#FE565D"
    BG_SECONDARY = "#0d0d0d"
    BG_TERTIARY = "#111111"
    ERROR = "#ef4444"
    WARNING = "#f59e0b"
    SUCCESS = "#22c55e"
    INFO = "#3b82f6"

    # Accent hover / pressed
    ACCENT_HOVER = "#9a1a9c"
    ACCENT_PRESSED = "#6b006d"

    # Log levels
    LOG_DEBUG = "#4a5568"
    LOG_INFO = "#a0aec0"
    LOG_WARNING = "#f59e0b"
    LOG_ERROR = "#FE565D"

    DARK_THEME = {
        "BG_PRIMARY": "#000000",
        "BG_PANEL": "#0d0d0d",
        "BG_ELEVATED": "#111111",
        "BG_HOVER": "#1a0a1b",
        "BG_SUBTLE_HOVER": "#14081a",
        "BORDER": "#2a0e2b",
        "BORDER_SUBTLE": "#0f050f",
        "TEXT_PRIMARY": "#e2e8f0",
        "TEXT_SECONDARY": "#94a3b8",
        "TEXT_MUTED": "#64748b",
        "TEXT_DIMMED": "#4a5568",
        "BRIGHT_CORAL": "#FE565D",
        "ACCENT_HOVER": "#9a1a9c",
        "ACCENT_PRESSED": "#6b006d",
        "GREEN_BG": "#14532d",
        "RED_BG": "#450a0a",
        "YELLOW_BG": "#422006",
        "STONE_BG": "#292524",
        "SLATE_BG": "#1e293b",
    }

    LIGHT_THEME = {
        "BG_PRIMARY": "#f8fafc",
        "BG_PANEL": "#ffffff",
        "BG_ELEVATED": "#f1f5f9",
        "BG_HOVER": "#f3e8ff",
        "BG_SUBTLE_HOVER": "#faf5ff",
        "BORDER": "#cbd5e1",
        "BORDER_SUBTLE": "#e2e8f0",
        "TEXT_PRIMARY": "#0f172a",
        "TEXT_SECONDARY": "#475569",
        "TEXT_MUTED": "#64748b",
        "TEXT_DIMMED": "#94a3b8",
        "BRIGHT_CORAL": "#dc2626",
        "ACCENT_HOVER": "#a3339f",
        "ACCENT_PRESSED": "#5e0060",
        "GREEN_BG": "#dcfce7",
        "RED_BG": "#fee2e2",
        "YELLOW_BG": "#fef3c7",
        "STONE_BG": "#e7e5e4",
        "SLATE_BG": "#e2e8f0",
    }

    @classmethod
    def set_theme(cls, theme_name: str):
        if theme_name == "light":
            vals = cls.LIGHT_THEME
        else:
            vals = cls.DARK_THEME

        for k, v in vals.items():
            setattr(cls, k, v)

        # Update dependent color dicts in this module
        global STATUS_COLORS, STATUS_TABLE_COLORS
        STATUS_COLORS.update({
            "PENDING":   cls.TEXT_MUTED,
            "RUNNING":   cls.YELLOW,
            "COMPLETED": cls.GREEN,
            "FAILED":    cls.BRIGHT_CORAL,
            "ABORTED":   cls.STONE,
        })
        STATUS_TABLE_COLORS.update({
            "PENDING":   (cls.SLATE_BG, cls.TEXT_SECONDARY),
            "RUNNING":   (cls.YELLOW_BG, cls.YELLOW),
            "COMPLETED": (cls.GREEN_BG, cls.GREEN),
            "FAILED":    (cls.RED_BG, cls.RED),
            "ABORTED":   (cls.STONE_BG, cls.STONE),
        })



# ---------------------------------------------------------------------------
# Design system — spacing & tokens
# ---------------------------------------------------------------------------

class Spacing:
    """8px-grid spacing scale used across all views."""
    XS  = 4
    SM  = 8
    MD  = 12
    LG  = 16
    XL  = 24
    XXL = 32


class DesignTokens:
    """Shared dimension tokens for consistent sizing."""
    TOOLBAR_BTN_HEIGHT   = 32
    TOOLBAR_BTN_PADDING  = 16     # horizontal padding inside buttons
    TOOLBAR_INPUT_HEIGHT = 32
    PALETTE_WIDTH_MIN    = 240
    PALETTE_WIDTH_MAX    = 300
    CONFIG_WIDTH_MIN     = 220
    CONFIG_WIDTH_MAX     = 320
    BORDER_RADIUS_SM     = 4
    BORDER_RADIUS_MD     = 6
    BORDER_RADIUS_LG     = 8
    FONT_SIZE_XS         = 10
    FONT_SIZE_SM         = 11
    FONT_SIZE_MD         = 13
    FONT_SIZE_LG         = 15
    FONT_SIZE_XL         = 18


# ---------------------------------------------------------------------------
# Status colour maps
# ---------------------------------------------------------------------------
#: (background_hex, foreground_hex) for table-row colouring
STATUS_TABLE_COLORS: dict[str, tuple[str, str]] = {
    "PENDING":   (Colors.SLATE_BG,  Colors.TEXT_SECONDARY),
    "RUNNING":   (Colors.YELLOW_BG, Colors.YELLOW),
    "COMPLETED": (Colors.GREEN_BG,  Colors.GREEN),
    "FAILED":    (Colors.RED_BG,    Colors.RED),
    "ABORTED":   (Colors.STONE_BG,  Colors.STONE),
}

#: Single hex for timeline / canvas status indicators
STATUS_COLORS: dict[str, str] = {
    "PENDING":   Colors.TEXT_MUTED,
    "RUNNING":   Colors.YELLOW,
    "COMPLETED": Colors.GREEN,
    "FAILED":    Colors.BRIGHT_CORAL,
    "ABORTED":   Colors.STONE,
}

LOG_LEVEL_COLORS: dict[str, str] = {
    "DEBUG":   Colors.LOG_DEBUG,
    "INFO":    Colors.LOG_INFO,
    "WARNING": Colors.LOG_WARNING,
    "ERROR":   Colors.LOG_ERROR,
}

# ---------------------------------------------------------------------------
# Canvas dimensions
# ---------------------------------------------------------------------------
NODE_WIDTH = 180
NODE_HEIGHT = 60
GRID_STEP = 28

# ---------------------------------------------------------------------------
# Batch table columns
# ---------------------------------------------------------------------------
BATCH_COLUMNS: list[str] = [
    "Job ID", "Label", "Data Dir", "Config", "Type", "Status", "Duration",
]

# ---------------------------------------------------------------------------
# Default palette functions (well-known preclinical modules)
# ---------------------------------------------------------------------------
DEFAULT_PALETTE_FUNCTIONS: list[str] = [
    "BrukerLoader", "NIfTILoader", "SteadyStateTrim", "ControlLabelSplit",
    "MotionCheck", "DiffImage", "ComputeM0", "SlicePLDAdjust",
    "CBFRelative", "BrainMask", "AbsCBF_T1Fit",
    "PreclinicalCoregister", "PreclinicalNormalize", "SaveOutputs",
]

from pyasl._version import __version__ as APP_VERSION

APP_NAME = "PyASL"
APP_DISPLAY_NAME = "PyASL Pipeline GUI"
APP_ORG = "OSIPI TF2.2"
