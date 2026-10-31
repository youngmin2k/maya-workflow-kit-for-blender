# SPDX-License-Identifier: GPL-3.0-or-later
"""L15: blendShape in-between and combination targets on shape keys.

Maya (``inbetween_one`` / ``inbetween_two`` /
``combination_two`` / ``combination_three``):

- In-betweens: the target's deformation is **piecewise linear** in its weight between the breakpoints
  0 < p1 < ... < pn = 1 (the in-between weights, item index 5000 + 1000·w, and the target at 1); outside [0, 1] the
  end segments are extended (w < 0 follows the first segment, w > 1 the last).
- Combinations (``combinationShape``): the combination target's weight = product of the inputs (multiplication,
  default, negatives included), their minimum (lowest weighting) or n·Π / Σ(products of n − 1) (smooth = harmonic
  mean), 0 when any input ≤ 0 for smooth.

Blender: shape keys + **simple-expression drivers** (no Python, so they
run without "Auto Run Python Scripts" and survive the kit being disabled):

- the user handle stays the target key (``smile``), value = Maya weight: Channel Box, Shape Editor, SDK, keys and FBX
  keep working;
- each in-between = a hidden key ``<target>_ib<round(1000 w)>`` holding that shape (relative to the Basis), driven by
  its piecewise-linear basis coefficient of the target value; one more hidden key ``<target>_ibfix`` = a copy of the
  target, driven by coef_target(w) − w, so target·w + fix = target·coef_target: the sum equals Maya exactly;
- a combination = a target whose value is driven by the input targets' values; method in the Key ID property
  ``allset_combinations``.

Records (Key ID properties): ``allset_inbetweens`` = {target: {"<round(1000 w)>": display name}},
``allset_combinations`` = {target: {"inputs": [names], "method": 0 | 1 | 2}}. A deferred sync (depsgraph handler →
0 s timer) keeps the fix copies equal to their targets, the helpers' mute / vertex group equal to the target's and
drops records whose keys went away.
"""

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, StringProperty

INB = "allset_inbetweens"
COMB = "allset_combinations"
METHODS = (('MULTIPLY', "Multiplication", "Product of the input weights (the default, like Maya)"),
           ('LOWEST', "Lowest Weighting", "The smallest input weight"),
           ('SMOOTH', "Smooth", "Harmonic mean of the input weights, 0 when any is 0 or less"))
METHOD_IDS = [m[0] for m in METHODS]
HELPER_RANGE = 10.0          # helper coefficients go negative / above 1 outside [0, 1]
VAR = "w"


# --- pure maths (no bpy) --------------------------------------------------------------------------------------------

def _num(x):
    return format(float(x), ".10g")


def breakpoints(weights):
    """Sorted breakpoints p1 < ... < pn = 1 of a target with in-betweens at ``weights`` (Maya L15)."""
    return sorted({round(float(w), 3) for w in weights if 0.0 < float(w) < 1.0}) + [1.0]


def coefficient(points, k, w):
    """Basis coefficient of breakpoint ``points[k]`` at target weight ``w`` (piecewise linear, p0 = 0 with a zero
    shape, end segments extended)."""
    p = [0.0] + list(points)
    n = len(points)
    j = k + 1                                  # index into p
    if n == 1:
        return w
    rise = (w - p[j - 1]) / (p[j] - p[j - 1])
    if j == n:
        return rise if w >= p[j - 1] else 0.0
    fall = (p[j + 1] - w) / (p[j + 1] - p[j])
    if w <= p[j]:
        return rise if (j == 1 or w >= p[j - 1]) else 0.0
    return fall if (j == n - 1 or w <= p[j + 1]) else 0.0


def coefficient_expr(points, k, var=VAR):
    """``coefficient`` as a Blender simple expression of the target value ``var``."""
    p = [0.0] + list(points)
    n = len(points)
    j = k + 1
    if n == 1:
        return var
    lo, at = p[j - 1], p[j]
    rise = f"{var} / {_num(at)}" if lo == 0.0 else f"({var} - {_num(lo)}) / {_num(at - lo)}"
    if j == n:
        return f"({rise} if {var} >= {_num(lo)} else 0.0)"
    hi = p[j + 1]
    fall = f"({_num(hi)} - {var}) / {_num(hi - at)}"
    up = rise if j == 1 else f"({rise} if {var} >= {_num(lo)} else 0.0)"
    down = fall if j == n - 1 else f"({fall} if {var} <= {_num(hi)} else 0.0)"
    return f"(({up}) if {var} <= {_num(at)} else ({down}))"


def inbetween_exprs(weights, var=VAR):
    """{breakpoint weight (in-betweens only): expression, "fix": expression} for a target with in-betweens."""
    pts = breakpoints(weights)
    out = {pts[k]: coefficient_expr(pts, k, var) for k in range(len(pts) - 1)}
    out["fix"] = f"{coefficient_expr(pts, len(pts) - 1, var)} - {var}"
    return out


def combination_value(values, method='MULTIPLY'):
    """Maya combinationShape outputWeight (combination_two / _three)."""
    vals = [float(v) for v in values]
    if method == 'LOWEST':
        return min(vals)
    prod = 1.0
    for v in vals:
        prod *= v
    if method == 'MULTIPLY':
        return prod
    if min(vals) <= 0.0:
        return 0.0
    n = len(vals)
    return n * prod / sum(prod / v for v in vals)


def _nested_min(names):
    out = names[0]
    for x in names[1:]:
        out = f"min({out}, {x})"
    return out


def combination_expr(n, method='MULTIPLY'):
    """Blender simple expression over variables w0 ... w{n-1} for ``combination_value``."""
    names = [f"w{i}" for i in range(n)]
    if method == 'LOWEST':
        return _nested_min(names)
    prod = " * ".join(names)
    if method == 'MULTIPLY':
        return prod
    parts = [" * ".join(names[:i] + names[i + 1:]) or "1.0" for i in range(n)]
    return f"(0.0 if {_nested_min(names)} <= 0.0 else {n} * {prod} / ({' + '.join(parts)}))"


def ib_name(target, weight):
    return f"{target}_ib{round(float(weight) * 1000)}"


def fix_name(target):
    return f"{target}_ibfix"


# --- records --------------------------------------------------------------------------------------------------------

def inbetweens(key):
    """{target: [(weight, display name)]} sorted by weight."""
    rec = key.get(INB) if key is not None else None
    out = {}
    if not rec:
        return out
    for target, items in rec.items():
        out[target] = sorted(((int(code) / 1000.0, str(name)) for code, name in items.items()), key=lambda t: t[0])
    return out


def combinations(key):
    """{target: (inputs, method id)}."""
    rec = key.get(COMB) if key is not None else None
    out = {}
    if not rec:
        return out
    for target, item in rec.items():
        m = int(item.get("method", 0))
        out[target] = ([str(x) for x in item.get("inputs", [])], METHOD_IDS[m if 0 <= m < 3 else 0])
    return out


def helper_names(key):
    """Names of the hidden in-between / fix keys (never listed as Maya targets)."""
    out = set()
    for target, items in inbetweens(key).items():
        out.add(fix_name(target))
        out.update(ib_name(target, w) for w, _n in items)
    return out


def is_helper(key, name):
    return name in helper_names(key)


def target_blocks(key):
    """The Maya targets of ``key``: key blocks after the Basis, helpers left out."""
    if key is None:
        return []
    hidden = helper_names(key)
    return [kb for kb in key.key_blocks[1:] if kb.name not in hidden]


# --- drivers --------------------------------------------------------------------------------------------------------

def _path(name):
    return f'key_blocks["{bpy.utils.escape_identifier(name)}"].value'


def _undrive(key, name):
    ad = key.animation_data
    if ad is not None and any(fc.data_path == _path(name) for fc in ad.drivers):
        key.driver_remove(_path(name))


def _drive(key, name, expr, inputs):
    """Simple-expression driver on key block ``name``'s value; ``inputs`` = [(variable, key block name)]."""
    _undrive(key, name)
    fc = key.driver_add(_path(name))
    drv = fc.driver
    drv.type = 'SCRIPTED'
    while drv.variables:
        drv.variables.remove(drv.variables[0])
    for var, src in inputs:
        v = drv.variables.new()
        v.name = var
        v.type = 'SINGLE_PROP'
        v.targets[0].id_type = 'KEY'
        v.targets[0].id = key
        v.targets[0].data_path = _path(src)
    drv.expression = expr
    # a new driver F-curve maps its value (4.5: a Generator modifier, 5.x: keys (0, 0) (1, 1)): the expression alone
    for m in list(fc.modifiers):
        fc.modifiers.remove(m)
    fc.keyframe_points.clear()
    return fc


def driver_of(key, name):
    ad = key.animation_data if key is not None else None
    if ad is None:
        return None
    fc = next((f for f in ad.drivers if f.data_path == _path(name)), None)
    return fc.driver if fc is not None else None


def _coords(points):
    flat = [0.0] * (len(points) * 3)
    points.foreach_get("co", flat)
    return flat


def _helper(ob, key, name, flat, like):
    """Key block ``name`` with absolute coords ``flat`` (a new one if missing), relative to the Basis."""
    kb = key.key_blocks.get(name)
    if kb is None:
        kb = ob.shape_key_add(name=name, from_mix=False)
    kb.data.foreach_set("co", flat)
    kb.relative_key = key.reference_key
    kb.slider_min, kb.slider_max = -HELPER_RANGE, HELPER_RANGE
    kb.vertex_group = like.vertex_group
    kb.mute = like.mute
    return kb


def rebuild_inbetweens(key, target):
    """(Re)make the fix key and the drivers of ``target``'s in-betweens from the record (nothing left = helpers go)."""
    from ..ui import shape_editor
    ob = shape_editor.owner(key)
    items = inbetweens(key).get(target, [])
    kb = key.key_blocks.get(target)
    fix = key.key_blocks.get(fix_name(target))
    if not items or kb is None or ob is None:
        for name in [fix_name(target)] + [ib_name(target, w) for w, _n in items]:
            _drop_block(ob, key, name)
        rec = key.get(INB)
        if rec is not None and target in rec:
            del rec[target]
        return
    with shape_editor._object_mode(ob):
        fix = _helper(ob, key, fix_name(target), _coords(kb.data), kb)
        exprs = inbetween_exprs([w for w, _n in items])
        for w, _n in items:
            hb = key.key_blocks.get(ib_name(target, w))
            if hb is None:
                continue
            hb.slider_min, hb.slider_max = -HELPER_RANGE, HELPER_RANGE
            _drive(key, hb.name, exprs[round(w, 3)], [(VAR, target)])
        _drive(key, fix.name, exprs["fix"], [(VAR, target)])
    key.update_tag()


def _drop_block(ob, key, name):
    kb = key.key_blocks.get(name)
    if kb is None:
        return
    _undrive(key, name)
    if ob is not None:
        ob.shape_key_remove(kb)


def interpolated(key, target, weight):
    """Absolute coords of ``target``'s shape at ``weight`` (what the mesh shows from this target alone)."""
    base = _coords(key.reference_key.data)
    items = inbetweens(key).get(target, [])
    pts = breakpoints([w for w, _n in items])
    shapes = [key.key_blocks.get(ib_name(target, w)) for w, _n in items] + [key.key_blocks[target]]
    out = list(base)
    for k, kb in enumerate(shapes):
        if kb is None:
            continue
        c = coefficient(pts, k, weight)
        if c == 0.0:
            continue
        co = _coords(kb.data)
        for i in range(len(out)):
            out[i] += c * (co[i] - base[i])
    return out


def add_inbetween(key, target, weight, flat=None, name=""):
    """Maya ``cmds.blendShape(edit=True, inBetween=True)``: an in-between of ``target`` at ``weight`` with absolute
    coords ``flat`` (None = the shape the target has at that weight, like Maya's Add In-Between Target). Returns the
    helper key block."""
    from ..ui import shape_editor
    weight = round(float(weight), 3)
    if not 0.0 < weight < 1.0:
        raise ValueError("In-between weight must be between 0 and 1 (the target is at 1)")
    ob = shape_editor.owner(key)
    kb = key.key_blocks.get(target)
    if kb is None or ob is None:
        raise ValueError(f"No target {target}")
    code = str(round(weight * 1000))
    rec = key.get(INB)
    if rec is not None and target in rec and code in rec[target]:
        raise ValueError(f"{target} already has an in-between at {weight:.3f}")
    if flat is None:
        flat = interpolated(key, target, weight)
    with shape_editor._object_mode(ob):
        hb = _helper(ob, key, ib_name(target, weight), flat, kb)
    if key.get(INB) is None:
        key[INB] = {}
    rec = key[INB]
    if target not in rec:
        rec[target] = {}
    rec[target][code] = name or hb.name
    rebuild_inbetweens(key, target)
    return key.key_blocks[ib_name(target, weight)]


def remove_inbetween(key, target, weight):
    from ..ui import shape_editor
    code = str(round(float(weight) * 1000))
    rec = key.get(INB)
    if rec is None or target not in rec or code not in rec[target]:
        return False
    del rec[target][code]
    with shape_editor._object_mode(shape_editor.owner(key)):
        _drop_block(shape_editor.owner(key), key, ib_name(target, weight))
    rebuild_inbetweens(key, target)
    return True


def set_combination(key, target, inputs, method='MULTIPLY'):
    """Make ``target``'s value the combination of ``inputs`` (combinationShape -cti target -dti inputs)."""
    inputs = [n for n in inputs if n != target]
    if not inputs:
        raise ValueError("A combination target needs driver targets")
    for n in inputs + [target]:
        if key.key_blocks.get(n) is None:
            raise ValueError(f"No target {n}")
    if key.get(COMB) is None:
        key[COMB] = {}
    key[COMB][target] = {"inputs": list(inputs), "method": METHOD_IDS.index(method)}
    rebuild_combination(key, target)


def rebuild_combination(key, target):
    item = combinations(key).get(target)
    kb = key.key_blocks.get(target)
    if item is None or kb is None:
        return
    inputs, method = item
    kb.slider_min, kb.slider_max = -HELPER_RANGE, HELPER_RANGE
    _drive(key, target, combination_expr(len(inputs), method), [(f"w{i}", n) for i, n in enumerate(inputs)])
    key.update_tag()


def remove_combination(key, target):
    rec = key.get(COMB)
    if rec is None or target not in rec:
        return False
    del rec[target]
    _undrive(key, target)
    return True


# --- sync -----------------------------------------------------------------------------------------------------------

def sync(key):
    """Keep helpers in step with their targets; drop records whose keys are gone. Returns True when it wrote."""
    from ..ui import shape_editor
    wrote = False
    ob = shape_editor.owner(key)
    if ob is None or ob.mode == 'EDIT':
        return False
    for target, items in list(inbetweens(key).items()):
        kb = key.key_blocks.get(target)
        if kb is None:
            rebuild_inbetweens_missing(key, target, items, ob)
            wrote = True
            continue
        gone = [w for w, _n in items if key.key_blocks.get(ib_name(target, w)) is None]
        if gone:
            for w in gone:
                del key[INB][target][str(round(w * 1000))]
            rebuild_inbetweens(key, target)
            wrote = True
            continue
        fix = key.key_blocks.get(fix_name(target))
        if fix is None:
            rebuild_inbetweens(key, target)
            wrote = True
            continue
        if _coords(fix.data) != _coords(kb.data):
            fix.data.foreach_set("co", _coords(kb.data))
            wrote = True
        for name in [fix.name] + [ib_name(target, w) for w, _n in items]:
            hb = key.key_blocks[name]
            if hb.mute != kb.mute or hb.vertex_group != kb.vertex_group:
                hb.mute, hb.vertex_group = kb.mute, kb.vertex_group
                wrote = True
    for target, (inputs, _m) in list(combinations(key).items()):
        if key.key_blocks.get(target) is None or any(key.key_blocks.get(n) is None for n in inputs):
            remove_combination(key, target)
            wrote = True
    if wrote:
        key.update_tag()
    return wrote


def rebuild_inbetweens_missing(key, target, items, ob):
    """The target went away (deleted in Blender): its helpers and record go too."""
    for name in [fix_name(target)] + [ib_name(target, w) for w, _n in items]:
        _drop_block(ob, key, name)
    rec = key.get(INB)
    if rec is not None and target in rec:
        del rec[target]


_pending = set()


def _tick():
    names = list(_pending)
    _pending.clear()
    for name in names:
        key = bpy.data.shape_keys.get(name)
        if key is not None:
            try:
                sync(key)
            except (RuntimeError, ReferenceError, KeyError, ValueError):
                pass
    return None


@bpy.app.handlers.persistent
def _on_depsgraph(scene, depsgraph):
    for u in depsgraph.updates:
        idb = getattr(u.id, "original", u.id)
        key = None
        if isinstance(idb, bpy.types.Key):
            key = idb
        elif isinstance(idb, bpy.types.Mesh):
            key = idb.shape_keys
        elif isinstance(idb, bpy.types.Object) and idb.type == 'MESH' and u.is_updated_geometry:
            key = idb.data.shape_keys
        if key is not None and (key.get(INB) or key.get(COMB)):
            _pending.add(key.name)
    if _pending and not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick, first_interval=0.0)


# --- operators ------------------------------------------------------------------------------------------------------

def _resolve(context, op):
    """(key, target name) an operator works on: its own props, else the Shape Editor's current target."""
    from ..ui import shape_editor
    if op.key:
        key = bpy.data.shape_keys.get(op.key)
        return key, (op.target if key is not None and key.key_blocks.get(op.target) else None)
    key, index = shape_editor.current(context)
    if key is None:
        return None, None
    return key, (key.key_blocks[index].name if index is not None else None)


def _picked(context, key):
    """Targets picked in the Shape Editor (in pick order) for ``key``."""
    wm = context.window_manager
    text = getattr(wm, "allset_se_picked", "")
    name, _, rest = text.partition("/")
    if name != key.name:
        return []
    return [n for n in rest.split("\t") if n and key.key_blocks.get(n) is not None]


def _redraw(context):
    from ..ui import shape_editor
    shape_editor.redraw(context)


class ALLSET_OT_shape_add_inbetween(bpy.types.Operator):
    """Add an in-between target to the selected target at a weight: the target blends piecewise linearly through it
    (Maya Shape Editor Create > Add In-Between Target)"""
    bl_idname = "allset.shape_add_inbetween"
    bl_label = "Add In-Between Target"
    bl_options = {'UNDO'}

    key: StringProperty(options={'SKIP_SAVE'})
    target: StringProperty(options={'SKIP_SAVE'})
    weight: FloatProperty(name="In-between weight", default=0.5, min=0.001, max=0.999, precision=3,
                          description="Target weight at which the in-between shape is reached (the target is at 1)")
    selection: BoolProperty(name="From selection", default=False, options={'SKIP_SAVE'},
                            description="Use the selected meshes as in-between shapes")
    option_box: BoolProperty(options={'SKIP_SAVE', 'HIDDEN'})

    def invoke(self, context, event):
        if self.option_box:
            return context.window_manager.invoke_props_dialog(self, title="Add In-Between Target Options")
        return self.execute(context)

    def draw(self, context):
        self.layout.prop(self, "weight")

    def execute(self, context):
        from ..ui import shape_editor
        key, target = _resolve(context, self)
        if key is None or target is None or is_helper(key, target):
            self.report({'WARNING'}, "Select a target in the Shape Editor to add an in-between to")
            return {'CANCELLED'}
        ob = shape_editor.owner(key)
        shapes = [None]
        if self.selection:
            n = len(key.reference_key.data)
            shapes = [o for o in context.selected_objects if o.type == 'MESH' and o != ob and len(o.data.vertices) == n]
            if not shapes:
                self.report({'ERROR'}, f"Select meshes with the same vertex count as {ob.name}")
                return {'CANCELLED'}
        made = None
        try:
            for i, src in enumerate(shapes):
                # several meshes: weights w, 2w, 3w ... (Maya's Add In-Between Target accumulates)
                w = round(self.weight * (i + 1), 3)
                flat = None if src is None else [c for v in src.data.vertices for c in v.co]
                made = add_inbetween(key, target, w, flat, name=src.name if src is not None else "")
        except ValueError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'} if made is None else {'FINISHED'}
        if not self.selection:
            # the empty in-between goes into Edit (sculptTarget -ibw w, like Maya's Add In-Between Target)
            shape_editor.edit_on(context, key, key.key_blocks.find(made.name))
        _redraw(context)
        return {'FINISHED'}


class ALLSET_OT_shape_remove_inbetween(bpy.types.Operator):
    """Delete this in-between target (Maya blendShapeDeleteInBetweenTarget)"""
    bl_idname = "allset.shape_remove_inbetween"
    bl_label = "Delete In-Between Target"
    bl_options = {'UNDO'}

    key: StringProperty(options={'SKIP_SAVE'})
    target: StringProperty(options={'SKIP_SAVE'})
    weight: FloatProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        key = bpy.data.shape_keys.get(self.key)
        if key is None or not remove_inbetween(key, self.target, self.weight):
            return {'CANCELLED'}
        _redraw(context)
        return {'FINISHED'}


class ALLSET_OT_shape_add_combination(bpy.types.Operator):
    """Add a combination target driven by the selected targets: its weight = their product (or lowest / smooth)
    (Maya Shape Editor Create > Add Combination Target)"""
    bl_idname = "allset.shape_add_combination"
    bl_label = "Add Combination Target"
    bl_options = {'UNDO'}

    key: StringProperty(options={'SKIP_SAVE'})
    targets: StringProperty(options={'SKIP_SAVE'}, description="Driver targets, tab separated (else the picked ones)")
    method: EnumProperty(name="Combination method", items=METHODS, default='MULTIPLY')
    mode: EnumProperty(items=(('NEW', "New", "A new target (copy of the base)"),
                              ('SELECTION', "Selection", "The selected meshes; the last one is the combination"),
                              ('SET', "Set", "The last picked target becomes the combination of the others")),
                       default='NEW', options={'SKIP_SAVE'})
    option_box: BoolProperty(options={'SKIP_SAVE', 'HIDDEN'})

    def invoke(self, context, event):
        if self.option_box:
            return context.window_manager.invoke_props_dialog(self, title="Add Combination Target Options")
        return self.execute(context)

    def draw(self, context):
        self.layout.prop(self, "method")

    def execute(self, context):
        from ..ui import shape_editor
        key = bpy.data.shape_keys.get(self.key) if self.key else shape_editor._key_of(context)
        if key is None:
            self.report({'ERROR'}, "No blend shape selected in the Shape Editor")
            return {'CANCELLED'}
        ob = shape_editor.owner(key)
        names = ([n for n in self.targets.split("\t") if key.key_blocks.get(n) is not None] if self.targets
                 else _picked(context, key))
        names = [n for n in names if not is_helper(key, n)]
        try:
            if self.mode == 'SELECTION':
                n = len(key.reference_key.data)
                meshes = [o for o in context.selected_objects
                          if o.type == 'MESH' and o != ob and len(o.data.vertices) == n]
                if len(meshes) < 2:
                    self.report({'ERROR'}, "Select two or more target meshes: the last one is the combination")
                    return {'CANCELLED'}
                made = []
                with shape_editor._object_mode(ob):
                    for o in meshes:
                        kb = ob.shape_key_add(name=shape_editor.unique_target_name(key, o.name), from_mix=False)
                        kb.data.foreach_set("co", [c for v in o.data.vertices for c in v.co])
                        kb.value = 0.0
                        made.append(kb.name)
                set_combination(key, made[-1], made[:-1], self.method)
            elif self.mode == 'SET':
                if len(names) < 2:
                    self.report({'ERROR'}, "Select the driver targets, then the combination target last")
                    return {'CANCELLED'}
                set_combination(key, names[-1], names[:-1], self.method)
            else:
                if not names:
                    self.report({'ERROR'}, "Select the targets that drive the combination in the Shape Editor")
                    return {'CANCELLED'}
                with shape_editor._object_mode(ob):
                    kb = ob.shape_key_add(name=shape_editor.add_target_name(key, ob), from_mix=False)
                set_combination(key, kb.name, names, self.method)
                shape_editor.edit_on(context, key, key.key_blocks.find(kb.name))
                context.window_manager.allset_se_current = f"{key.name}/{key.key_blocks.find(kb.name)}"
        except ValueError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        _redraw(context)
        return {'FINISHED'}


class ALLSET_OT_shape_combination_method(bpy.types.Operator):
    """How the driver targets combine into this target's weight (Maya combinationShape Combination Method)"""
    bl_idname = "allset.shape_combination_method"
    bl_label = "Combination Method"
    bl_options = {'UNDO'}

    key: StringProperty(options={'SKIP_SAVE'})
    target: StringProperty(options={'SKIP_SAVE'})
    method: EnumProperty(name="Combination method", items=METHODS, default='MULTIPLY')

    def execute(self, context):
        key = bpy.data.shape_keys.get(self.key)
        item = combinations(key).get(self.target) if key is not None else None
        if item is None:
            return {'CANCELLED'}
        key[COMB][self.target]["method"] = METHOD_IDS.index(self.method)
        rebuild_combination(key, self.target)
        _redraw(context)
        return {'FINISHED'}


classes = (ALLSET_OT_shape_add_inbetween, ALLSET_OT_shape_remove_inbetween, ALLSET_OT_shape_add_combination,
           ALLSET_OT_shape_combination_method)


def register_props():
    bpy.types.WindowManager.allset_se_picked = StringProperty(
        name="Picked targets", description="<blendShape>/<target>\\t<target>... picked in the Shape Editor")
    if _on_depsgraph not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph)


def unregister_props():
    if _on_depsgraph in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph)
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
    _pending.clear()
    if hasattr(bpy.types.WindowManager, "allset_se_picked"):
        del bpy.types.WindowManager.allset_se_picked
