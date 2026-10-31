"""Dogfood run: clean-config install, then a scripted Maya user session in a GUI Blender.

    python tools/dogfood.py [--blender PATH] [--session SCRIPT]

Builds and installs the extension into a fresh sandbox exactly like
tools/release_check.py (tmp/release_env; the user's real Blender settings are
never touched), then runs tools/dogfood_session.py in a GUI Blender with
--enable-event-simulate. Prints each check, the screenshots written to
tmp/dogfood/shots/ and every console error/traceback line of the session log.
Only the Blender process started here is terminated on timeout.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import build  # noqa: E402
import release_check as rc  # noqa: E402

OUT = ROOT / "tmp" / "dogfood"
ERROR_RE = re.compile(r"Traceback|Error|error:|WARN|Warning", re.I)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--blender", default=os.environ.get("BLENDER", build.DEFAULT_BLENDER))
    ap.add_argument("--session", default=str(ROOT / "tools" / "dogfood_session.py"),
                    help="session script (other scripts write to tmp/dogfood/<script name>/)")
    args = ap.parse_args(argv)
    session = Path(args.session).resolve()
    out_dir = OUT if session.name == "dogfood_session.py" else OUT / session.stem

    zip_path = build.main(["--blender", args.blender])
    env = rc.sandbox_env()
    env["ALLSET_NO_WELCOME"] = "1"   # the first-start dialog would eat the simulated events
    code, out = rc.run([args.blender, "--command", "extension", "install-file", "-r", rc.REPO_ID,
                        "--enable", str(zip_path)], env)
    if code != 0:
        print(out[-3000:])
        return 1
    shots = out_dir / "shots"
    shots.mkdir(parents=True, exist_ok=True)
    for p in shots.glob("*.png"):
        p.unlink()
    result, log = out_dir / "dogfood.json", out_dir / "dogfood.log"
    result.unlink(missing_ok=True)
    env["ALLSET_DOGFOOD_SHOTS"] = str(shots)
    cmd = [args.blender, "--enable-event-simulate", "--window-geometry", "0", "0", "1600", "900",
           "--python", str(session), "--", str(result)]
    with open(log, "w", encoding="utf-8", errors="replace") as fh:
        proc = subprocess.Popen(cmd, env=env, stdin=subprocess.DEVNULL, stdout=fh,
                                stderr=subprocess.STDOUT)
        try:
            proc.wait(timeout=rc.TIMEOUT)
        except subprocess.TimeoutExpired:
            proc.kill()  # only the Blender started here
    checks = json.loads(result.read_text(encoding="utf-8")) if result.exists() else \
        [{"name": f"dogfood_session.py wrote no results (see {log})", "ok": False}]
    for c in checks:
        print("PASS" if c["ok"] else "FAIL", c["name"])
    print("screenshots:", ", ".join(sorted(p.name for p in shots.glob("*.png"))))
    errors = [ln.rstrip() for ln in log.read_text(encoding="utf-8", errors="replace").splitlines()
              if ERROR_RE.search(ln) and not ln.startswith("GUI ")]
    print(f"console error/warning lines: {len(errors)}")
    for ln in errors:
        print("  ", ln)
    return 0 if all(c["ok"] for c in checks) and not errors else 1


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
    import hidden_desktop  # noqa: E402  (test Blenders never show on screen)
    hidden_desktop.ensure_hidden()
    sys.exit(main())
