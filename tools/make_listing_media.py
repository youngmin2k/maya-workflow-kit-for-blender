"""extensions.blender.org listing media: docs/distribution/media/.

    python tools/make_listing_media.py [--blender PATH] [--no-build] [--no-shots]

Runs tools/marketing/make_marketing.py (licensed scene, GUI shots in a clean sandbox, Pillow compositing; the user's
Blender settings are never read or written) and copies its outputs under the listing names:
icon.png (256 x 256), featured.png (1920 x 1080 key visual) and 01_*.png ... 10_*.png (1920 x 1080 captioned
screens, in upload order).
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MEDIA = ROOT / "docs" / "distribution" / "media"
MARKETING = ROOT / "docs" / "distribution" / "marketing"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--blender", default=None)
    ap.add_argument("--no-build", action="store_true")
    ap.add_argument("--no-shots", action="store_true", help="reuse tmp/marketing/raw")
    args = ap.parse_args(argv)
    cmd = [sys.executable, str(ROOT / "tools" / "marketing" / "make_marketing.py")]
    if args.blender:
        cmd += ["--blender", args.blender]
    if args.no_build:
        cmd.append("--no-build")
    if args.no_shots:
        cmd.append("--no-shots")
    rc = subprocess.run(cmd, stdin=subprocess.DEVNULL).returncode
    if rc:
        return rc
    MEDIA.mkdir(parents=True, exist_ok=True)
    for old in MEDIA.glob("*.png"):
        old.unlink()
    shutil.copy2(MARKETING / "icon_256.png", MEDIA / "icon.png")
    shutil.copy2(MARKETING / "key_visual.png", MEDIA / "featured.png")
    for p in sorted((MARKETING / "screens").glob("*.png")):
        shutil.copy2(p, MEDIA / p.name)
    print("media:", ", ".join(sorted(p.name for p in MEDIA.glob("*.png"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
