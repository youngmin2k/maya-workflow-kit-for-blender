"""Issue #178: Maya D hold (pivot edit) — the OS key repeat of the held key must not cancel the
manipulator's drag, and another add-on's D item mustn't run before the kit's Maya key in Maya mode.

Blender's rule (wm_event_system.cc 4.5 :3740-3749): a keyboard event a handler *handles* cancels the pending LMB
CLICK_DRAG; a repeat nothing handles doesn't (:3683). The GUI side: tests/gui/gui_step265_pivot_hold.py."""

from importlib import import_module
from types import SimpleNamespace

import bpy

import kit

hold = import_module(kit.MODULE + ".operators.hold")
keymap = import_module(kit.MODULE + ".keymap")


def _ev(type_, value, repeat=False):
    return SimpleNamespace(type=type_, value=value, is_repeat=repeat)


def test_key_repeat_of_the_held_key_is_not_handled():
    done = []
    stub = SimpleNamespace(_key='D', _finish=lambda context: done.append(1) or {'FINISHED'})
    modal = hold.ALLSET_OT_hold.modal
    assert modal(stub, bpy.context, _ev('D', 'PRESS', repeat=True)) == {'PASS_THROUGH'}
    assert modal(stub, bpy.context, _ev('D', 'PRESS')) == {'RUNNING_MODAL'}
    assert not done
    assert modal(stub, bpy.context, _ev('D', 'RELEASE')) == {'FINISHED'} and done


def test_kit_hold_items_ignore_repeats():
    # a passed-on repeat must not start a second hold
    kc = kit.maya_kc()
    items = [k for km in kc.keymaps for k in km.keymap_items if k.idname == "allset.hold" and k.active]
    assert items
    assert not any(k.repeat for k in items), [(k.type, k.properties.name) for k in items if k.repeat]


def _foreign():
    kc = bpy.context.window_manager.keyconfigs.addon
    km = kc.keymaps.new("Object Mode", space_type='EMPTY', region_type='WINDOW')
    return km, km.keymap_items.new("wm.context_toggle", 'D', 'PRESS')


def _index(km, pred):
    return [i for i, k in enumerate(km.keymap_items) if pred(k)]


def test_kit_keys_stay_first_over_another_addons_same_key():
    km, other = _foreign()
    kit_d = lambda k: k.idname == "allset.hold" and k.type == 'D' and not (k.shift or k.ctrl or k.alt)
    try:
        # Blender's merge puts later add-on items first: the foreign D comes after the kit's in the list
        assert _index(km, lambda k: k == other)[0] > _index(km, kit_d)[0]
        assert keymap._keep_first() >= 1
        assert _index(km, kit_d)[0] > _index(km, lambda k: k.idname == "wm.context_toggle")[0]
        assert keymap._keep_first() == 0                    # nothing changed: no work
        # the kit's moved items are still the ones it removes on Maya mode off
        ptrs = keymap._state["addon_items"]
        assert all(k.as_pointer() in ptrs for k in km.keymap_items if k.idname == "allset.hold")
    finally:
        for k in [k for k in km.keymap_items if k.idname == "wm.context_toggle" and k.type == 'D']:
            km.keymap_items.remove(k)


def test_an_inactive_or_different_foreign_key_moves_nothing():
    km, other = _foreign()
    try:
        other.active = False
        keymap._state["addon_count"] = -1
        assert keymap._keep_first() == 0
        other.active, other.shift = True, True              # Shift+D is the kit's Duplicate with Transform...
        other.type = 'F13'                                  # ...so use a key the kit doesn't bind
        keymap._state["addon_count"] = -1
        assert keymap._keep_first() == 0
    finally:
        km.keymap_items.remove(other)
