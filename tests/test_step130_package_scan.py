"""The store review points (GitHub #40) stay fixed — a static scan of the extension.

The extensions.blender.org moderator asked for: no ``exec`` / ``eval``; no manual ``sys.path`` / ``sys.modules``
changes (and no import hooks); nothing related to themes; nothing that outlives the add-on (no ``user_disabling``,
no template copied outside the extension, no preference / active-keyconfig changes); tags = User Interface only.

Scanned: every ``.py`` file of ``src/allset`` and of the built extension zip (``dist/maya-workflow-kit-<ver>.zip``,
so the scan also covers what is uploaded). Python files are tokenized, so comments and docstrings that *mention*
a call never count — only code does. ``save_userpref`` is allowed only as the operator id string of Maya's
explicit File > Save Preferences menu item (``ui/menu_map.py``), never as a call.
"""

import io
import os
import tokenize
import tomllib
import zipfile

AUTO_ENABLE = False
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "src", "allset")

# Blender preference sections (bpy.types.Preferences): a write below one of them is a persistent preference change.
PREF_SECTIONS = {"view", "inputs", "edit", "system", "filepaths", "keymap", "themes", "apps", "extensions",
                 "experimental", "ui_styles", "studio_lights", "autoexec_paths", "addons"}
CALLS = {"exec", "eval", "execfile", "__import__"}
# Names whose mere presence in code is a review violation.
BANNED_NAMES = {
    "__builtins__": "builtins access (import hook)",
    "rna_xml": "theme XML import / export",
    "_rna_xml": "theme XML import / export",
    "user_disabling": "user_disabling (moderator: remove)",
    "remove_on_disable": "app template removal on disable (no template may be written)",
    "keyconfig_activate": "changes the active keyconfig",
    "save_userpref": "saves the user's preferences",
    "reset_default_theme": "theme change",
    "interface_theme_preset_add": "theme change",
}
ALLOWED_STRINGS = {("ui/menu_map.py", "wm.save_userpref")}   # Maya's File > Save Preferences: the user's own command


def _sources():
    """(label, relative path, text) of every Python file in the source package and the built zip."""
    out = []
    for base, dirs, files in os.walk(PKG):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in files:
            if name.endswith(".py"):
                path = os.path.join(base, name)
                rel = os.path.relpath(path, PKG).replace(os.sep, "/")
                out.append(("src", rel, open(path, encoding="utf-8").read()))
    with zipfile.ZipFile(_zip_path()) as zf:
        for rel in zf.namelist():
            if rel.endswith(".py"):
                out.append(("zip", rel, zf.read(rel).decode("utf-8")))
    return out


def _zip_path():
    with open(os.path.join(PKG, "blender_manifest.toml"), "rb") as fh:
        version = tomllib.load(fh)["version"]
    path = os.path.join(ROOT, "dist", f"maya-workflow-kit-{version}.zip")
    assert os.path.exists(path), f"{path} missing: run tests/run.py (it builds) or tools/build.py"
    return path


def _logical_lines(text):
    """Code tokens (no comments / NL / INDENT) grouped by logical line: [(line number, [tokens])]."""
    skip = {tokenize.COMMENT, tokenize.NL, tokenize.INDENT, tokenize.DEDENT, tokenize.ENCODING,
            tokenize.ENDMARKER}
    lines, cur = [], []
    for tok in tokenize.generate_tokens(io.StringIO(text).readline):
        if tok.type == tokenize.NEWLINE:
            if cur:
                lines.append((cur[0].start[0], cur))
            cur = []
        elif tok.type not in skip:
            cur.append(tok)
    if cur:
        lines.append((cur[0].start[0], cur))
    return lines


def _assign_targets(toks):
    """Token lists of every assignment target of a logical line (``a = b = c`` -> [a, b])."""
    depth, cuts = 0, []
    for i, t in enumerate(toks):
        if t.type == tokenize.OP:
            if t.string in "([{":
                depth += 1
            elif t.string in ")]}":
                depth -= 1
            elif t.string == "=" and depth == 0:
                cuts.append(i)
    if not cuts or (toks[0].type == tokenize.NAME and toks[0].string in {"def", "class", "lambda"}):
        return []
    targets, start = [], 0
    for c in cuts:
        targets.append(toks[start:c])
        start = c + 1
    return targets


def _attr_chain(toks, i):
    """Names of the dotted chain starting at token i: ``a.b[0].c`` -> ['a', 'b', 'c']."""
    names, depth = [], 0
    while i < len(toks):
        t = toks[i]
        if depth:
            depth += {"[": 1, "]": -1}.get(t.string, 0) if t.type == tokenize.OP else 0
        elif t.type == tokenize.NAME:
            names.append(t.string)
        elif t.type == tokenize.OP and t.string == "[":
            depth = 1
        elif not (t.type == tokenize.OP and t.string == "."):
            break
        i += 1
    return names


def _pref_aliases(lines):
    """Names bound to ``<...>.preferences`` (``prefs = context.preferences``), add-on prefs excluded."""
    aliases = set()
    for _n, toks in lines:
        for target in _assign_targets(toks):
            if len(target) == 1 and target[0].type == tokenize.NAME:
                rhs = [t.string for t in toks[len(target) + 1:]]
                if rhs and rhs[-1] == "preferences" and "addons" not in rhs:
                    aliases.add(target[0].string)
    return aliases


def _violations(label, rel, text):
    hits = []
    lines = _logical_lines(text)
    aliases = _pref_aliases(lines)

    def hit(n, why):
        hits.append(f"{label}:{rel}:{n}: {why}")

    for n, toks in lines:
        strs = [t.string for t in toks]
        for i, t in enumerate(toks):
            prev = strs[i - 1] if i else ""
            nxt = strs[i + 1] if i + 1 < len(strs) else ""
            if t.type == tokenize.STRING and "save_userpref" in t.string:
                if not any(rel == f and s in t.string for f, s in ALLOWED_STRINGS):
                    hit(n, "save_userpref outside Maya's File > Save Preferences item")
            if t.type != tokenize.NAME:
                continue
            s = t.string
            if s in CALLS and nxt == "(" and (prev != "." or s == "execfile"):
                hit(n, f"{s}() call")
            elif s == "execfile":
                hit(n, "execfile")
            if s == "compile" and nxt == "(" and prev != ".":
                args = [x.string.strip("'\"") for x in toks[i:] if x.type == tokenize.STRING]
                if {"exec", "eval", "single"} & set(args):
                    hit(n, "compile(..., 'exec' / 'eval')")
            if s in BANNED_NAMES:
                hit(n, BANNED_NAMES[s])
            if s == "sys" and nxt == "." and i + 2 < len(strs) and strs[i + 2] in {"path", "modules", "meta_path",
                                                                                 "path_hooks"}:
                hit(n, f"sys.{strs[i + 2]}")
            if s == "builtins" and prev in {"import", "from"}:
                hit(n, "import builtins")
            if s == "importlib" and (nxt == "." and i + 2 < len(strs) and strs[i + 2] in {"util", "machinery"}
                                     or prev == "from" and "util" in strs[i:] or prev == "from" and "machinery" in strs[i:]):
                hit(n, "importlib.util / machinery (import hooks)")
        for target in _assign_targets(toks):
            if not target or target[0].type != tokenize.NAME:
                continue
            chain = _attr_chain(target, 0)
            text_t = ".".join(chain)
            if "themes" in chain:
                hit(n, f"theme write: {text_t} =")
            if "keyconfigs" in chain and chain[-1] == "active":
                hit(n, f"active keyconfig write: {text_t} =")
            for k, name in enumerate(chain[:-2]):
                if (name == "preferences" or k == 0 and name in aliases) and chain[k + 1] in PREF_SECTIONS:
                    hit(n, f"preference write: {text_t} =")
                    break
        if strs and strs[0] == "setattr":
            args = strs[2:]
            for k, name in enumerate(args[:-2]):
                if (name == "preferences" or name in aliases) and args[k + 1] == "." and args[k + 2] in PREF_SECTIONS:
                    hit(n, "preference write through setattr")
                    break
    return hits


def test_no_exec_eval_hooks_or_persistent_writes_in_code():
    hits = []
    for label, rel, text in _sources():
        hits += _violations(label, rel, text)
    assert not hits, "\n".join(hits)


def test_no_theme_files_or_package():
    found = []
    for base, dirs, files in os.walk(PKG):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        rel_base = os.path.relpath(base, PKG).replace(os.sep, "/")
        if rel_base.split("/")[-1] == "theme":
            found.append(f"src:{rel_base}/ (theme package)")
        found += [f"src:{rel_base}/{f}" for f in files if f.endswith(".xml")]
    with zipfile.ZipFile(_zip_path()) as zf:
        for rel in zf.namelist():
            if rel.endswith(".xml") or rel.startswith("theme/") or "/theme/" in rel:
                found.append(f"zip:{rel}")
    assert not found, found
    assert not os.path.exists(os.path.join(PKG, "prefs_preset.py")), "preference presets were dropped"


def test_no_writes_outside_the_extension():
    """No app template copied into the user's scripts folder, no startup / userpref files written."""
    hits = []
    for label, rel, text in _sources():
        for n, toks in _logical_lines(text):
            for t in toks:
                if t.type == tokenize.STRING and "bl_app_templates" in t.string:
                    hits.append(f"{label}:{rel}:{n}: {t.string}")
                if t.type == tokenize.NAME and t.string == "save_homefile":
                    hits.append(f"{label}:{rel}:{n}: save_homefile")
                if t.type == tokenize.NAME and t.string == "user_resource":
                    hits.append(f"{label}:{rel}:{n}: user_resource (user config / scripts folder)")
    assert not hits, "\n".join(hits)


def test_manifest_tags_user_interface_only():
    with open(os.path.join(PKG, "blender_manifest.toml"), "rb") as fh:
        m = tomllib.load(fh)
    assert m["tags"] == ["User Interface"], m["tags"]
    with zipfile.ZipFile(_zip_path()) as zf:
        assert tomllib.loads(zf.read("blender_manifest.toml").decode("utf-8"))["tags"] == ["User Interface"]


def test_scanner_catches_known_violations():
    """The scanner itself: each pattern is found in a sample and nothing in harmless look-alikes."""
    bad = {
        "exec(src, ns)": "exec() call",
        "x = eval('1')": "eval() call",
        "code = compile(src, '<cl>', 'exec')": "compile",
        "m = __import__('os')": "__import__() call",
        "import builtins": "import builtins",
        "sys.modules['maya'] = m": "sys.modules",
        "sys.path.insert(0, p)": "sys.path",
        "import importlib.util": "importlib.util",
        "bpy.utils.execfile(p)": "execfile",
        "context.preferences.inputs.use_zoom_to_mouse = True": "preference write",
        "prefs = bpy.context.preferences\nprefs.edit.undo_steps = 256": "preference write",
        "bpy.context.preferences.themes[0].view_3d.space.gradients.high_gradient = c": "theme write",
        "wm.keyconfigs.active = kc": "active keyconfig write",
        "bpy.ops.wm.save_userpref()": "saves the user's preferences",
        "bpy.ops.preferences.keyconfig_activate(filepath=p)": "active keyconfig",
        "from rna_xml import xml_file_run": "theme XML",
        "def user_disabling():\n    pass": "user_disabling",
    }
    for src, why in bad.items():
        found = _violations("t", "x.py", src + "\n")
        assert any(why in h for h in found), (src, found)
    ok = ("# exec(src) in a comment\n"
          "'''eval(x) in a docstring'''\n"
          "bpy.ops.text.run_script()\n"
          "op('EXEC_DEFAULT')\n"
          "prefs = context.preferences.addons[__package__].preferences\n"
          "prefs.option_settings = '{}'\n"
          "c = context.preferences.themes[0].view_3d.space.back\n"
          "kc = wm.keyconfigs.active\n"
          "col = re.compile(r'x')\n")
    assert not _violations("t", "x.py", ok), _violations("t", "x.py", ok)
    assert not _violations("t", "ui/menu_map.py", "MAP = {'File/Save Preferences': 'wm.save_userpref'}\n")
    assert _violations("t", "ui/other.py", "MAP = {'x': 'wm.save_userpref'}\n")


def test_no_menu_item_targets_blender_preferences():
    """#43: a Maya menu item may open Blender's Preferences, never write them ("preferences.<section>..." data paths)."""
    import re
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "allset")
    bad = []
    pat = re.compile(r"""["']preferences\.(edit|view|inputs|system|filepaths|keymap|experimental|apps|extensions)\.""")
    for d, _s, fs in os.walk(root):
        for f in fs:
            # keymap/ic_*.py = Blender's own Industry Compatible data (its NDOF sensitivity keys are Blender's)
            if f.endswith(".py") and not (os.path.basename(d) == "keymap" and f.startswith("ic_")):
                path = os.path.join(d, f)
                for n, line in enumerate(open(path, encoding="utf-8"), 1):
                    if pat.search(line):
                        bad.append(f"{os.path.relpath(path, root)}:{n}: {line.strip()}")
    assert not bad, chr(10).join(bad)
