"""User translations (#293): ``<language code>.json`` files in the kit's translations folder add a language (or
correct a built-in one) over the kit's tables; empty values and values equal to the English text are skipped; a
broken file is listed, not raised; the shipped English template lists every kit string by section and is up to
date; the preferences box operators work and disabling takes the user's translations back.

The language is switched in this process only (sandbox factory preferences, never saved)."""

import importlib.util
import json
import os
from importlib import import_module

import bpy

import kit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
i18n = import_module(kit.MODULE + ".i18n")
user_files = import_module(kit.MODULE + ".i18n.user_files")
SAMPLE = "Channel Box / Layer Editor"        # a kit string Blender has no translation of
OTHER = "Smooth Mesh Preview to Polygons"


def _tool(name):
    spec = importlib.util.spec_from_file_location("tool_" + name, os.path.join(ROOT, "tools", name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _sandboxed(path):
    path = os.path.normcase(os.path.abspath(path))
    assert os.sep + "tmp" + os.sep in path, f"not a sandbox folder: {path}"


class _Language:
    def __init__(self, locale):
        self.locale = locale

    def __enter__(self):
        _sandboxed(bpy.utils.user_resource('CONFIG'))
        view = bpy.context.preferences.view
        self.saved = (view.language, view.use_translate_interface, view.use_translate_tooltips)
        view.language = self.locale
        view.use_translate_interface = view.use_translate_tooltips = True

    def __exit__(self, *exc):
        view = bpy.context.preferences.view
        view.language, view.use_translate_interface, view.use_translate_tooltips = self.saved


def _usable(locale):
    items = bpy.context.preferences.view.bl_rna.properties["language"].enum_items
    return locale in {it.identifier for it in items}


class _Files:
    """Translation files written into the (sandbox) translations folder for the block, removed afterwards."""

    def __init__(self, files):
        self.files = files

    def __enter__(self):
        self.folder = user_files.folder(create=True)
        _sandboxed(self.folder)
        for name, content in self.files.items():
            with open(os.path.join(self.folder, name), "w", encoding="utf-8") as fh:
                fh.write(content if isinstance(content, str) else json.dumps(content))
        i18n.reload()
        return self

    def __exit__(self, *exc):
        for name in list(self.files) + [user_files.TEMPLATE]:
            path = os.path.join(self.folder, name)
            if os.path.exists(path):
                os.remove(path)
        i18n.reload()


def test_entries_rules():
    data = {"sections": {"A": {"Open": "Öffnen", "Close": "", "Keep": "Keep", "": "x", "Num": 3},
                         "B": {"Open": "Aufmachen", "Save": "Speichern"}}}
    assert user_files.entries(data) == {"Open": "Öffnen", "Save": "Speichern"}
    assert user_files.entries({"Open": "Öffnen", "about": ["x"]}) == {"Open": "Öffnen"}     # flat file
    assert user_files.entries(["not", "a", "dict"]) == {}


def test_template_is_up_to_date_and_complete():
    gen = _tool("gen_i18n_template")
    with open(gen.OUT, encoding="utf-8") as fh:
        shipped = fh.read()
    assert shipped == gen.text(), "run python tools/gen_i18n_template.py"
    data = json.loads(shipped)
    sections = data["sections"]
    every = set().union(*(set(v) for v in sections.values()))
    assert every == _tool("i18n_strings").all_strings()
    for name in ("Main menu/File", "Main menu/Edit Mesh", "Notices", "Status Line", "Panel toolbar"):
        assert name in sections, name
    assert any(n.startswith("Marking menus/") for n in sections) and any(n.startswith("Shelves/") for n in sections)
    assert any(n.startswith("Editor menus/Graph Editor/") for n in sections)
    assert any(n.startswith("Tooltips/") for n in sections) and any(n.startswith("Labels/") for n in sections)
    assert all(en == tr for block in sections.values() for en, tr in block.items())     # English template
    assert user_files.entries(data) == {}           # the untouched template adds nothing


def test_user_file_adds_a_language():
    locale = "de_DE"
    if not _usable(locale):
        print(f"skip {locale}: not in this Blender build")
        return
    content = {"sections": {"Main menu/Windows": {SAMPLE: "Kanalbox / Ebenen-Editor", OTHER: ""}}}
    with _Files({"de_DE.json": content}):
        assert ("de_DE.json", 1, "") in user_files.LOADED, user_files.LOADED
        with _Language(locale):
            assert bpy.app.translations.pgettext_iface(SAMPLE) == "Kanalbox / Ebenen-Editor"
            assert bpy.app.translations.pgettext_iface(SAMPLE, "Operator") == "Kanalbox / Ebenen-Editor"
            assert i18n.iface(OTHER) == OTHER           # empty value: English stays
        kit.disable()
        try:
            with _Language(locale):
                assert bpy.app.translations.pgettext_iface(SAMPLE) == SAMPLE
        finally:
            kit.enable()
        with _Language(locale):        # read again on register
            assert bpy.app.translations.pgettext_iface(SAMPLE) == "Kanalbox / Ebenen-Editor"
    with _Language(locale):            # file removed + reloaded
        assert bpy.app.translations.pgettext_iface(SAMPLE) == SAMPLE


def test_user_file_corrects_a_built_in_language():
    locale = "ja_JP"
    if not _usable(locale):
        return
    built_in = i18n.LANGUAGES[locale][OTHER]
    with _Files({"ja_JP.json": {SAMPLE: "チャンネルボックス (修正)"}}):
        with _Language(locale):
            assert bpy.app.translations.pgettext_iface(SAMPLE) == "チャンネルボックス (修正)"
            assert bpy.app.translations.pgettext_iface(OTHER) == built_in       # the rest stays built in
    with _Language(locale):
        assert bpy.app.translations.pgettext_iface(SAMPLE) == i18n.LANGUAGES[locale][SAMPLE]


def test_broken_and_misnamed_files_are_listed():
    with _Files({"fr_FR.json": "{ not json", "klingon.json": {SAMPLE: "x"}}):
        loaded = {name: (count, problem) for name, count, problem in user_files.LOADED}
        assert loaded["fr_FR.json"] == (0, user_files.NOT_READ), loaded
        assert loaded["klingon.json"] == (1, user_files.NOT_LANGUAGE), loaded


def test_template_operator_writes_the_template():
    folder = user_files.folder(create=True)
    _sandboxed(folder)
    target = os.path.join(folder, user_files.TEMPLATE)
    try:
        assert bpy.ops.allset.translations_template() == {'FINISHED'}
        with open(target, encoding="utf-8") as fh, open(user_files.template_path(), encoding="utf-8") as src:
            assert fh.read() == src.read()
        assert bpy.ops.allset.translations_reload() == {'FINISHED'}
        assert all(name != user_files.TEMPLATE for name, _c, _p in user_files.LOADED)     # never read as a language
    finally:
        if os.path.exists(target):
            os.remove(target)


def test_operators_are_core():
    """The box is in the preferences with Maya mode off too."""
    kit.disable()
    try:
        kit.enable(maya=False)
        for op in ("translations_folder", "translations_template", "translations_reload"):
            assert hasattr(bpy.types, "ALLSET_OT_" + op), op
    finally:
        kit.disable()
        kit.enable()


class _Layout:
    """Records what a draw function puts in a layout (``row`` / ``box`` / ``column`` nest)."""

    def __init__(self, log):
        self.log = log

    def _child(self, *_a, **_k):
        return _Layout(self.log)

    row = box = column = _child

    def label(self, text="", **kw):
        self.log.append(("label", text))

    def operator(self, idname, **kw):
        self.log.append(("operator", idname))


def test_preferences_box_lists_the_files():
    translations = import_module(kit.MODULE + ".translations")
    with _Files({"de_DE.json": {SAMPLE: "Kanalbox"}, "fr_FR.json": "{ not json"}):
        log = []
        translations.draw(_Layout(log))
    ops = [v for k, v in log if k == "operator"]
    assert ops == ["allset.translations_folder", "allset.translations_template", "allset.translations_reload"], ops
    labels = [v for k, v in log if k == "label"]
    assert "de_DE.json: 1 translated texts" in labels, labels
    assert any(t.startswith("fr_FR.json: could not be read") for t in labels), labels
