"""
gui/error_map.py
------------------
Mapping of known exception types and error message substrings to
plain-English, human-readable user guidance.
"""
from __future__ import annotations

from typing import List, Tuple, Union, Type, Optional

ERROR_MAPPINGS: List[Tuple[Type[Exception], Optional[str], str]] = [
    (
        KeyError, "ImageCtr",
        "The ASL control image was not found. Make sure a loader step (BrukerLoader or NIfTILoader) ran successfully before this step."
    ),
    (
        KeyError, "AnatImage",
        "The anatomical reference image was not found. Provide an anatomical image path in step configuration or run an anatomical loader first."
    ),
    (
        FileNotFoundError, None,
        "File or directory not found. Check that the specified path exists and is accessible."
    ),
    (
        ValueError, "cannot contain '.'",
        "Node IDs cannot contain dot '.' characters. Rename the node using alphanumeric characters or underscores (e.g. 'node_1')."
    ),
    (
        PermissionError, None,
        "Permission denied when accessing path. Check file and directory permissions."
    ),
]


def format_human_error(exc: Union[Exception, str]) -> str:
    """Format an exception or error string into user-friendly guidance."""
    exc_str = str(exc)
    exc_type = type(exc) if isinstance(exc, Exception) else Exception

    for mapped_type, key_sub, user_msg in ERROR_MAPPINGS:
        if issubclass(exc_type, mapped_type):
            if key_sub is None or key_sub in exc_str:
                return f"{user_msg}\n\n(Details: {exc_str})"

    return f"Error: {exc_str}\n\nPlease check input parameters and dataset files."
