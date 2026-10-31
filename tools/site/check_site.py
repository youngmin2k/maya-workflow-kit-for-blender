"""Local link / media check and page weight of site/ (no network).

    python tools/site/check_site.py

Every local href / src / srcset / poster in index.html and every media name in its workflows JSON must exist; external
links are listed (not fetched). Weight: what the first view loads (HTML, CSS, JS, font, first poster) and the total of
everything the page can load (all referenced files once).
"""
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

SITE = Path(__file__).resolve().parents[2] / "site"


class Refs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.local, self.external = set(), set()

    def handle_starttag(self, tag, attrs):
        for k, v in attrs:
            if not v or k not in ("href", "src", "srcset", "poster", "content"):
                continue
            for part in ([p.strip().split(" ")[0] for p in v.split(",")] if k == "srcset" else [v]):
                if part.startswith(("http://", "https://")):
                    self.external.add(part)
                elif k != "content" and not part.startswith(("#", "mailto:", "data:")):
                    self.local.add(part)


def main():
    html = (SITE / "index.html").read_text(encoding="utf-8")
    r = Refs()
    r.feed(html)
    data = json.loads(re.search(r'<script type="application/json" id="workflows-data">(.*?)</script>', html, re.S)[1])
    for wf in data.values():
        if wf.get("video"):
            r.local |= {f"media/{wf['video']}.{e}" for e in ("mp4", "webm", "jpg")}
        if wf.get("still"):
            r.local |= {f"media/shot-{wf['still']}{s}" for s in ("-800.webp", ".webp", ".jpg")}
    for css in SITE.glob("*.css"):
        r.local |= {m for m in re.findall(r'url\("?([^")]+)"?\)', css.read_text(encoding="utf-8")) if not m.startswith("data:")}
    missing = sorted(p for p in r.local if not (SITE / p).exists())
    for p in sorted(r.local):
        print(("MISSING " if p in missing else "ok      ") + p)
    print("external:", *sorted(r.external), sep="\n  ")
    size = lambda p: (SITE / p).stat().st_size if (SITE / p).exists() else 0   # noqa: E731
    first = ["index.html", "styles.css", "app.js", "fonts/InterVariable-latin.woff2", "media/hotbox.jpg",
             "media/favicon-32.png"]
    fv = sum(size(p) for p in first)
    total = sum(size(p) for p in set(r.local) | {"index.html"})
    print(f"first view: {fv / 1024:.0f} KiB ({', '.join(first)}); the hotbox clip streams after it ({size('media/hotbox.webm') / 1024:.0f} KiB webm)")
    print(f"everything the page can load: {total / 1024 / 1024:.1f} MiB over {len(r.local) + 1} files (videos only on view / play)")
    print("PASS" if not missing else f"FAIL: {len(missing)} missing")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
