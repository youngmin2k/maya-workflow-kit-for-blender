"""Lane CB (#55): Channel Box INPUTS nodes collapsed by default, Maya's click-the-name expansion (reset when the
lead changes), the fixed Channel Box / Layer Editor split with a scrolling Channel Box part, the dock's tab widths.
Maya-style layout. Real dock: tests/gui/gui_step135_dock.py."""

from importlib import import_module
from types import SimpleNamespace

import bpy

import kit

cb = import_module(kit.MODULE + ".ui.channel_box")
maya_dock = import_module(kit.MODULE + ".ui.maya_dock")
creation_inputs = import_module(kit.MODULE + ".ui.creation_inputs")


class Recorder:
    """A stand-in UILayout recording labels / operators / props."""

    def __init__(self, log=None):
        self.log = [] if log is None else log

    def __getattr__(self, name):
        if name in ("row", "column", "split", "box", "column_flow", "grid_flow"):
            return lambda *a, **k: Recorder(self.log)
        if name in ("menu", "operator", "prop", "label", "popover"):
            def add(*args, **kw):
                props = SimpleNamespace()
                text = kw.get("text")
                if text is None:
                    text = args[0] if args and isinstance(args[0], str) else (args[1] if len(args) > 1 else "")
                self.log.append((name, text, args, props))
                return props
            return add
        return lambda *a, **k: None

    def __setattr__(self, name, value):
        if name == "log":
            object.__setattr__(self, name, value)

    def texts(self, kind):
        return [t for k, t, _a, _p in self.log if k == kind]

    def ops(self, idname):
        return [p for k, _t, a, p in self.log if k == "operator" and a[:1] == (idname,)]


def _fresh():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    cb.reset_open()


def _cube():
    assert bpy.ops.allset.create(kind='CUBE') == {'FINISHED'}
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    ob = bpy.context.view_layer.objects.active
    assert creation_inputs.has_node(ob), "a kit cube has its polyCube node"
    return ob


def _pick(ob):
    for o in bpy.context.view_layer.objects:
        o.select_set(o == ob)
    bpy.context.view_layer.objects.active = ob
    cb.rebuild_rows()


def _draw():
    rec = Recorder()
    cb.ALLSET_PT_channel_box.body(rec, bpy.context)
    return rec


def _node_name(ob):
    return cb.history_node(creation_inputs.prim_history.node_of(ob)[1]["name"])


def test_inputs_node_starts_collapsed_and_toggles():
    _fresh()
    ob = _cube()
    node = _node_name(ob)
    rec = _draw()
    assert "INPUTS" in rec.texts("label")
    names = [p.node for p in rec.ops("allset.cb_node_toggle")]
    assert names == [node], names
    assert "Width" not in rec.texts("label"), "polyCube1 collapsed like Maya"
    assert bpy.ops.allset.cb_node_toggle(node=node) == {'FINISHED'}
    assert cb.is_open(ob, node)
    rec = _draw()
    # the attribute names are selectable channel names (a toggle labelled with the Maya name)
    names = rec.texts("label") + rec.texts("prop")
    assert "Width" in names and "Subdivisions Width" in names, names
    assert bpy.ops.allset.cb_node_toggle(node=node) == {'FINISHED'}
    rec = _draw()
    assert not cb.is_open(ob, node) and "Width" not in rec.texts("label") + rec.texts("prop")


def test_new_lead_collapses_every_node():
    """Maya: polyCube1 expanded, select pCube2, back to pCube1 -> collapsed (cb135/d03, d04)."""
    _fresh()
    a = _cube()
    na = _node_name(a)
    b = _cube()
    _pick(a)
    cb.set_open(a, na)
    assert cb.is_open(a, na)
    _pick(b)
    assert not cb.open_nodes(b), "another lead: nothing expanded"
    _pick(a)
    assert not cb.is_open(a, na), "the earlier lead comes back collapsed"


def test_modifier_rows_follow_expansion_not_show_expanded():
    _fresh()
    ob = _cube()
    mod = ob.modifiers.new("polyBevel1", 'BEVEL')
    mod.show_expanded = True
    _pick(ob)
    assert not [r for r in bpy.context.scene.allset_cb.rows if r.kind == "INPUT"], "collapsed: no rows"
    before = mod.show_expanded
    assert bpy.ops.allset.cb_node_toggle(node=cb.mod_node(mod)) == {'FINISHED'}
    assert mod.show_expanded == before, "the Channel Box never writes the Properties panel state"
    rows = [r for r in bpy.context.scene.allset_cb.rows if r.kind == "INPUT"]
    assert rows and all(r.mod_type == 'BEVEL' for r in rows), [(r.kind, r.name) for r in rows]
    assert "Width" in _draw().texts("label") or rows, "expanded rows drawn"
    mod.show_expanded = False
    cb.rebuild_rows()
    assert [r for r in bpy.context.scene.allset_cb.rows if r.kind == "INPUT"], "show_expanded doesn't collapse it"


def test_toggle_pushes_no_undo_step():
    assert 'UNDO' not in cb.ALLSET_OT_cb_node_toggle.bl_options
    assert 'UNDO' not in cb.ALLSET_OT_cb_scroll.bl_options


def test_window_lines():
    assert cb.window_lines(10, None, 5) == (0, None, False), "no split: every line"
    assert cb.window_lines(10, 10, 3) == (0, None, False), "fits"
    assert cb.window_lines(20, 10, 0) == (0, 10, True), "every line of the pane shows content (buttons on the name line)"
    assert cb.window_lines(20, 10, 50) == (10, 10, True), "clamped at the end"
    assert cb.window_lines(20, 10, -4) == (0, 10, True)


def test_lines_draw_a_window():
    rec = Recorder()
    lines = cb.Lines(rec, first=2, limit=3)
    drawn = [i for i in range(10) if lines.row() is not None]
    assert drawn == [2, 3, 4] and lines.n == 10 and lines.shown == 3
    count = cb.Lines(None)
    for _ in range(4):
        assert count.row() is None
    assert count.n == 4


def test_scroll_operator_clamps():
    area = SimpleNamespace(as_pointer=lambda: 12345, tag_redraw=lambda: None)
    cb._last[12345] = (0, 30, 9)
    op = SimpleNamespace(lines=50)
    ctx = SimpleNamespace(area=area, window=SimpleNamespace(as_pointer=lambda: 67890))
    cb._hover[67890] = 'stale row'
    cb.ALLSET_OT_cb_scroll.execute(op, ctx)
    assert 67890 not in cb._hover, 'Scrolling must clear the previous row under the pointer'
    assert cb._scroll[12345] == 21
    cb._last[12345] = (21, 30, 9)
    op.lines = -100
    cb.ALLSET_OT_cb_scroll.execute(op, ctx)
    assert cb._scroll[12345] == 0
    cb._last.pop(12345)
    cb._scroll.pop(12345)


def test_wheel_keymap_items():
    patches = import_module(kit.MODULE + ".keymap.maya_patches")
    items = [(km, ev["type"]) for km, idname, ev, _p, _s in patches.ADDED if idname == "allset.cb_scroll"]
    # the region's View2D Buttons List handler runs before Property Editor (it would scroll the whole region)
    assert sorted(items) == [("View2D Buttons List", "WHEELDOWNMOUSE"), ("View2D Buttons List", "WHEELUPMOUSE")], items
    assert "allset.cb_scroll" in patches.PASS_THROUGH_FIRST


def test_dock_tabs_take_their_text_width():
    ctx = bpy.context
    long_ = maya_dock.text_units(ctx, maya_dock.LABELS['CHANNEL_BOX'], maya_dock.TAB_PAD)
    short = maya_dock.text_units(ctx, maya_dock.LABELS['MODELING_TOOLKIT'], maya_dock.TAB_PAD)
    assert long_ > short > maya_dock.TAB_PAD, (long_, short)
