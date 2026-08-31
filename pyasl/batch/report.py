"""
batch/report.py
---------------
Generate HTML + JSON summary reports from a list of BatchResult objects.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import List

from .job import BatchResult, BatchStatus


_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PyASL Batch Report</title>
<style>
  :root {{
    --bg: #0f1117; --panel: #1a1d27; --accent: #7c6af7;
    --green: #22c55e; --red: #ef4444; --yellow: #f59e0b;
    --text: #e2e8f0; --muted: #64748b; --border: #2d3148;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: 'Segoe UI', sans-serif;
          padding: 2rem; line-height: 1.6; }}
  h1 {{ font-size: 1.8rem; margin-bottom: 0.3rem; color: var(--accent); }}
  .meta {{ color: var(--muted); font-size: 0.9rem; margin-bottom: 2rem; }}
  .summary {{ display: flex; gap: 1rem; margin-bottom: 2rem; flex-wrap: wrap; }}
  .stat {{ background: var(--panel); border: 1px solid var(--border); border-radius: 12px;
           padding: 1rem 1.5rem; flex: 1; min-width: 140px; }}
  .stat-num {{ font-size: 2rem; font-weight: 700; }}
  .stat-label {{ font-size: 0.8rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.08em; }}
  .green {{ color: var(--green); }} .red {{ color: var(--red); }}
  .yellow {{ color: var(--yellow); }} .accent {{ color: var(--accent); }}
  table {{ width: 100%; border-collapse: collapse; background: var(--panel);
           border-radius: 12px; overflow: hidden; }}
  th {{ background: #252840; padding: 0.75rem 1rem; text-align: left;
        font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.06em;
        color: var(--muted); border-bottom: 1px solid var(--border); }}
  td {{ padding: 0.75rem 1rem; border-bottom: 1px solid var(--border); font-size: 0.9rem; }}
  tr:last-child td {{ border-bottom: none; }}
  .badge {{ display: inline-block; padding: 0.15rem 0.6rem; border-radius: 99px;
             font-size: 0.75rem; font-weight: 600; text-transform: uppercase; }}
  .badge-COMPLETED {{ background: #14532d; color: var(--green); }}
  .badge-FAILED    {{ background: #450a0a; color: var(--red); }}
  .badge-ABORTED   {{ background: #422006; color: var(--yellow); }}
  .badge-PENDING   {{ background: #1e293b; color: var(--muted); }}
  .path {{ font-size: 0.8rem; color: var(--muted); word-break: break-all; }}
  .error-row td {{ background: #1a0505; }}
  .error-msg {{ color: var(--red); font-size: 0.8rem; font-family: monospace;
                 max-height: 80px; overflow-y: auto; white-space: pre-wrap; }}
</style>
</head>
<body>
<h1>PyASL Batch Report</h1>
<p class="meta">Generated: {generated} &nbsp;|&nbsp; Total jobs: {total}</p>

<div class="summary">
  <div class="stat"><div class="stat-num accent">{total}</div><div class="stat-label">Total</div></div>
  <div class="stat"><div class="stat-num green">{completed}</div><div class="stat-label">Completed</div></div>
  <div class="stat"><div class="stat-num red">{failed}</div><div class="stat-label">Failed</div></div>
  <div class="stat"><div class="stat-num yellow">{aborted}</div><div class="stat-label">Aborted/Skipped</div></div>
  <div class="stat"><div class="stat-num accent">{avg_dur}s</div><div class="stat-label">Avg Duration</div></div>
</div>

<table>
<thead>
  <tr>
    <th>Job ID</th><th>Status</th><th>Data Directory</th>
    <th>Config</th><th>Duration</th>
  </tr>
</thead>
<tbody>
{rows}
</tbody>
</table>
{qc_matrix}
</body>
</html>
"""

_ROW_TEMPLATE = """<tr{cls}>
  <td><code>{job_id}</code></td>
  <td><span class="badge badge-{status}">{status}</span></td>
  <td class="path">{data_dir}</td>
  <td class="path">{config_path}</td>
  <td>{duration}</td>
</tr>{error_row}"""

_ERROR_ROW = """<tr class="error-row">
  <td colspan="5"><div class="error-msg">{error}</div></td>
</tr>"""


_LIVE_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PyASL Batch Report (Live)</title>
<style>
  :root {
    --bg: #0f1117; --panel: #1a1d27; --accent: #7c6af7;
    --green: #22c55e; --red: #ef4444; --yellow: #f59e0b;
    --text: #e2e8f0; --muted: #64748b; --border: #2d3148;
    --console-bg: #050505;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: 'Segoe UI', sans-serif;
          padding: 2rem; line-height: 1.6; }
  
  .header-container {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.5rem;
  }
  h1 { font-size: 1.8rem; color: var(--accent); }
  
  .live-indicator {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.85rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    padding: 0.25rem 0.75rem;
    border-radius: 99px;
    background: rgba(34, 197, 94, 0.1);
    color: var(--green);
  }
  .live-indicator.completed {
    background: rgba(124, 106, 247, 0.1);
    color: var(--accent);
  }
  .live-indicator.aborted {
    background: rgba(245, 158, 11, 0.1);
    color: var(--yellow);
  }
  .dot {
    width: 8px;
    height: 8px;
    background-color: currentColor;
    border-radius: 50%;
  }
  .live-indicator:not(.completed):not(.aborted) .dot {
    animation: pulse 1.5s infinite;
  }
  
  @keyframes pulse {
    0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.7); }
    70% { transform: scale(1); box-shadow: 0 0 0 6px rgba(34, 197, 94, 0); }
    100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(34, 197, 94, 0); }
  }
  
  .meta { color: var(--muted); font-size: 0.9rem; margin-bottom: 2rem; }
  .summary { display: flex; gap: 1rem; margin-bottom: 2rem; flex-wrap: wrap; }
  .stat { background: var(--panel); border: 1px solid var(--border); border-radius: 12px;
           padding: 1rem 1.5rem; flex: 1; min-width: 140px; transition: transform 0.2s, border-color 0.2s; }
  .stat:hover { transform: translateY(-2px); border-color: var(--accent); }
  .stat-num { font-size: 2rem; font-weight: 700; }
  .stat-label { font-size: 0.8rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.08em; }
  .green { color: var(--green); } .red { color: var(--red); }
  .yellow { color: var(--yellow); } .accent { color: var(--accent); }
  
  /* Console styling */
  .console-wrapper {
    background: var(--console-bg);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1rem;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 0.9rem;
    box-shadow: inset 0 4px 12px rgba(0,0,0,0.5);
  }
  .console-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid var(--border);
    padding-bottom: 0.5rem;
    margin-bottom: 1rem;
    font-size: 0.8rem;
    color: var(--muted);
  }
  .console-logs {
    height: 400px;
    overflow-y: auto;
    white-space: pre-wrap;
    word-break: break-all;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    scroll-behavior: smooth;
  }
  
  /* Log line styles */
  .log-line {
    line-height: 1.4;
  }
  .log-time { color: var(--muted); }
  .log-level { font-weight: bold; }
  .log-level.info { color: #3b82f6; }
  .log-level.warning { color: var(--yellow); }
  .log-level.error { color: var(--red); }
  
  /* Scrollbar styling */
  .console-logs::-webkit-scrollbar { width: 8px; }
  .console-logs::-webkit-scrollbar-track { background: var(--console-bg); }
  .console-logs::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }
  .console-logs::-webkit-scrollbar-thumb:hover { background: var(--muted); }
  
  .refresh-btn {
    display: none;
    margin-top: 1rem;
    padding: 0.75rem 1.5rem;
    background: var(--accent);
    color: white;
    border: none;
    border-radius: 8px;
    font-weight: 600;
    cursor: pointer;
    transition: background 0.2s, transform 0.1s;
    font-size: 0.95rem;
    box-shadow: 0 4px 12px rgba(124, 106, 247, 0.3);
  }
  .refresh-btn:hover { background: #6352e3; transform: translateY(-1px); }
  .refresh-btn:active { transform: translateY(1px); }
</style>
</head>
<body>
<div class="header-container">
  <h1>PyASL Batch Execution</h1>
  <div id="live-banner" class="live-indicator">
    <div class="dot"></div>
    <span id="live-text">Live Batch Running</span>
  </div>
</div>
<p class="meta">Started: {{started_time}}</p>

<div class="summary">
  <div class="stat"><div class="stat-num accent" id="stat-total">{{total}}</div><div class="stat-label">Total Jobs</div></div>
  <div class="stat"><div class="stat-num green" id="stat-completed">0</div><div class="stat-label">Completed</div></div>
  <div class="stat"><div class="stat-num red" id="stat-failed">0</div><div class="stat-label">Failed</div></div>
  <div class="stat"><div class="stat-num yellow" id="stat-pending">{{total}}</div><div class="stat-label">Pending</div></div>
</div>

<div class="console-wrapper">
  <div class="console-header">
    <span>EXECUTION LOG CONSOLE</span>
    <span id="console-status">STREAMING ACTIVE</span>
  </div>
  <div class="console-logs" id="log-console">
    <!-- Log lines appended here -->
  </div>
</div>

<button id="refresh-btn" class="refresh-btn" onclick="window.location.reload()">🔄 Refresh to View Final Report</button>

<script>
  let isFinished = false;
  
  function updateData(data) {
    document.getElementById('stat-total').innerText = data.total;
    document.getElementById('stat-completed').innerText = data.completed;
    document.getElementById('stat-failed').innerText = data.failed;
    document.getElementById('stat-pending').innerText = data.pending;
    
    const consoleEl = document.getElementById('log-console');
    
    // Clear and build the log stream
    consoleEl.innerHTML = '';
    data.logs.forEach(log => {
      const line = document.createElement('div');
      line.className = 'log-line';
      
      const timeSpan = `<span class="log-time">[${log.time}]</span>`;
      const levelSpan = `<span class="log-level ${log.level.toLowerCase()}">[${log.level}]</span>`;
      const msgSpan = `<span>${log.message}</span>`;
      
      line.innerHTML = `${timeSpan} ${levelSpan} ${msgSpan}`;
      consoleEl.appendChild(line);
    });
    
    // Auto-scroll to bottom
    consoleEl.scrollTop = consoleEl.scrollHeight;
    
    if (data.finished && !isFinished) {
      isFinished = true;
      const banner = document.getElementById('live-banner');
      banner.className = 'live-indicator completed';
      document.getElementById('live-text').innerText = 'Batch Completed';
      document.getElementById('console-status').innerText = 'STREAMING ENDED';
      document.getElementById('refresh-btn').style.display = 'block';
    } else if (data.aborted && !isFinished) {
      isFinished = true;
      const banner = document.getElementById('live-banner');
      banner.className = 'live-indicator aborted';
      document.getElementById('live-text').innerText = 'Batch Aborted';
      document.getElementById('console-status').innerText = 'STREAMING ENDED';
      document.getElementById('refresh-btn').style.display = 'block';
    }
  }
  
  function poll() {
    if (isFinished) return;
    const oldScript = document.getElementById('live-data-script');
    if (oldScript) {
      oldScript.remove();
    }
    const script = document.createElement('script');
    script.id = 'live-data-script';
    script.src = 'batch_report_data.js?t=' + Date.now();
    document.body.appendChild(script);
  }
  
  setInterval(poll, 1000);
  poll();
</script>
</body>
</html>
"""


def generate_live_report_template(
    html_path: str,
    total: int,
    started_time: str,
) -> None:
    html = _LIVE_HTML_TEMPLATE.replace("{{started_time}}", started_time).replace("{{total}}", str(total))
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)


def generate_report(
    results: List[BatchResult],
    output_dir: str = ".",
    base_name: str = "batch_report",
    qc_results: Optional[dict] = None,
) -> tuple[str, str]:
    """
    Generate HTML and JSON reports from batch results.

    Parameters
    ----------
    results    : List of BatchResult objects
    output_dir : Output directory for report files
    base_name  : File name prefix for reports
    qc_results : Optional mapping of subject_id -> list of QCResult (or dicts)

    Returns
    -------
    (html_path, json_path) — absolute paths to the written files.
    """
    os.makedirs(output_dir, exist_ok=True)
    html_path = os.path.join(output_dir, f"{base_name}.html")
    json_path = os.path.join(output_dir, f"{base_name}.json")

    completed = sum(1 for r in results if r.status == BatchStatus.COMPLETED)
    failed = sum(1 for r in results if r.status == BatchStatus.FAILED)
    aborted = sum(1 for r in results if r.status == BatchStatus.ABORTED)
    total = len(results)
    durations = [r.duration for r in results if r.status == BatchStatus.COMPLETED]
    avg_dur = f"{sum(durations)/len(durations):.1f}" if durations else "—"

    rows = []
    for r in results:
        dur = f"{r.duration:.2f}s" if r.duration is not None else "—"
        error_row = ""
        if r.error:
            err_text = r.error
            # If traceback has more detailed information, append it
            tb = getattr(r, "traceback", None)
            if tb:
                err_text += f"\n\nTraceback:\n{tb}"
            error_row = _ERROR_ROW.format(error=err_text.replace("<", "&lt;").replace(">", "&gt;"))
        cls = ' class="error-row"' if r.status == BatchStatus.FAILED else ""
        rows.append(_ROW_TEMPLATE.format(
            cls=cls,
            job_id=r.job_id,
            status=r.status.value,
            data_dir=r.data_dir,
            config_path=r.config_path,
            duration=dur,
            error_row=error_row,
        ))

    qc_matrix_html = ""
    json_qc_data = None
    if qc_results:
        try:
            from pyasl.qc.report import render_qc_matrix, qc_results_to_json
            subjects = [r.job_id for r in results]
            qc_matrix_html = render_qc_matrix(subjects, qc_results)
            json_qc_data = qc_results_to_json(qc_results)
        except Exception as e:
            qc_matrix_html = f"<!-- Error rendering QC matrix: {e} -->"

    html = _HTML_TEMPLATE.format(
        generated=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        total=total,
        completed=completed,
        failed=failed,
        aborted=aborted,
        avg_dur=avg_dur,
        rows="\n".join(rows),
        qc_matrix=qc_matrix_html,
    )

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    json_data = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "summary": {"total": total, "completed": completed,
                    "failed": failed, "aborted": aborted},
        "jobs": [r.to_dict() for r in results],
    }
    if json_qc_data is not None:
        json_data["qc_results"] = json_qc_data

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2, default=str)

    return html_path, json_path
