"""
Agent trace dashboard.

Reads traces.json written by the orchestrator and renders a simple
auto-refreshing HTML page showing all pipeline runs.

Run in a separate terminal:
  python3 dashboard.py
Then open: http://localhost:5001
"""

import json
import os
from pathlib import Path

from flask import Flask, jsonify, render_template_string

TRACES_FILE = Path(__file__).parent / "traces.json"
app = Flask(__name__)

_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta http-equiv="refresh" content="10">
  <title>Teaching Bot — Agent Traces</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 1000px; margin: 40px auto;
           padding: 0 16px; background: #f7f8fa; color: #222; }
    h1   { font-size: 1.4rem; color: #2c3e8a; }
    .badge-ok  { background:#2ecc71; color:#fff; padding:2px 8px; border-radius:4px; }
    .badge-err { background:#e74c3c; color:#fff; padding:2px 8px; border-radius:4px; }
    table { width:100%; border-collapse:collapse; margin-top:16px; background:#fff;
            border-radius:8px; box-shadow:0 1px 4px rgba(0,0,0,.1); }
    th { background:#2c3e8a; color:#fff; padding:10px 12px; text-align:left;
         font-weight:600; font-size:.85rem; }
    td { padding:9px 12px; border-bottom:1px solid #eee; font-size:.85rem;
         vertical-align:top; }
    tr:last-child td { border-bottom:none; }
    tr:hover td { background:#f0f3ff; }
    details summary { cursor:pointer; color:#2c3e8a; font-weight:600; }
    pre  { background:#f4f4f4; padding:10px; border-radius:4px;
           font-size:.8rem; white-space:pre-wrap; word-break:break-word;
           max-height:260px; overflow:auto; }
    .ts  { color:#888; font-size:.78rem; }
    .empty { text-align:center; padding:40px; color:#888; }
    .refresh { float:right; font-size:.8rem; color:#888; }
  </style>
</head>
<body>
<h1>🤖 Teaching Bot — Agent Traces
  <span class="refresh">auto-refreshes every 10 s</span>
</h1>

{% if not traces %}
  <p class="empty">No traces yet. Run /plan in Telegram to generate a pipeline trace.</p>
{% else %}
<table>
  <thead>
    <tr>
      <th>#</th><th>Time</th><th>User</th><th>File</th>
      <th>Language</th><th>Duration</th><th>Total time</th><th>Status</th>
    </tr>
  </thead>
  <tbody>
  {% for t in traces|reverse %}
    <tr>
      <td>{{ loop.index }}</td>
      <td><span class="ts">{{ t.timestamp[:19].replace("T"," ") }}</span></td>
      <td>{{ t.user_id }}</td>
      <td>{{ t.file_name or '—' }}</td>
      <td>{{ t.params.language }}</td>
      <td>{{ t.params.duration }}</td>
      <td>{{ t.total_elapsed_s }} s</td>
      <td>
        {% if t.status == "success" %}
          <span class="badge-ok">✓ ok</span>
        {% else %}
          <span class="badge-err">✗ error</span>
        {% endif %}
      </td>
    </tr>
    <tr>
      <td colspan="8">
        <details>
          <summary>Steps &amp; trace</summary>
          <pre>
{%- for s in t.steps %}{{ "%-42s"|format(s.name) }}  {{ s.elapsed_s }} s
{% endfor %}
{%- if t.error %}
ERROR: {{ t.error }}{% endif %}
          </pre>
        </details>
      </td>
    </tr>
  {% endfor %}
  </tbody>
</table>
{% endif %}
</body>
</html>
"""


def _load_traces() -> list[dict]:
    if not TRACES_FILE.exists():
        return []
    try:
        return json.loads(TRACES_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


@app.route("/")
def index():
    return render_template_string(_HTML, traces=_load_traces())


@app.route("/api/traces")
def api_traces():
    return jsonify(_load_traces())


if __name__ == "__main__":
    port = int(os.getenv("DASHBOARD_PORT", "5001"))
    print(f"Dashboard running at http://localhost:{port}")
    app.run(port=port, debug=False)
