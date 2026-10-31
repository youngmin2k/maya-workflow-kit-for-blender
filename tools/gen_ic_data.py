"""Generate src/allset/keymap/ic_<major>_<minor>.py: Blender's Industry Compatible keymap data as static Python data.

    python tools/gen_ic_data.py                 # the default 5.2 + every portable 5.x in allset_blenders (ALLSET_BLENDERS)
    python tools/gen_ic_data.py --blender EXE   # one Blender only

The kit's Maya keymap = this data + keymap/maya_patches.py. Earlier the add-on
loaded Blender's ``presets/keyconfig/keymap_data/industry_compatible_data.py`` at run time with
``bpy.utils.execfile``; the extensions store review rejects any exec-style loading (GitHub #40), so this tool
runs that file here, outside the add-on, and writes the result (``generate_keymaps(Params())``) as plain data.

One file per Blender minor whose data differs from the previous minor's file (keymap/ic_data.py picks the newest
file <= the running version). Each file records the Blender build it came from. Re-run after a Blender update.
"""

import argparse
import ast
import os
import pprint
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "src" / "allset" / "keymap"
PORTABLE = Path(os.environ.get("ALLSET_BLENDERS",
                                os.path.join(os.environ.get("LOCALAPPDATA", ""), "allset_blenders")))


def blenders():
    sys.path.insert(0, str(ROOT / "tools"))
    import build
    out = [os.environ.get("BLENDER", build.DEFAULT_BLENDER)]
    if PORTABLE.is_dir():
        out += [str(p / "blender.exe") for p in sorted(PORTABLE.glob("blender-5.*-windows-x64"))
                if (p / "blender.exe").is_file()]
    return out


def run_outside_blender(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--blender", action="append", default=[])
    args = ap.parse_args(argv)
    sys.path.insert(0, str(ROOT / "tools"))
    import build
    rc = 0
    for exe in args.blender or blenders():
        r = subprocess.run([exe, "-b", "--factory-startup", "--python-exit-code", "1", "--python", __file__],
                           env=build.sandbox_env(), stdin=subprocess.DEVNULL, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        for line in r.stdout.splitlines():
            if line.startswith("gen_ic_data"):
                print(line)
        if r.returncode:
            sys.stderr.write(r.stdout[-3000:] + r.stderr[-3000:])
            rc = 1
    return rc


def previous_file(version):
    best = None
    for p in OUT_DIR.glob("ic_*_*.py"):
        v = tuple(int(x) for x in p.stem.split("_")[1:3])
        if v < version and (best is None or v > best[0]):
            best = (v, p)
    return best[1] if best else None


def read_data(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and node.targets[0].id == "DATA":
            return ast.literal_eval(node.value)
    raise LookupError(path)


def in_blender():
    import bpy
    src = os.path.join(bpy.utils.system_resource('SCRIPTS'), "presets", "keyconfig", "keymap_data",
                       "industry_compatible_data.py")
    ic = bpy.utils.execfile(src)   # tool side only: the add-on itself never executes files
    data = ic.generate_keymaps(ic.Params())
    text = pprint.pformat(data, width=118, sort_dicts=False)
    assert ast.literal_eval(text) == data, "IC data is not plain literal data"
    version = tuple(bpy.app.version[:2])
    out = OUT_DIR / f"ic_{version[0]}_{version[1]}.py"
    prev = previous_file(version)
    if prev is not None and read_data(prev) == data:
        if out.exists():
            out.unlink()
        print(f"gen_ic_data {bpy.app.version_string}: same as {prev.name}, no file")
        return
    out.write_text(
        "# SPDX-License-Identifier: GPL-2.0-or-later\n"
        f'"""Industry Compatible keymap data of Blender {bpy.app.version_string} '
        f"(build {bpy.app.build_hash.decode()}) — generated, do not edit.\n\n"
        "Written by tools/gen_ic_data.py from Blender's presets/keyconfig/keymap_data/industry_compatible_data.py\n"
        "(``generate_keymaps(Params())``, GPL-2.0-or-later like Blender). Read by keymap/ic_data.py.\n"
        '"""\n\n'
        f"BLENDER = {bpy.app.version_string!r}\n\n"
        f"DATA = {text}\n", encoding="utf-8", newline="\n")
    print(f"gen_ic_data {bpy.app.version_string}: wrote {out.relative_to(ROOT)} "
          f"({len(data)} keymaps, {sum(len(km[2]['items']) for km in data)} items)")


if __name__ == "__main__":
    try:
        import bpy  # noqa: F401
    except ImportError:
        sys.exit(run_outside_blender(sys.argv[1:]))
    in_blender()
