"""Issue #205: with Move / Rotate / Scale, a drag off the manipulator is Maya's marquee even when the tool's Drag
fallback (workspace data) is Blender's Tweak. The kit binds the marquee in the Tweak fallback keymaps (add-on
keymap items, gone with Maya mode) and never rewrites the workspace's fallback.

The drag itself is checked in tests/gui/gui_issue205_tweak_fallback.py."""

from importlib import import_module

import bpy

import kit

patches = import_module(kit.MODULE + ".keymap.maya_patches")

PAIRS = (("3D View Tool: Tweak (fallback)", "3D View Tool: Select Box (fallback)", "view3d.select_box"),
         ("Image Editor Tool: Uv, Tweak (fallback)", "Image Editor Tool: Uv, Select Box (fallback)", "uv.select_box"))
MODS = ((False, False), (True, False), (False, True), (True, True))


def _drag_items(km):
    """{(shift, ctrl): [(idname, props)]} of the LMB CLICK_DRAG items without Alt, in keymap order."""
    out = {}
    for k in km.keymap_items:
        if k.active and k.type == 'LEFTMOUSE' and k.value == 'CLICK_DRAG' and not k.alt:
            props = {p: getattr(k.properties, p) for p in ("mode",) if k.properties and hasattr(k.properties, p)}
            out.setdefault((k.shift, k.ctrl), []).append((k.idname, props))
    return out


def test_tweak_fallback_drag_is_the_select_box_marquee():
    kc = kit.maya_kc()
    for tweak, box, idname in PAIRS:
        got, want = _drag_items(kc.keymaps[tweak]), _drag_items(kc.keymaps[box])
        for mods in MODS:
            boxes = [it for it in want.get(mods, []) if it[0] == idname]
            assert boxes, (box, mods, want)
            assert got.get(mods) == want.get(mods), (tweak, mods, got.get(mods), want.get(mods))


def test_tweak_fallback_listed_with_the_marquee_keymaps():
    assert "3D View Tool: Tweak (fallback)" in patches.SELECT_DRAG_KEYMAPS          # select-through
    assert "Image Editor Tool: Uv, Tweak (fallback)" in patches.UV_SHELL_DRAG_KEYMAPS   # UV shell box


def test_lasso_and_circle_fallbacks_unchanged():
    kc = kit.maya_kc()
    for name, idname in (("3D View Tool: Select Lasso (fallback)", "view3d.select_lasso"),
                         ("3D View Tool: Select Circle (fallback)", "view3d.select_circle")):
        ids = {k.idname for k in kc.keymaps[name].keymap_items if k.active and k.type == 'LEFTMOUSE'}
        assert idname in ids and "view3d.select_box" not in ids, (name, ids)


def _view3d():
    area = next((a for a in bpy.context.screen.areas if a.type == 'VIEW_3D'), None) if bpy.context.screen else None
    if area is None:
        return None, None
    return area, next(r for r in area.regions if r.type == 'WINDOW')


def test_workspace_fallback_left_alone():
    """The user's Drag fallback stays what it was (nothing written to the workspace / .blend)."""
    area, region = _view3d()
    if area is None:
        return
    with bpy.context.temp_override(area=area, region=region):
        bpy.ops.wm.tool_set_by_id(name="builtin.move")
        bpy.ops.wm.tool_set_by_id(name="builtin.select", as_fallback=True)
        bpy.ops.wm.tool_set_by_id(name="builtin.select_box")
        bpy.ops.wm.tool_set_by_id(name="builtin.move")
        tool = bpy.context.workspace.tools.from_space_view3d_mode(bpy.context.mode, create=False)
        assert (tool.idname, tool.idname_fallback) == ("builtin.move", "builtin.select"), \
            (tool.idname, tool.idname_fallback)


def test_maya_mode_off_removes_the_marquee():
    kc = bpy.context.window_manager.keyconfigs.addon
    kit.disable()
    try:
        for tweak, _box, _idname in PAIRS:
            km = kc.keymaps.get(tweak)
            left = [k.idname for k in km.keymap_items] if km is not None else []
            assert not left, (tweak, left)
    finally:
        kit.enable()
    assert _drag_items(kit.maya_kc().keymaps[PAIRS[0][0]])
