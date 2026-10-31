"""Translations (#197): the kit's labels follow Blender's interface language (ja_JP, zh_HANS) and its Translate
toggles; every dictionary key is a real kit string and the main Maya menus are fully covered; the menu texts the
kit composes and sizes itself (hotkey column, option boxes) are built from the translated label; disabling the
kit takes the translations back.

The language is switched in this process only (sandbox factory preferences, never saved)."""

import importlib.util
import os
from importlib import import_module

import bpy

import kit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
i18n = import_module(kit.MODULE + ".i18n")
ms = import_module(kit.MODULE + ".ui.menu_sets")
oc = import_module(kit.MODULE + ".ui.option_click")
notices = import_module(kit.MODULE + ".ui.notices")
chrome = import_module(kit.MODULE + ".ui.chrome")
LOCALES = ("ja_JP", "zh_HANS")
SAMPLES = ("Channel Box / Layer Editor", "Save Scene As...", "Smooth Mesh Preview to Polygons")


def _tool():
    spec = importlib.util.spec_from_file_location("tool_i18n_strings", os.path.join(ROOT, "tools", "i18n_strings.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _sandboxed():
    config = os.path.normcase(os.path.abspath(bpy.utils.user_resource('CONFIG')))
    assert os.sep + "tmp" + os.sep in config, f"not a sandbox config: {config}"


class _Language:
    """Interface language ``locale`` for the block (``None`` = keep), with Blender's Translate toggles."""

    def __init__(self, locale, interface=True, tooltips=True):
        self.values = (locale, interface, tooltips)

    def __enter__(self):
        _sandboxed()
        view = bpy.context.preferences.view
        self.saved = (view.language, view.use_translate_interface, view.use_translate_tooltips)
        locale, interface, tooltips = self.values
        if locale is not None:
            view.language = locale
        view.use_translate_interface = interface
        view.use_translate_tooltips = tooltips
        return self

    def __exit__(self, *exc):
        view = bpy.context.preferences.view
        view.language, view.use_translate_interface, view.use_translate_tooltips = self.saved


def _usable(locale):
    """Blender lists the language (a build without translations has only English)."""
    items = bpy.context.preferences.view.bl_rna.properties["language"].enum_items
    return locale in {it.identifier for it in items}


def test_every_key_is_a_kit_string():
    tool = _tool()
    cats = tool.collect()
    stale = tool.stale(cats)
    assert not any(stale.values()), {loc: keys[:10] for loc, keys in stale.items()}
    for locale, strings in i18n.LANGUAGES.items():
        for en, tr in strings.items():
            assert isinstance(tr, str) and tr.strip(), (locale, en)
            assert not en.endswith("...") or tr.endswith("..."), (locale, en, tr)


def test_main_menus_fully_covered():
    tool = _tool()
    cov = tool.coverage()
    for locale in LOCALES:
        for cat in ("menus", "editor_menus", "panel_menus", "marking", "shelf", "notices"):
            done, total = cov[locale][cat]
            assert total > 0 and done == total, (locale, cat, done, total)


def test_labels_follow_the_interface_language():
    for locale in LOCALES:
        if not _usable(locale):
            print(f"skip {locale}: not in this Blender build")
            continue
        table = i18n.LANGUAGES[locale]
        with _Language(locale):
            for s in SAMPLES:
                assert bpy.app.translations.pgettext_iface(s) == table[s], (locale, s)
                assert i18n.iface(s) == table[s]
            # operator buttons with their own text use Blender's operator context
            assert bpy.app.translations.pgettext_iface(SAMPLES[0], "Operator") == table[SAMPLES[0]]
            assert i18n.core("  Save Scene As... ▸") == "  " + table["Save Scene As..."] + " ▸"
            iface = bpy.app.translations.pgettext_iface
            assert i18n.path("File/Save Scene As...") == iface("File") + "/" + table["Save Scene As..."]
        with _Language(locale, interface=False):
            assert i18n.iface(SAMPLES[0]) == SAMPLES[0]      # Translate: Interface off = English labels
        with _Language(locale, tooltips=False):
            assert i18n.tip(SAMPLES[0]) == SAMPLES[0]        # Translate: Tooltips off = English tooltips


def test_menu_rows_are_translated_before_alignment():
    locale = "ja_JP"
    if not _usable(locale):
        return
    table = i18n.LANGUAGES[locale]
    iface = bpy.app.translations.pgettext_iface      # Blender's own translation of a word wins over the kit's
    with _Language(locale):
        out, texts = oc.rows("Edit Mesh")
        bevel = texts["Edit Mesh/Bevel"]
        assert iface("Bevel") != "Bevel" and bevel.startswith(iface("Bevel")) and "Ctrl+B" in bevel and bevel.endswith("❒"), bevel
        file_rows, file_texts = oc.rows("File")
        assert file_texts["File/Save Scene As..."].startswith(table["Save Scene As..."])
        sections = [t for t, _sub in file_rows]
        assert iface("Import/Export") in sections and iface("Import/Export") != "Import/Export", sections     # section titles as Blender draws them
    with _Language("en_US"):
        _out, texts = oc.rows("Edit Mesh")
        assert texts["Edit Mesh/Bevel"].startswith("Bevel")


def test_tooltips_follow_the_tooltip_language():
    locale = "zh_HANS"
    if not _usable(locale):
        return
    table = i18n.LANGUAGES[locale]
    path = next(p for p in notices.NOTICES if notices.NOTICES[p][1] in table)
    with _Language(locale):
        text = notices.tooltip(path, mapped=False)
        assert table[notices.NOTICES[path][1]] in text, text
        top = path.split("/")[0]
        assert bpy.app.translations.pgettext_tip(top) in text, text       # the Maya menu path in the tooltip language
        greyed = ms._no_equivalent("File/Archive Scene")
        assert table["No Blender equivalent in Maya Workflow Kit yet"] in greyed, greyed


def test_cjk_wrap():
    lines = i18n.wrap("チャンネルボックスとレイヤエディタはメインビューの右に並びます。 Blender のサイドバーではありません。", 20)
    assert len(lines) > 2
    assert all(i18n.width(line) <= 20 for line in lines), lines
    assert i18n.wrap("plain English words wrap at spaces", 12) == ["plain", "English", "words wrap", "at spaces"]


def test_disable_takes_translations_back():
    locale = "ja_JP"
    if not _usable(locale):
        return
    with _Language(locale):
        assert bpy.app.translations.pgettext_iface(SAMPLES[0]) != SAMPLES[0]
        kit.disable()
        try:
            assert bpy.app.translations.pgettext_iface(SAMPLES[0]) == SAMPLES[0]
        finally:
            kit.enable()
        assert bpy.app.translations.pgettext_iface(SAMPLES[0]) != SAMPLES[0]


def _kit_classes():
    """Registered kit classes (operators, panels, menus ...) whose description comes from their docstring."""
    out = []
    for base in (bpy.types.Operator, bpy.types.Panel, bpy.types.Menu, bpy.types.Header, bpy.types.UIList,
                 bpy.types.PropertyGroup, bpy.types.GizmoGroup, bpy.types.Gizmo):
        stack = list(base.__subclasses__())
        while stack:
            cls = stack.pop()
            stack.extend(cls.__subclasses__())
            if cls.__module__.startswith(kit.MODULE) and "bl_rna" in cls.__dict__ and cls.__doc__:
                out.append(cls)
    return out


def test_tooltips_are_collected_and_translated():
    """A kit class's docstring is its tooltip: the string Blender shows is in the collected ``tooltips`` and in
    every dictionary, and Blender returns the translation for it."""
    tool = _tool()
    collected = tool.tooltips()
    classes = _kit_classes()
    assert len(classes) > 200, len(classes)
    import inspect
    import sys

    def literal(cls):       # written as a class statement (type()-built classes compose their text)
        src = sys.modules[cls.__module__].__file__
        return f"class {cls.__name__}(" in open(src, encoding="utf-8").read()
    shown = {inspect.cleandoc(cls.__doc__) for cls in classes
             if "bl_description" not in cls.__dict__ and "__doc__" in cls.__dict__ and literal(cls)}
    missing = sorted(s for s in shown if s not in collected and tool._ok(s))
    assert not missing, missing[:5]
    for locale in LOCALES:
        table = i18n.LANGUAGES[locale]
        untranslated = sorted(s for s in collected if s not in table)
        assert not untranslated, (locale, untranslated[:5])
        if not _usable(locale):
            continue
        sample = next(inspect.cleandoc(cls.__doc__) for cls in classes
                      if getattr(cls, "bl_idname", "") == "allset.component_slide")
        with _Language(locale):
            assert bpy.app.translations.pgettext_tip(sample) == table[sample], (locale, sample)
