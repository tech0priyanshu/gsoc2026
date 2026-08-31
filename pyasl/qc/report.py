"""
pyasl/qc/report.py
--------------------
Generate HTML snippets for QC result reporting.

The primary entry point is ``render_qc_matrix`` which produces an HTML
table showing a per-subject × QC-check matrix (pass / warn / fail).
"""
from __future__ import annotations

import html
from typing import Dict, List

from .checks import QCResult


_QC_CSS = """
<style>
  .qc-table { width: 100%; border-collapse: collapse; background: var(--panel, #1a1d27);
               border-radius: 12px; overflow: hidden; margin-top: 2rem; }
  .qc-table th { background: #252840; padding: 0.65rem 1rem; text-align: center;
                  font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.06em;
                  color: var(--muted, #64748b); border-bottom: 1px solid var(--border, #2d3148); }
  .qc-table td { padding: 0.6rem 1rem; text-align: center;
                  border-bottom: 1px solid var(--border, #2d3148); font-size: 0.85rem; }
  .qc-table tr:last-child td { border-bottom: none; }
  .qc-table .subject-col { text-align: left; font-weight: 600; }
  .qc-pass { color: #22c55e; font-weight: 700; }
  .qc-warn { color: #f59e0b; font-weight: 700; }
  .qc-fail { color: #ef4444; font-weight: 700; }
</style>
"""

_LEVEL_LABELS = {
    "pass": ("✓", "qc-pass"),
    "warn": ("⚠", "qc-warn"),
    "fail": ("✗", "qc-fail"),
}


def render_qc_matrix(
    subjects: List[str],
    qc_results: Dict[str, List[QCResult]],
) -> str:
    """Render an HTML table: rows = subjects, columns = QC checks.

    Parameters
    ----------
    subjects   : Ordered list of subject identifiers.
    qc_results : Mapping ``subject_id → list[QCResult]``.
                 Each subject should have results for the same set of checks.

    Returns
    -------
    str : Complete HTML snippet (CSS + table) ready to embed in a report.
    """
    if not subjects or not qc_results:
        return "<!-- No QC data -->"

    # Collect all check names (preserve order from first subject)
    first_key = next(iter(qc_results))
    check_names = [r.check for r in qc_results.get(first_key, [])]
    if not check_names:
        return "<!-- No QC checks -->"

    # Build index: subject → {check_name: QCResult}
    lookup: Dict[str, Dict[str, QCResult]] = {}
    for subj in subjects:
        results_list = qc_results.get(subj, [])
        lookup[subj] = {r.check: r for r in results_list}

    # Header row
    header_cells = "<th class='subject-col'>Subject</th>"
    for cn in check_names:
        header_cells += f"<th>{html.escape(cn)}</th>"

    # Data rows
    rows = []
    for subj in subjects:
        cells = f"<td class='subject-col'><code>{html.escape(subj)}</code></td>"
        for cn in check_names:
            qr = lookup.get(subj, {}).get(cn)
            if qr is None:
                cells += "<td>—</td>"
            else:
                label, css_class = _LEVEL_LABELS.get(qr.level, ("?", ""))
                tooltip = f"{cn}: {qr.value:.4f} ({qr.threshold})"
                cells += (
                    f'<td class="{css_class}" title="{html.escape(tooltip)}">'
                    f'{label}</td>'
                )
        rows.append(f"  <tr>{cells}</tr>")

    table_html = (
        f"{_QC_CSS}\n"
        f"<h2 style='color: var(--accent, #7c6af7); margin-top: 2rem;'>"
        f"Quality Control Matrix</h2>\n"
        f"<table class='qc-table'>\n"
        f"<thead><tr>{header_cells}</tr></thead>\n"
        f"<tbody>\n"
        + "\n".join(rows)
        + "\n</tbody>\n</table>"
    )
    return table_html


def qc_results_to_json(
    qc_results: Dict[str, List[QCResult]],
) -> Dict[str, list]:
    """Convert QC results to a JSON-serialisable dict."""
    return {
        subj: [r.to_dict() for r in results]
        for subj, results in qc_results.items()
    }
