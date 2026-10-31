"""List every translatable string of the kit and report translation coverage per language.

    python tools/i18n_strings.py                 # coverage table per language and category
    python tools/i18n_strings.py --missing ja_JP [category]   # untranslated strings of a language
    python tools/i18n_strings.py --stale         # dictionary keys that are no kit string any more
    python tools/i18n_strings.py --dump [category]            # every string of a category, one per line

Runs without Blender. Categories:

- ``menus``         main Maya menu bar: menu names, items, section titles, menu set names (``ui/menu_data.py``)
- ``editor_menus``  Graph Editor / Dope Sheet / UV Editor / Hypershade ... menu bars (``ui/editor_menu_data.py``)
- ``panel_menus``   viewport panel menus and panel toolbar (``ui/panel_menu_data.py``)
- ``marking``       marking menus and the hotbox (``marking/menus.py``)
- ``shelf``         shelf tab names and button labels (``ui/shelf_data.py``)
- ``notices``       "not in Blender" notices shown in tooltips (``ui/notices.py``)
- ``ui``            literal labels in the code: ``text=``, ``bl_label``, ``bl_category``, property ``name=`` /
                    ``description=`` and enum item names
- ``tooltips``      docstrings of operator / panel / menu classes (and subclasses that set ``bl_*`` values):
                    Blender shows a class docstring as the tooltip when the class sets no ``bl_description``;
                    classes built with ``type()`` at run time (composed texts) are not listed

The translations live in ``src/allset/i18n/<locale>.py`` (``STRINGS = {English: translation}``).
"""

import ast
import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "src" / "allset"
LOCALES = ("ja_JP", "zh_HANS")

# Data modules walked by their own rules (not scanned for literals).
_DATA = {"ui/menu_data.py", "ui/editor_menu_data.py", "ui/shelf_data.py", "ui/menu_hotkeys.py", "ui/menu_icon_data.py",
         "ui/panel_menu_data.py", "marking/menus.py", "ui/notices.py", "keymap/hotkey_data.py"}
_LETTER = re.compile(r"[A-Za-z]")
_IDENT = re.compile(r"^[A-Za-z0-9_.]+$")


def _load(rel):
    """Import a bpy-free module of the package by its file path."""
    path = PKG / rel
    spec = importlib.util.spec_from_file_location("i18n_src_" + rel.replace("/", "_")[:-3], path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ok(text):
    """A string a user reads: has a letter, is not an identifier / operator id / data path."""
    if not isinstance(text, str):
        return False
    text = text.strip()
    if len(text) < 2 or not _LETTER.search(text):
        return False
    if "_" in text and _IDENT.match(text):
        return False
    if re.match(r"^[a-z]+\.[a-z_]+$", text):          # operator ids
        return False
    if "{" in text and "}" in text:                    # format templates
        return False
    return True


def _walk_menu(items, out):
    for it in items:
        if it[0] == "-":
            if len(it) > 1 and it[1]:
                out.add(it[1])
            continue
        out.add(it[0])
        if len(it) > 1 and isinstance(it[1], list):
            _walk_menu(it[1], out)


def menus():
    md = _load("ui/menu_data.py")
    out = set()
    for _name, (label, _set, _src, items) in md.MENUS.items():
        out.add(label)
        _walk_menu(items, out)
    for _sid, label, _menus in md.MENU_SETS:
        out.add(label)
    return out


def editor_menus():
    ed = _load("ui/editor_menu_data.py")
    out = set()
    for editor, bars in ed.EDITORS.items():
        out.add(editor)
        for title, items in bars:
            out.add(title)
            _walk_menu(items, out)
    return out


def panel_menus():
    pm = _load("ui/panel_menu_data.py")
    out = set()
    for _idname, (prefix, rows) in pm.MENUS.items():
        out.update(prefix.split("/"))
        for row in rows:
            if row[0] == "sep":
                if len(row) > 1 and row[1]:
                    out.add(row[1])
                continue
            out.add(row[1] if row[0] in ("grey", "run", "menu") else row[-1])
    for title, _idname in pm.BAR:
        out.add(title)
    for group in pm.TOOLBAR:
        for _glyph, _kind, _data, label in group:
            out.add(label)
    for path in pm.STATUS_LINE:
        out.add(path.split("/", 1)[1])
    for label, _ui in pm.PANEL_TYPES:
        out.add(label)
    return {s for s in out if _ok(s)}


def _walk_marking(sub, out):
    for label, action in list(sub.radial.values()) + [e for e in sub.items if isinstance(e, tuple)]:
        out.add(label)
        if hasattr(action, "radial"):
            _walk_marking(action, out)


def marking():
    mm = _load("marking/menus.py")
    out = set()
    for menu in mm.MENUS.values():
        out.add(menu.label)
        _walk_marking(menu, out)
    return {s for s in out if _ok(s)}


def shelf():
    sd = _load("ui/shelf_data.py")
    out = set()
    for _file, tab, buttons in sd.SHELVES:
        out.add(tab)
        out.update(label for label, _cmd in buttons)
    return {s for s in out if _ok(s)}


def _is_text(e):
    return isinstance(e, ast.Constant) and isinstance(e.value, str)


def _notice_values(node, out):
    """String literals of the notice tables' (substitute, line) tuples; a line may be a named constant
    (collected from its own assignment)."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Tuple) and len(sub.elts) == 2 and _is_text(sub.elts[0]) and (
                _is_text(sub.elts[1]) or isinstance(sub.elts[1], ast.Name)):
            out.update(e.value for e in sub.elts if _is_text(e))


def notices():
    tree = ast.parse((PKG / "ui" / "notices.py").read_text(encoding="utf-8"))
    out = set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id.isupper() or
                                                isinstance(t, ast.Name) and t.id.startswith("_")
                                                for t in node.targets):
            if _is_text(node.value):
                if node.value.value.endswith("."):
                    out.add(node.value.value)      # a shared notice line (NAME = "...")
            else:
                _notice_values(node.value, out)
    return {s for s in out if _ok(s) and " " in s}


def _call_name(node):
    f = node.func
    return f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else ""


def _literals(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _call_name(node)
            f = node.func
            if (isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "i18n"
                    and name in ("iface", "tip", "mark") and node.args and isinstance(node.args[0], ast.Constant)):
                out.add(node.args[0].value)
            for kw in node.keywords:
                v = kw.value
                if not (isinstance(v, ast.Constant) and isinstance(v.value, str)):
                    if kw.arg == "items" and name.endswith("Property") and isinstance(v, (ast.List, ast.Tuple)):
                        for item in v.elts:
                            if isinstance(item, ast.Tuple) and len(item.elts) >= 2 and isinstance(
                                    item.elts[1], ast.Constant):
                                out.add(item.elts[1].value)
                    continue
                if kw.arg == "text" or kw.arg in ("name", "description") and name.endswith("Property"):
                    out.add(v.value)
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in ("bl_label", "bl_category", "bl_description"):
                    out.add(node.value.value)
    return out


def ui():
    out = set()
    for path in sorted(PKG.rglob("*.py")):
        rel = path.relative_to(PKG).as_posix()
        if rel in _DATA or rel.startswith("i18n/") or rel.startswith("keymap/ic_"):
            continue
        out |= _literals(path)
    return {s for s in out if _ok(s)}


# Blender classes whose docstring becomes the description (tooltip)
_DOC_BASES = ("Operator", "Macro", "Panel", "Menu", "Header", "UIList", "Gizmo", "GizmoGroup", "PropertyGroup",
              "WorkSpaceTool")


def _base_name(node):
    return node.attr if isinstance(node, ast.Attribute) else node.id if isinstance(node, ast.Name) else ""


def _docstrings(path):
    """Docstrings of the Blender classes in ``path``, as Python stores them (``inspect.cleandoc``), unless the
    class sets its own ``bl_description``."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        blender_class = any(isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id.startswith("bl_")
                                                               for t in n.targets) for n in node.body)
        if not (blender_class or any(_base_name(b) in _DOC_BASES for b in node.bases)):
            continue
        if any(isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "bl_description"
                                                 for t in n.targets) for n in node.body):
            continue
        doc = ast.get_docstring(node, clean=True)
        if doc:
            out.add(doc)
    return out


def tooltips():
    out = set()
    for path in sorted(PKG.rglob("*.py")):
        rel = path.relative_to(PKG).as_posix()
        if rel.startswith("i18n/") or rel.startswith("keymap/ic_"):
            continue
        out |= _docstrings(path)
    return {s for s in out if _ok(s)}


CATEGORIES = {"menus": menus, "editor_menus": editor_menus, "panel_menus": panel_menus, "marking": marking,
              "shelf": shelf, "notices": notices, "ui": ui,
              "tooltips": tooltips}


def collect():
    """{category: set of English strings}."""
    return {name: fn() for name, fn in CATEGORIES.items()}


def all_strings(cats=None):
    cats = cats or collect()
    out = set()
    for strings in cats.values():
        out |= strings
    return out


def translations(locale):
    return _load(f"i18n/{locale}.py").STRINGS


def coverage(cats=None):
    """{locale: {category: (translated, total)}}."""
    cats = cats or collect()
    out = {}
    for locale in LOCALES:
        table = translations(locale)
        out[locale] = {name: (sum(1 for s in strings if s in table), len(strings)) for name, strings in cats.items()}
    return out


def stale(cats=None):
    """{locale: sorted keys that are no kit string}."""
    known = all_strings(cats)
    return {locale: sorted(k for k in translations(locale) if k not in known) for locale in LOCALES}


def main(argv):
    cats = collect()
    if "--dump" in argv:
        names = argv[argv.index("--dump") + 1:] or list(cats)
        for name in names:
            for s in sorted(cats[name]):
                print(s)
        return 0
    if "--missing" in argv:
        i = argv.index("--missing")
        locale = argv[i + 1]
        names = argv[i + 2:] or list(cats)
        table = translations(locale)
        for name in names:
            for s in sorted(cats[name]):
                if s not in table:
                    print(f"{name}\t{s}")
        return 0
    if "--stale" in argv:
        bad = stale(cats)
        for locale, keys in bad.items():
            for k in keys:
                print(f"{locale}\t{k}")
        return 1 if any(bad.values()) else 0
    cov = coverage(cats)
    print(f"{'category':14}" + "".join(f"{loc:>22}" for loc in LOCALES))
    totals = {loc: [0, 0] for loc in LOCALES}
    for name in cats:
        row = f"{name:14}"
        for loc in LOCALES:
            done, total = cov[loc][name]
            totals[loc][0] += done
            totals[loc][1] += total
            row += f"{done:>9} / {total:<5} {100.0 * done / max(total, 1):5.1f} %"
        print(row)
    print(f"{'all':14}" + "".join(f"{d:>9} / {t:<5} {100.0 * d / max(t, 1):5.1f} %" for d, t in totals.values()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
