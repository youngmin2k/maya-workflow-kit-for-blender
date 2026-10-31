"""Headless test harness for Maya Workflow Kit.

    python tests/run.py [-k PATTERN] [--no-build] [--blender PATH]

1. Builds dist/maya-workflow-kit-<version>.zip with tools/build.py (skip: --no-build).
2. Recreates a sandbox tmp/test_env/{config,scripts,extensions} and points
   BLENDER_USER_CONFIG / BLENDER_USER_SCRIPTS / BLENDER_USER_EXTENSIONS at it,
   so the real %APPDATA%/Blender Foundation is never touched.
3. Installs the zip into the sandbox "user_default" repository with
   ``blender --command extension install-file``.
4. Runs every tests/test_*.py in its own ``blender -b --factory-startup``
   process through tests/_bootstrap.py, which enables the extension (unless
   the test module sets ``AUTO_ENABLE = False``), runs each ``test_*``
   function and writes a JSON result.
5. Prints PASS/FAIL/SKIP per test and a summary (SKIP = a test raised kit.Skip:
   something this machine or clone lacks). Exit code 1 if anything failed.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"
# ALLSET_SANDBOX: another folder under tmp/ so runs on several Blender versions can go in parallel
SANDBOX = ROOT / "tmp" / os.environ.get("ALLSET_SANDBOX", "test_env")
REPO_ID = "user_default"
PKG_ID = "allset"
MODULE = f"bl_ext.{REPO_ID}.{PKG_ID}"
TIMEOUT = 300

sys.path.insert(0, str(ROOT / "tools"))
import blender_slots  # noqa: E402
import build  # noqa: E402


def make_sandbox():
    assert SANDBOX.resolve().is_relative_to(ROOT / "tmp"), SANDBOX
    if SANDBOX.exists():
        shutil.rmtree(SANDBOX)
    env = os.environ.copy()
    for var, sub in (("BLENDER_USER_CONFIG", "config"),
                     ("BLENDER_USER_SCRIPTS", "scripts"),
                     ("BLENDER_USER_EXTENSIONS", "extensions")):
        d = SANDBOX / sub
        d.mkdir(parents=True)
        env[var] = str(d)
    (SANDBOX / "logs").mkdir()
    (SANDBOX / "results").mkdir()
    # the default Maya Workflow Kit project (operators/project.default_root) lives in the sandbox, not in Documents
    env["ALLSET_PROJECTS_DIR"] = str(SANDBOX / "projects")
    env["ALLSET_MODULE"] = MODULE
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONUNBUFFERED"] = "1"     # logs survive a timeout kill
    # a Blender started from inside a test's Blender (lifecycle / switch tests) rides on the parent's slot
    env["ALLSET_NO_SLOTS"] = "1"
    return env


def blender_run(blender, args, env, log):
    # stdin=DEVNULL: `blender --command ...` hangs when it inherits a console stdin.
    # one of the machine-wide Blender slots (tools/blender_slots.py) while it runs
    with blender_slots.slot(f"tests/run.py {Path(log).stem}"), \
            open(log, "w", encoding="utf-8", errors="replace") as fh:
        r = subprocess.run([blender, *args], env=env, stdin=subprocess.DEVNULL,
                           stdout=fh, stderr=subprocess.STDOUT, timeout=TIMEOUT)
    return r.returncode


def install(blender, zip_path, env):
    log = SANDBOX / "logs" / "install.log"
    rc = blender_run(blender, ["--factory-startup", "--command", "extension", "install-file",
                               "-r", REPO_ID, str(zip_path)], env, log)
    installed = SANDBOX / "extensions" / REPO_ID / PKG_ID / "__init__.py"
    if rc != 0 or not installed.exists():
        print(log.read_text(encoding="utf-8", errors="replace"))
        raise SystemExit(f"install failed (exit {rc}); see {log}")


def run_test_file(blender, path, env):
    log = SANDBOX / "logs" / f"{path.stem}.log"
    out = SANDBOX / "results" / f"{path.stem}.json"
    args = ["-b", "--factory-startup", "--python-exit-code", "1",
            "--python", str(TESTS / "_bootstrap.py"), "--", str(path), str(out)]
    t0 = time.time()
    try:
        rc = blender_run(blender, args, env, log)
    except subprocess.TimeoutExpired:
        rc = "timeout"
    dt = time.time() - t0
    if out.exists():
        results = json.loads(out.read_text(encoding="utf-8"))
    else:
        results = [{"name": "<file>", "ok": False,
                    "error": f"no result file (blender exit {rc})"}]
    return results, log, dt


def add_order_args(ap):
    """Release QA (activity A): file order is a test input too (order-dependent failures, M59-4)."""
    ap.add_argument("--shuffle", type=int, default=None, metavar="SEED", help="run the files in a seeded random order")
    ap.add_argument("--reverse", action="store_true", help="run the files in reverse order")
    ap.add_argument("--order", default="", help="file with one test file stem per line: run exactly these, in this order")
    ap.add_argument("--extra", default="", help="comma-separated extra test module paths (tools/qa harnesses)")
    ap.add_argument("--zip", default="", help="install this extension zip instead of the current build (QA: older release)")


def order(files, args):
    if args.extra:
        files = files + [Path(p).resolve() for p in args.extra.split(",") if p]
    if args.order:
        by_stem = {p.stem: p for p in files}
        wanted = [line.strip() for line in Path(args.order).read_text(encoding="utf-8").splitlines() if line.strip()]
        files = [by_stem[s] for s in wanted if s in by_stem]
    if args.shuffle is not None:
        import random
        random.Random(args.shuffle).shuffle(files)
    if args.reverse:
        files = files[::-1]
    if args.shuffle is not None or args.reverse or args.order:
        print("order: " + " ".join(p.stem for p in files))
    return files


def main(argv=None):
    ap = argparse.ArgumentParser(description="Run Maya Workflow Kit headless tests")
    ap.add_argument("-k", default="", help="only test files whose name contains this (comma-separated: any of them)")
    ap.add_argument("--no-build", action="store_true")
    ap.add_argument("--blender", default=os.environ.get("BLENDER", build.DEFAULT_BLENDER))
    add_order_args(ap)
    args = ap.parse_args(argv)

    if not Path(args.blender).is_file():
        raise SystemExit(f"Blender not found: {args.blender}")

    if args.zip:
        zip_path = Path(args.zip).resolve()
    elif args.no_build:
        zip_path = build.ext_zip()
    else:
        zip_path = build.main(["--blender", args.blender, "--no-legacy"])

    env = make_sandbox()
    install(args.blender, zip_path, env)

    pats = args.k.split(",")
    files = order(sorted(p for p in TESTS.glob("test_*.py") if any(k in p.name for k in pats)), args)
    passed = failed = skipped = 0
    for path in files:
        results, log, dt = run_test_file(args.blender, path, env)
        file_failed = False
        for r in results:
            status = "SKIP" if "skipped" in r else "PASS" if r["ok"] else "FAIL"
            print(f"{status}  {path.stem}::{r['name']}")
            if "skipped" in r:
                skipped += 1
                print("      " + r["skipped"])
            elif r["ok"]:
                passed += 1
            else:
                failed += 1
                file_failed = True
                print("      " + r.get("error", "").replace("\n", "\n      "))
        print(f"      ({dt:.1f}s, log: {log.relative_to(ROOT)})")
        if file_failed:
            tail = log.read_text(encoding="utf-8", errors="replace").splitlines()[-30:]
            print("      --- log tail ---\n      " + "\n      ".join(tail))

    print(f"\n{passed} passed, {failed} failed, {skipped} skipped, {len(files)} file(s)")
    return 1 if failed or not files else 0


if __name__ == "__main__":
    sys.exit(main())
