"""Build the Maya Workflow Kit packages into dist/.

    python tools/build.py [--blender PATH] [--no-legacy]

Outputs:
  dist/maya-workflow-kit-<version>.zip         Blender 4.2+ extension (id ``allset`` inside)
  dist/maya-workflow-kit-<version>-legacy.zip  legacy add-on zip (folder allset/, uses bl_info)

The file names follow the product name; the extension id, package and module stay ``allset``.

The extension is built with ``blender --command extension build`` (it also
validates the manifest). When Blender is not available it falls back to a
plain zip of src/allset with the manifest at the archive root, which is the
layout the extension builder produces.

The build runs Blender with a throwaway user config inside tmp/ so the
user's real Blender settings are never read or written.
"""

import argparse
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "allset"
DIST = ROOT / "dist"
# Main target: Blender 5.2 LTS, the portable 5.2.3 build; 5.0 / 5.1 are run with
# ``--blender`` / ``BLENDER``. Blender 4.5 is not supported since 0.7.0.
BLENDER_52 = os.path.join(os.environ.get("LOCALAPPDATA", ""), "allset_blenders", "blender-5.2.3-windows-x64",
                          "blender.exe")
DEFAULT_BLENDER = BLENDER_52

# Zip file name stem = the product name. `extension build` would name the file after the
# manifest id; the output path is passed explicitly.
ZIP_STEM = "maya-workflow-kit"

EXCLUDE_DIRS = {"__pycache__", ".git"}
EXCLUDE_SUFFIXES = {".pyc", ".zip", ".blend1"}


def manifest_value(key):
    text = (SRC / "blender_manifest.toml").read_text(encoding="utf-8")
    m = re.search(rf'^{key}\s*=\s*"([^"]+)"', text, re.M)
    if not m:
        raise SystemExit(f"blender_manifest.toml: '{key}' not found")
    return m.group(1)


def ext_zip(version=None, folder=None):
    """dist/maya-workflow-kit-<version>.zip (the extension package)."""
    return (folder or DIST) / f"{ZIP_STEM}-{version or manifest_value('version')}.zip"


def legacy_zip(version=None, folder=None):
    return (folder or DIST) / f"{ZIP_STEM}-{version or manifest_value('version')}-legacy.zip"


def iter_source_files():
    for path in sorted(SRC.rglob("*")):
        if path.is_dir():
            continue
        rel = path.relative_to(SRC)
        if EXCLUDE_DIRS.intersection(rel.parts) or path.suffix in EXCLUDE_SUFFIXES:
            continue
        yield path, rel


def sandbox_env():
    """Environment that points Blender's user dirs into tmp/build_env."""
    base = ROOT / "tmp" / "build_env"
    env = os.environ.copy()
    for var, sub in (("BLENDER_USER_CONFIG", "config"),
                     ("BLENDER_USER_SCRIPTS", "scripts"),
                     ("BLENDER_USER_EXTENSIONS", "extensions")):
        d = base / sub
        d.mkdir(parents=True, exist_ok=True)
        env[var] = str(d)
    return env


def build_extension_with_blender(blender, out):
    cmd = [blender, "--factory-startup", "--command", "extension", "build",
           "--source-dir", str(SRC), "--output-filepath", str(out)]
    # stdin must not be inherited: with an interactive stdin the command can hang.
    from blender_slots import slot      # machine-wide Blender slots
    with slot("tools/build.py extension build"):
        r = subprocess.run(cmd, env=sandbox_env(), stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, timeout=300)
    sys.stdout.write(r.stdout)
    sys.stderr.write(r.stderr)
    if r.returncode != 0 or not out.exists():
        raise SystemExit(f"extension build failed (exit {r.returncode})")


def build_extension_fallback(out):
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, rel in iter_source_files():
            zf.write(path, rel.as_posix())


def legacy_bl_info():
    """The legacy add-on's ``bl_info``, from the manifest (the extension source has none)."""
    version = tuple(int(p) for p in manifest_value("version").split("."))
    blender = tuple(int(p) for p in manifest_value("blender_version_min").split("."))
    return ("\n\n# Legacy add-on metadata, added by tools/build.py (extensions read blender_manifest.toml).\n"
            "bl_info = {\n"
            f"    \"name\": {manifest_value('name')!r},\n"
            "    \"author\": \"5hyuns\",\n"
            f"    \"version\": {version!r},\n"
            f"    \"blender\": {blender!r},\n"
            "    \"location\": \"Preferences > Add-ons\",\n"
            f"    \"description\": {manifest_value('tagline')!r},\n"
            "    \"category\": \"Interface\",\n"
            "}\n")


def build_legacy(out):
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, rel in iter_source_files():
            if rel.name == "blender_manifest.toml":
                continue
            if rel.as_posix() == "__init__.py":
                zf.writestr(("allset" / rel).as_posix(), path.read_text(encoding="utf-8") + legacy_bl_info())
                continue
            zf.write(path, ("allset" / rel).as_posix())


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--blender", default=os.environ.get("BLENDER", DEFAULT_BLENDER))
    ap.add_argument("--no-legacy", action="store_true", help="skip the legacy add-on zip")
    args = ap.parse_args(argv)

    version = manifest_value("version")
    DIST.mkdir(exist_ok=True)

    ext = ext_zip(version)
    ext.unlink(missing_ok=True)
    if Path(args.blender).is_file():
        build_extension_with_blender(args.blender, ext)
    else:
        print(f"Blender not found at {args.blender}; using plain zip fallback")
        build_extension_fallback(ext)
    print(f"built {ext.relative_to(ROOT)}")

    if not args.no_legacy:
        legacy = legacy_zip(version)
        build_legacy(legacy)
        print(f"built {legacy.relative_to(ROOT)}")
    return ext


if __name__ == "__main__":
    main()
