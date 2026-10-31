"""QA activity I: change impact map since the previous release tag.

For every changed file under src/: lines changed, which test files mention its module, and a risk score
(lines x past bug count from commit messages x exposure). Files no test mentions are listed
first: activities B / D / J aim at them.

    python tools/qa/risk_map.py [--since v0.5.0] [--out tmp/qa240/risk_map.md]
"""

import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def changed(since):
    rows = []
    for line in git("diff", "--numstat", f"{since}..HEAD", "--", "src").splitlines():
        add, rem, path = line.split("\t")
        if not path.endswith(".py"):
            continue
        rows.append((path, int(add) + int(rem)))
    return rows


def tests_for(module):
    hits = []
    for folder in ("tests", "tests/gui", "tests/integration"):
        for f in sorted((ROOT / folder).glob("*.py")):
            text = f.read_text(encoding="utf-8", errors="replace")
            if re.search(rf"\b{re.escape(module)}\b", text):
                hits.append(f.relative_to(ROOT).as_posix())
    return hits


def bug_count(module):
    """Commits that touched the module with 'fix' in the message (all history): a rough bug-proneness."""
    out = git("log", "--oneline", "-i", "--grep=fix", "--", f"src/allset/**/{module}.py")
    return len(out.splitlines())


def exposure(path):
    # menus / hotkeys / UI shown to every user count more than one-path operators
    if "/ui/" in path or path.endswith(("switch.py", "preferences.py")) or "/marking/" in path:
        return 3
    if "/keymap/" in path:
        return 3
    return 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="v0.5.0")
    ap.add_argument("--out", default=str(ROOT / "tmp" / "qa240" / "risk_map.md"))
    args = ap.parse_args()
    rows = []
    for path, lines in changed(args.since):
        module = Path(path).stem
        if module == "__init__":
            continue
        tests = tests_for(module)
        bugs = bug_count(module)
        score = round(lines / 50 + bugs / 5 + exposure(path), 1)
        rows.append({"file": path, "lines": lines, "bugs": bugs, "tests": tests, "score": score})
    rows.sort(key=lambda r: (bool(r["tests"]), -r["score"]))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    md = [f"# Change impact map since {args.since}", "",
          "| file | lines | fix commits | tests | score |", "|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r['file']} | {r['lines']} | {r['bugs']} | {len(r['tests'])} | {r['score']} |")
    untested = [r["file"] for r in rows if not r["tests"]]
    md += ["", f"untested changed files: {len(untested)}"] + [f"- {u}" for u in untested]
    out.write_text("\n".join(md) + "\n", encoding="utf-8")
    out.with_suffix(".json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
