"""QA shared helpers (run inside Blender or plain Python): findings file, JSON output."""

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "tmp" / "qa240"


def out_dir():
    OUT.mkdir(parents=True, exist_ok=True)
    return OUT


def add_finding(fid, activity, severity, repro, oracle, version):
    """Append one finding to tmp/qa240/findings.jsonl (an id already there is not written again)."""
    path = out_dir() / "findings.jsonl"
    seen = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                seen.add(json.loads(line)["id"])
            except Exception:
                pass
    if fid in seen:
        return False
    rec = {"id": fid, "activity": activity, "severity": severity, "repro": repro, "oracle": oracle,
           "version": version}
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return True


def write_json(name, data):
    path = out_dir() / name
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    return path


def git_head():
    try:
        head = (ROOT / ".git" / "HEAD").read_text().strip()
        if head.startswith("ref:"):
            return (ROOT / ".git" / head[5:]).read_text().strip()[:7]
        return head[:7]
    except Exception:
        return "?"


def env_tag():
    return os.environ.get("ALLSET_SANDBOX", "default")
