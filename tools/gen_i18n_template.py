"""Write the English translation template: every kit string, grouped by menu / window / file.

    python tools/gen_i18n_template.py           # writes src/allset/i18n/template_en.json
    python tools/gen_i18n_template.py --check   # exit 1 when the shipped template is out of date

Runs without Blender. The strings come from ``tools/i18n_strings.py`` (``sections``). In the template every value
is the English text; a translator copies the file to ``<language code>.json`` (for example ``de_DE.json``) in the
kit's translations folder and replaces the values. The kit reads such files when it starts (see
``src/allset/i18n/user_files.py``).
"""

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "allset" / "i18n" / "template_en.json"

ABOUT = [
    "Maya Workflow Kit translation template (English).",
    "Copy this file to <language code>.json in the kit's translations folder (Preferences > Add-ons > Maya Workflow Kit"
    " > Translations > Open Translations Folder), for example de_DE.json, fr_FR.json or ko_KR.json: the code is"
    " Blender's language code (Preferences > Interface > Language).",
    "Replace the values with your translation. A value that is empty or still the English text is skipped, so you"
    " can translate a part and leave the rest.",
    "The same English text can be listed in several sections (it is shown in several places); translating it once"
    " is enough, it is used everywhere it is shown.",
    "Keep '...', leading / trailing spaces and placeholders as they are. Restart Blender or press Reload Translations"
    " to see the result; the kit follows Blender's interface language and its Translate switches.",
]


def _strings_tool():
    spec = importlib.util.spec_from_file_location("i18n_strings", ROOT / "tools" / "i18n_strings.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def template():
    """The template as a dict (``about`` lines, ``sections`` = {section: {English: English}})."""
    sections = _strings_tool().sections()
    return {"about": ABOUT,
            "sections": {name: {s: s for s in strings} for name, strings in sections.items()}}


def text():
    return json.dumps(template(), ensure_ascii=False, indent=1) + "\n"


def main(argv):
    new = text()
    if "--check" in argv:
        old = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if old != new:
            print(f"{OUT.relative_to(ROOT)} is out of date: run python tools/gen_i18n_template.py")
            return 1
        return 0
    OUT.write_text(new, encoding="utf-8", newline="\n")
    data = template()
    print(f"wrote {OUT.relative_to(ROOT)}: {len(data['sections'])} sections, "
          f"{sum(len(v) for v in data['sections'].values())} entries")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
