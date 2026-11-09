"""Export every notebook task of a job run (code + printed outputs) to plain-text Markdown under evidence/notebook_runs/.

Usage: uv run --with databricks-sdk python scripts/export_run_notebooks.py <job_run_id> [subfolder]

The Jobs API returns each executed notebook as HTML with the notebook model embedded (base64 + URL-encoded JSON);
this script decodes it and writes the cell sources and their text results, so execution evidence is readable as text.
"""
import base64
import json
import os
import re
import sys
import urllib.parse
from pathlib import Path

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.jobs import ViewsToExport

PROFILE = os.environ.get("DATABRICKS_CONFIG_PROFILE", "serverless-stable-3vku19")
OUT = Path(__file__).resolve().parents[1] / "evidence" / "notebook_runs"
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def decode_model(html: str) -> dict:
    m = re.search(r"__DATABRICKS_NOTEBOOK_MODEL = '([^']+)'", html)
    raw = base64.b64decode(m.group(1)).decode("utf-8")
    return json.loads(urllib.parse.unquote(raw))


def result_text(res) -> str:
    if not res:
        return ""
    t = res.get("type")
    data = res.get("data")
    if t in ("listResults",):
        return "\n".join(result_text(r) for r in data or [])
    if t == "table":
        cols = [c.get("name") for c in res.get("schema", [])]
        rows = data or []
        lines = [" | ".join(cols)] + [" | ".join(str(v) for v in r) for r in rows[:50]]
        return "\n".join(lines)
    if isinstance(data, str):
        return ANSI.sub("", data)
    return ""


def main(run_id: int, sub: str = ""):
    global OUT
    OUT = OUT / sub if sub else OUT
    w = WorkspaceClient(profile=PROFILE)
    run = w.jobs.get_run(run_id)
    OUT.mkdir(parents=True, exist_ok=True)
    index = [f"# Notebook outputs for job run {run_id}\n", f"Job: `{run.run_name}` | result: **{run.state.result_state.value if run.state.result_state else run.state.life_cycle_state.value}**\n"]
    for t in sorted(run.tasks or [], key=lambda t: t.start_time or 0):
        if not t.notebook_task or not t.state or not t.state.result_state or t.state.result_state.value not in ("SUCCESS", "FAILED"):
            continue
        try:
            exp = w.jobs.export_run(t.run_id, views_to_export=ViewsToExport.CODE)
        except Exception as e:
            print("skip", t.task_key, e)
            continue
        model = decode_model(exp.views[0].content)
        md = [f"# Task `{t.task_key}` - {t.state.result_state.value}\n",
              f"- Task run id: `{t.run_id}`\n- Notebook: `{t.notebook_task.notebook_path}`\n- Duration: {round((t.execution_duration or 0) / 1000)} s\n"]
        for i, cmd in enumerate(model.get("commands", []), 1):
            src = cmd.get("command", "").strip()
            if not src:
                continue
            lang = "sql" if src.startswith("%sql") else ("markdown" if src.startswith("%md") else "python")
            md.append(f"\n## Cell {i}\n\n```{lang}\n{src}\n```\n")
            out = result_text(cmd.get("results")).strip()
            err = ANSI.sub("", cmd.get("error") or "").strip()
            if out:
                md.append(f"\n**Output**\n\n```text\n{out[:20000]}\n```\n")
            if err:
                md.append(f"\n**Error**\n\n```text\n{err[:4000]}\n```\n")
        name = f"{t.task_key}.md"
        (OUT / name).write_text("".join(md))
        index.append(f"- [{t.task_key}]({name}) - {t.state.result_state.value}, {round((t.execution_duration or 0) / 1000)} s\n")
        print("wrote", name)
    (OUT / "README.md").write_text("".join(index))


if __name__ == "__main__":
    main(int(sys.argv[1]), sys.argv[2] if len(sys.argv) > 2 else "")
