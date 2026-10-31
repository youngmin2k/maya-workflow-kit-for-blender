"""#199: no kit Maya menu draw raises a Python error — also while an operator it draws is missing.

Every kit menu class (the Maya menu bar menus with all their submenus, the editor menu bars, the Status Line /
workspace / symmetry / UI Elements menus ...) and the top bar / Status Line draw functions are drawn into a
recording stand-in for ``UILayout``. ``UILayout.operator`` returns None for an operator Blender doesn't know; the
second pass makes the stand-in do that for ``allset.menu_tear_off`` (unregistered for real) and for every operator
that isn't registered, as a half-registered kit would see it (#199: one AttributeError emptied every menu).
"""

import traceback
from importlib import import_module
from types import SimpleNamespace

import bpy

import kit


def _mod(name):
    return import_module(f"{kit.MODULE}.{name}")


def _op_known(idname):
    mod, _, name = idname.partition(".")
    try:
        getattr(getattr(bpy.ops, mod), name).get_rna_type()
        return True
    except (AttributeError, KeyError):
        return False


class Recorder:
    """Stands in for a UILayout: any layout call is accepted and logged; ``operator`` gives a props stand-in, or
    None like Blender when ``missing(idname)`` says the operator is unknown."""

    def __init__(self, log, missing):
        object.__setattr__(self, "log", log)
        object.__setattr__(self, "missing", missing)

    def _sub(self, *_a, **_k):
        return Recorder(self.log, self.missing)

    row = column = split = box = column_flow = grid_flow = _sub

    def operator(self, idname, *a, **k):
        self.log.append(("op", k.get("text", ""), idname))
        return None if self.missing(idname) else SimpleNamespace()

    operator_menu_hold = operator

    def operator_menu_enum(self, idname, *a, **k):
        self.log.append(("op", k.get("text", ""), idname))
        return None if self.missing(idname) else SimpleNamespace()

    def __getattr__(self, name):          # label / prop / menu / separator / template_* / popover ...
        def call(*a, **k):
            self.log.append((name, k.get("text", ""), a[0] if a and isinstance(a[0], str) else None))
            return Recorder(self.log, self.missing)
        return call

    def __setattr__(self, name, value):   # scale_x, enabled, emboss, operator_context ...
        pass


def kit_menus():
    """Every registered kit Menu class with its own draw (Blender-editor menus the kit only wraps need their
    editor's space and are left out: ``ALLSET_MT_ed_blender_*``, the proxies of Blender menus)."""
    ms = _mod("ui.menu_sets")
    proxies = set(getattr(ms, "_proxies", {}).values())
    out = []
    for name in sorted(dir(bpy.types)):
        if not name.startswith("ALLSET_MT_") or name.startswith("ALLSET_MT_ed_blender_"):
            continue
        cls = getattr(bpy.types, name)
        if not (isinstance(cls, type) and issubclass(cls, bpy.types.Menu)) or not hasattr(cls, "draw"):
            continue
        if cls in proxies or getattr(cls, "bl_idname", name) in proxies:
            continue
        out.append(cls)
    return out


def maya_menus():
    """The Maya menu bar menus with every submenu, the editor menu bars and the Status Line / top bar menus."""
    ms = _mod("ui.menu_sets")
    names = {getattr(c, "bl_idname", c.__name__) for c in ms._menu_classes}
    names |= {"ALLSET_MT_menu_bar", "ALLSET_MT_ui_elements", "ALLSET_MT_option_box", "ALLSET_MT_menu_more",
              "ALLSET_MT_symmetry", "ALLSET_MT_maya_workspaces"}
    return [c for c in kit_menus() if getattr(c, "bl_idname", c.__name__) in names]


def _self(cls, layout):
    """``self`` of a menu draw: the layout plus the class's own attributes."""
    return type("MenuSelf", (), {"layout": layout, "bl_idname": getattr(cls, "bl_idname", cls.__name__),
                                 "__getattr__": lambda _s, n: getattr(cls, n)})()


def _context():
    """A window / top bar context when the file has one (``-b`` keeps the startup file's window)."""
    wm = bpy.context.window_manager
    window = wm.windows[0] if wm.windows else None
    if window is None:
        return None, None
    area = next((a for a in window.screen.areas if a.type == 'VIEW_3D'), None)
    region = next((r for r in area.regions if r.type == 'WINDOW'), None) if area else None
    return window, (area, region)


# Menus that read their own editor's space: drawn with an area of that type when the file has one.
SPACE_OF = {"ALLSET_MT_outliner_show": 'OUTLINER'}


def _area(window, kind):
    area = next((a for a in window.screen.areas if a.type == kind), None) if window else None
    region = next((r for r in area.regions if r.type == 'WINDOW'), None) if area else None
    return area, region


def _draw_menu(cls, rec, window):
    kind = SPACE_OF.get(cls.__name__)
    if kind is None:
        cls.draw(_self(cls, rec), bpy.context)
        return
    area, region = _area(window, kind)
    if area is None:
        return
    with bpy.context.temp_override(area=area, region=region):
        cls.draw(_self(cls, rec), bpy.context)


def draw_everything(missing, menus):
    """(drawn count, [error text]) for ``menus`` + the top bar / Status Line draws."""
    errors, drawn = [], 0
    ms = _mod("ui.menu_sets")
    sl = _mod("ui.status_line")
    window, (area, region) = _context()
    override = {"window": window, "screen": window.screen, "area": area, "region": region} if window else {}
    with bpy.context.temp_override(**override):
        context = bpy.context
        for cls in menus:
            rec = Recorder([], missing)
            try:
                _draw_menu(cls, rec, window)
            except Exception:
                errors.append(f"{cls.__name__}: {traceback.format_exc(limit=4)}")
            drawn += 1
        for label, fn in (("menu_bar", lambda rec: ms.draw_menu_bar(rec, context)),
                          ("status_line", lambda rec: sl.draw_status_line(rec, context)),
                          ("status_line compact", lambda rec: sl.draw_status_line(rec, context, compact=True))):
            try:
                fn(Recorder([], missing))
            except Exception:
                errors.append(f"{label}: {traceback.format_exc(limit=4)}")
            drawn += 1
    return drawn, errors


def _assert_clean(drawn, errors, what):
    assert drawn > 300, f"{what}: only {drawn} menus drawn (the Maya menus didn't register?)"
    assert not errors, f"{what}: {len(errors)} of {drawn} draws raised:\n" + "\n".join(errors[:6])


def test_every_kit_menu_draws_without_errors():
    drawn, errors = draw_everything(lambda idname: not _op_known(idname), kit_menus())
    _assert_clean(drawn, errors, "registered kit")
    print(f"step279: {drawn} menu / bar draws, 0 errors")


def test_menus_draw_with_the_tear_off_operator_missing():
    md = _mod("ui.maya_dock")
    bpy.utils.unregister_class(md.ALLSET_OT_menu_tear_off)
    try:
        assert not _op_known("allset.menu_tear_off")
        drawn, errors = draw_everything(lambda idname: not _op_known(idname), kit_menus())
        _assert_clean(drawn, errors, "allset.menu_tear_off unregistered")
    finally:
        bpy.utils.register_class(md.ALLSET_OT_menu_tear_off)


def test_menus_draw_with_every_kit_operator_missing():
    """The worst half-registered kit: every allset.* operator returns None (Maya menus + Status Line)."""
    drawn, errors = draw_everything(lambda idname: idname.startswith("allset.") or not _op_known(idname),
                                    maya_menus())
    _assert_clean(drawn, errors, "every allset operator missing")


def test_recorder_sees_a_none_assignment():
    """Guard against a vacuous pass: a draw that sets a property on a missing operator's None fails here."""
    rec = Recorder([], lambda idname: True)
    try:
        rec.operator("allset.nothing").value = 1
    except AttributeError:
        return
    raise AssertionError("the recorder did not return None for a missing operator")
