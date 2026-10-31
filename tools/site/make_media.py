"""Web copies of marketing media for site/media."""
import json, os, shutil, subprocess, sys
from pathlib import Path
from PIL import Image

ROOT = Path(r"C:\Repos\blender-maya-kit")
BIN = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "tools" / "ffmpeg-9.0.1-win32-x64" / "bin"
FF, FP = str(BIN / "ffmpeg.exe"), str(BIN / "ffprobe.exe")
MK = ROOT / "docs/distribution/marketing"
OUT = ROOT / "site/media"
# what site/index.html and app.js use (#41: the full lists left 32 unused files in site/media)
CLIPS = ["01_hotbox", "03_channel_box_keys", "04_navigation", "05_pivot_snap", "06_rigging"]
RAW = ["hero", "menus_shelves", "switch_before"]
VF = "scale=1280:-2:flags=lanczos"
LOG = []

def run(args):
    subprocess.run([FF, "-hide_banner", "-loglevel", "error", "-y", *args],
                   check=True, stdin=subprocess.DEVNULL)

def mp4(src, dst, limit, crf=22):
    while True:
        run(["-i", str(src), "-an", "-vf", VF, "-c:v", "libx264", "-profile:v", "high",
             "-pix_fmt", "yuv420p", "-preset", "veryslow", "-tune", "animation", "-crf", str(crf),
             "-movflags", "+faststart", str(dst)])
        if dst.stat().st_size <= limit or crf >= 34:
            LOG.append((dst.name, f"x264 crf {crf}")); return
        crf += 1

def webm(src, dst, limit, crf=34):
    while True:
        run(["-i", str(src), "-an", "-vf", VF, "-c:v", "libvpx-vp9", "-crf", str(crf), "-b:v", "0",
             "-deadline", "good", "-cpu-used", "2", "-row-mt", "1", "-pix_fmt", "yuv420p", str(dst)])
        if dst.stat().st_size <= limit or crf >= 50:
            LOG.append((dst.name, f"vp9 crf {crf}")); return
        crf += 2

def poster(src, stem, t):
    png = OUT / f"_{stem}.png"
    run(["-ss", str(t), "-i", str(src), "-frames:v", "1", "-vf", VF, str(png)])
    im = Image.open(png).convert("RGB")
    q = 82
    while True:
        im.save(OUT / f"{stem}.jpg", quality=q, optimize=True, progressive=True)
        if (OUT / f"{stem}.jpg").stat().st_size <= 150_000 or q <= 60: break
        q -= 4
    im.save(OUT / f"{stem}.webp", quality=80, method=6)
    LOG.append((f"{stem}.jpg", f"jpeg q{q} @ {t}s"))
    png.unlink()

def still(name):
    im = Image.open(ROOT / "tmp/marketing/raw" / f"{name}.png").convert("RGB")
    for w, sfx in ((1600, ""), (800, "-800")):
        r = im.resize((w, round(im.height * w / im.width)), Image.LANCZOS)
        r.save(OUT / f"shot-{name}{sfx}.webp", quality=80, method=6)
        if sfx == "":
            r.save(OUT / f"shot-{name}.jpg", quality=82, optimize=True, progressive=True)

def probe(p):
    if p.suffix in (".mp4", ".webm"):
        o = json.loads(subprocess.check_output([FP, "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height:format=duration", "-of", "json", str(p)],
            stdin=subprocess.DEVNULL))
        s = o["streams"][0]
        return s["width"], s["height"], round(float(o["format"]["duration"]), 3)
    with Image.open(p) as im:
        return im.width, im.height, None

def main():
    only = set(sys.argv[1:])
    if not only or "video" in only:
        for c in CLIPS:
            src = MK / "clips" / f"{c}.mp4"; stem = c.split("_", 1)[1]
            mp4(src, OUT / f"{stem}.mp4", 1_200_000)
            webm(src, OUT / f"{stem}.webm", 900_000)
            poster(src, stem, 0.5)
        src = MK / "clips/00_trailer.mp4"
        mp4(src, OUT / "trailer.mp4", 4_000_000)
        webm(src, OUT / "trailer.webm", 3_000_000)
        poster(src, "trailer", 0)
    if not only or "stills" in only:
        for n in RAW: still(n)
        shutil.copyfile(MK / "kit/social_preview.png", OUT / "og.png")
        master = Image.open(MK / "icon/icon_1024.png").convert("RGBA")        # icon master (link_a)
        master.resize((256, 256), Image.LANCZOS).save(OUT / "icon-256.png", optimize=True)
        master.resize((180, 180), Image.LANCZOS).save(OUT / "favicon-180.png", optimize=True)
        Image.open(MK / "icon/icon_32.png").convert("RGBA").save(OUT / "favicon-32.png", optimize=True)  # hand-hinted 32 px
    files, total = [], 0
    for p in sorted(OUT.iterdir()):
        if p.name == "media.json" or p.name.startswith("_") or p.suffix == ".json": continue   # *.webp.json = image provenance
        w, h, d = probe(p); b = p.stat().st_size; total += b
        e = {"path": f"media/{p.name}", "bytes": b, "width": w, "height": h}
        if d is not None: e["duration"] = d
        files.append(e)
    (OUT / "media.json").write_text(json.dumps({"files": files, "total_bytes": total,
        "count": len(files)}, indent=2), encoding="utf-8")
    for n, s in LOG: print(n, s)
    for e in files: print(f'{e["path"]:40} {e["bytes"]:>9} {e["width"]}x{e["height"]} {e.get("duration", "")}')
    print("total", total)

main()
