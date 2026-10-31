"""QA activity H: drive a clean Maya Workflow Kit install from a list of user actions.

    python tools/qa/fresh_eye.py ACTIONS.json [--out DIR] [--blender PATH] [--reinstall]

For an exploratory tester who doesn't read the code: ACTIONS.json is a list of plain user actions (keys, clicks,
drags, Maya menu items by their menu path, screenshots, a state dump). The first run installs the current dist zip
into the sandbox tmp/qa_h (never the real Blender config) and keeps it; each run starts a fresh GUI Blender on the
hidden desktop in the Maya layout and writes, to --out (default tmp/qa240/h/<actions name>/):
  NN_<label>.png  a screenshot after every action (the window, 1600 x 900),
  log.json        per action: what ran, kit reports / Python errors seen, a state dump when asked,
  console.log     the Blender console.

Action forms (x, y = window pixels from the bottom-left; "view" = centre of the main 3D view):
  {"key": "W"}  {"key": "Z", "ctrl": true}  {"key": "SPACE", "hold": true}  {"key": "A", "at": "view"}
  {"click": "view"}  {"click": [800, 450], "button": "RIGHTMOUSE", "shift": true}
  {"drag": ["view", [900, 500]], "button": "LEFTMOUSE", "alt": true}
  {"press": [x, y], "button": "RIGHTMOUSE"}  {"move": [x, y]}  {"release": [x, y], "button": "RIGHTMOUSE"}
  {"menu": "Create/Polygon Primitives/Cube"}      Maya main-menu item by its path (as a click on it would run)
  {"menus": "Create"}                              list the item paths under a Maya menu (into log.json)
  {"type": "text"}                                 text typed into the field under the mouse
  {"state": true}   {"wait": 3}   {"shot": "label"}
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("ALLSET_SANDBOX", "qa_h")
import run as headless  # noqa: E402

SESSION = Path(__file__).resolve().parent / "fresh_eye_session.py"
TIMEOUT = 600


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("actions")
    ap.add_argument("--out", default="")
    ap.add_argument("--blender", default=os.environ.get("BLENDER", headless.build.DEFAULT_BLENDER))
    ap.add_argument("--reinstall", action="store_true")
    args = ap.parse_args(argv)
    actions = Path(args.actions).resolve()
    out = Path(args.out).resolve() if args.out else ROOT / "tmp" / "qa240" / "h" / actions.stem
    out.mkdir(parents=True, exist_ok=True)
    for p in out.glob("*.png"):
        p.unlink()
    installed = headless.SANDBOX / "extensions" / headless.REPO_ID / headless.PKG_ID / "__init__.py"
    if args.reinstall or not installed.exists():
        env = headless.make_sandbox()
        headless.install(args.blender, headless.build.ext_zip(), env)
    env = os.environ.copy()
    for var, sub in (("BLENDER_USER_CONFIG", "config"), ("BLENDER_USER_SCRIPTS", "scripts"),
                     ("BLENDER_USER_EXTENSIONS", "extensions")):
        env[var] = str(headless.SANDBOX / sub)
    env.update(ALLSET_PROJECTS_DIR=str(headless.SANDBOX / "projects"), ALLSET_MODULE=headless.MODULE,
               ALLSET_NO_WELCOME="1", PYTHONUNBUFFERED="1", PYTHONDONTWRITEBYTECODE="1", ALLSET_NO_SLOTS="1",
               QA_ACTIONS=str(actions), QA_OUT=str(out))
    cmd = [args.blender, "--factory-startup", "--enable-event-simulate", "--window-geometry", "0", "0", "1600", "900",
           "--python", str(SESSION), "--", str(out / "checks.json")]
    with headless.blender_slots.slot(f"qa fresh_eye {actions.stem}"), \
            open(out / "console.log", "w", encoding="utf-8", errors="replace") as fh:
        proc = subprocess.Popen(cmd, env=env, stdin=subprocess.DEVNULL, stdout=fh, stderr=subprocess.STDOUT)
        try:
            proc.wait(timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            proc.kill()
            print("TIMEOUT: the session was killed")
    log = out / "log.json"
    if log.exists():
        for i, rec in enumerate(json.loads(log.read_text(encoding="utf-8"))):
            line = f"{i:02d} {rec['action']}"
            if rec.get("errors"):
                line += "  ERRORS: " + " | ".join(rec["errors"])
            if rec.get("reports"):
                line += "  REPORTS: " + " | ".join(rec["reports"])
            print(line)
            if rec.get("state"):
                print("     state:", json.dumps(rec["state"]))
            if rec.get("menus"):
                print("     items:", "; ".join(rec["menus"]))
    else:
        print("no log.json — Blender ended early; see", out / "console.log")
    print("screenshots in", out)


if __name__ == "__main__":
    import hidden_desktop  # noqa: E402  (test Blenders never show on screen)
    hidden_desktop.ensure_hidden()
    sys.exit(main())
