"""Release smoke on every supported Blender minor (#198 #199).

    python tools/smoke_matrix.py                          # 5.0.1, 5.1.2, 5.2.3 (portable builds)
    python tools/smoke_matrix.py --blenders 5.1.2         # one version (or a path to blender.exe)
    python tools/smoke_matrix.py --headless-only / --gui-only

For each Blender, one after the other: the headless smoke files (enable / disable, the Maya / Blender switch, its
rollback, the menu draws) and the GUI smoke files (enable, Maya mode with the Maya layout, open a Maya menu, back to
Blender; the layout files), each Blender in its own sandbox ``tmp/<ALLSET_SANDBOX or smoke>_<ver>``. The extension
is built once. GUI Blenders run on the hidden desktop (the GUI runner moves itself there); the runners take a
Blender slot per process. Exit 1 if anything failed.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build  # noqa: E402

BLENDERS = "5.0.1,5.1.2,5.2.3"       # the newest patch release of every supported minor
HEADLESS = "step279,enable_disable,step60_switch,issue185_switch_back,step115,step130_lifecycle"
GUI = "step279,switch,layout"
PORTABLE = Path(os.environ.get("ALLSET_BLENDERS",
                               os.path.join(os.environ.get("LOCALAPPDATA", ""), "allset_blenders")))


def blender_exe(ver):
    if "/" in ver or "\\" in ver:
        return ver
    return str(PORTABLE / f"blender-{ver}-windows-x64" / "blender.exe")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--blenders", default=BLENDERS, help=f"comma-separated versions or paths (default {BLENDERS})")
    ap.add_argument("--headless", default=HEADLESS, help="-k for tests/run.py")
    ap.add_argument("--gui", default=GUI, help="-k for the GUI runner")
    ap.add_argument("--headless-only", action="store_true")
    ap.add_argument("--gui-only", action="store_true")
    ap.add_argument("--no-build", action="store_true")
    args = ap.parse_args(argv)

    if not args.no_build:
        build.main(["--blender", build.DEFAULT_BLENDER, "--no-legacy"])
    base = os.environ.get("ALLSET_SANDBOX", "smoke")
    rows = []
    for n, ver in enumerate(v.strip() for v in args.blenders.split(",") if v.strip()):
        exe = blender_exe(ver)
        if not Path(exe).exists():
            rows.append((ver, "missing", exe))
            continue
        env = dict(os.environ, ALLSET_SANDBOX=f"{base}_{ver if exe != ver else n}")
        runs = []
        if not args.gui_only:
            runs.append(("headless", [sys.executable, str(ROOT / "tests" / "run.py"), "--no-build", "--blender", exe,
                                      "-k", args.headless]))
        if not args.headless_only:
            runs.append(("gui", [sys.executable, str(ROOT / "tests" / "gui" / "run.py"), "--no-build", "--blender",
                                 exe, "-k", args.gui]))
        for kind, cmd in runs:
            print(f"\n=== Blender {ver}: {kind} (sandbox tmp/{env['ALLSET_SANDBOX']}) ===", flush=True)
            code = subprocess.call(cmd, env=env, stdin=subprocess.DEVNULL, cwd=str(ROOT))
            rows.append((ver, kind, "ok" if code == 0 else f"FAILED (exit {code})"))
    print("\nSmoke matrix:")
    for row in rows:
        print("  " + " | ".join(row))
    return 1 if any(r[-1] != "ok" for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
