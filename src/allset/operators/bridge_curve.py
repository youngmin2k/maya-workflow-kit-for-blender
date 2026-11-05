# SPDX-License-Identifier: GPL-3.0-or-later
"""Bridge path evaluation, scalar ramps and explicit editable NURBS paths."""

import hashlib
import json
import math

import bpy
from mathutils import Matrix, Quaternion, Vector

from . import curves_math

RAMP_DEFAULT = '[[0.0,1.0,1],[1.0,1.0,1]]'
REFERENCE = 'allset_bridge_path_'
_dirty = set()
_updating = False


def reference_key(name):
    return REFERENCE+hashlib.blake2s(name.encode('utf-8'), digest_size=12).hexdigest()


def ramp_points(text):
    points = json.loads(text or RAMP_DEFAULT)
    if not isinstance(points, list) or not 1 <= len(points) <= 256:
        raise ValueError('A taper ramp requires between 1 and 256 points')
    result = []
    for point in points:
        if (not isinstance(point, (list, tuple)) or len(point) != 3
                or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in point)
                or not 0 <= point[0] <= 1 or point[1] < 0 or point[2] not in (0, 1, 2, 3)):
            raise ValueError('Invalid taper ramp position, value or interpolation')
        result.append((float(point[0]), float(point[1]), int(point[2])))
    return sorted(result, key=lambda point: point[0])


def ramp_value(points, t):
    if t <= points[0][0]:
        return points[0][1]
    if t >= points[-1][0]:
        return points[-1][1]
    for index in range(len(points)-1):
        x0, y0, mode = points[index]
        x1, y1, _next_mode = points[index+1]
        if t >= x1 or x1 <= x0:
            continue
        u = (t-x0)/(x1-x0)
        if mode == 0:
            return y0
        if mode == 1:
            return y0+(y1-y0)*u
        if mode == 2:
            return y0+(y1-y0)*u*u*(3-2*u)
        previous = points[max(0, index-1)]
        following = points[min(len(points)-1, index+2)]
        left = (y1-previous[1])/(x1-previous[0])*(x1-x0) if x1 > previous[0] else 0
        right = (following[1]-y0)/(following[0]-x0)*(x1-x0) if following[0] > x0 else 0
        return max(0, (2*u**3-3*u*u+1)*y0+(u**3-2*u*u+u)*left
                   +(-2*u**3+3*u*u)*y1+(u**3-u*u)*right)
    return points[-1][1]


def path_point(a, b, start, end, t):
    """Quintic endpoint interpolation, with zero endpoint acceleration."""
    return (a*(1-10*t**3+15*t**4-6*t**5)+b*(10*t**3-15*t**4+6*t**5)
            +start*(t-6*t**3+8*t**4-3*t**5)+end*(-4*t**3+7*t**4-3*t**5))


def directions(source, params):
    chord = source['b']-source['a']
    start, end = source['start'].copy(), source['end'].copy()
    if params.get('direction', 0):
        if params.get('source_direction', 0):
            start.negate()
        if params.get('target_direction', 0):
            end.negate()
    else:
        if start.dot(chord) < 0:
            start.negate()
        if end.dot(chord) < 0:
            end.negate()
    return start, end


def curve_object(ob, params):
    name = params.get('input_curve', '')
    curve = ob.data.get(reference_key(name)) or bpy.data.objects.get(name)
    if curve is None or curve.type != 'CURVE' or not curve.data.splines:
        raise ValueError('Choose an existing curve or create a Bridge path')
    return curve


def path_evaluator(ob, source, params):
    a, b = source['a'], source['b']
    start, end = directions(source, params)
    if params.get('curve_type', 0) == 0:
        return lambda t: a.lerp(b, t)
    if params.get('curve_type') == 2:
        from .curves_maya import read_spline
        curve = curve_object(ob, params)
        data = read_spline(curve.data.splines[0], ob.matrix_world.inverted() @ curve.matrix_world)
        lo, hi = data.knots[0], data.knots[-1]
        def evaluate(t):
            return Vector(curves_math.evaluate(data.cvs, data.knots, data.degree,
                                              lo+(hi-lo)*t, data.weights))
        first, last = evaluate(0), evaluate(1)
        return lambda t: evaluate(t)+(a-first)*(1-t)+(b-last)*t
    return lambda t: path_point(a, b, start, end, t)


def taper_value(taper, t):
    """A symmetric middle section with smooth tangent transitions at the peak."""
    u = 2*min(t, 1-t)
    delta = taper-1
    slope = max(-3*abs(delta), min(3*abs(delta), taper*taper-1))
    return ((2*u**3-3*u*u+1)+(u**3-2*u*u+u)*slope
            +(-2*u**3+3*u*u)*taper)


def deform(vertices, source, params, ob=None):
    if hasattr(vertices, 'ensure_lookup_table'):
        vertices.ensure_lookup_table()
    smooth = bool(params.get('curve_type', 0))
    path = path_evaluator(ob, source, params)
    start, end = directions(source, params)
    ramp = ramp_points(params.get('taper_curve', RAMP_DEFAULT))
    divisions = len(source['rows'])+1
    for t, row in source['rows']:
        centre = path(t)
        axis = path(min(1, t+1/divisions))-path(max(0, t-1/divisions))
        if axis.length_squared < 1e-16:
            axis = source['b']-source['a']
        axis.normalize()
        reference = start.lerp(end, t).normalized()
        rotation = reference.rotation_difference(axis) if reference.length_squared else axis.to_track_quat('Z','Y')
        blend = math.sin(math.pi*t)**1.5 if smooth else 0
        scale = taper_value(float(params.get('taper', 1)), t)*ramp_value(ramp, t) if smooth else 1
        twist = Quaternion(axis, math.radians(float(params.get('twist_angle', 0)))*math.sin(math.pi*t))
        for index, a, b in row:
            offset = (a-source['a']).lerp(b-source['b'], t)
            offset = offset.lerp(rotation @ offset, blend)
            if smooth:
                offset = twist @ offset
            vertices[index].co = centre+offset*scale


def prepare(context, ob, record, params):
    """Create the explicit path inside the caller's normal undoable command."""
    if params.get('curve_type') != 2:
        return params
    if params.get('input_curve'):
        curve = curve_object(ob, params)
        ob.data[reference_key(params['input_curve'])] = curve
        return params
    from . import model_history, poly_attribute_nodes
    import bmesh
    temporary = None
    if record is not None and record.pre is not None:
        bm = record.pre
    elif record is not None:
        temporary = model_history.input_mesh(ob, record.history_id)
        bm = temporary
    else:
        bm = bmesh.from_edit_mesh(ob.data)
    try:
        source = poly_attribute_nodes.path_source(bm, params)
        if source is None:
            raise ValueError('Select two compatible Bridge borders')
        start, end = directions(source, params)
        a, b = source['a'], source['b']
        cvs = [a, a+start/5, a+start*2/5, b-end*2/5, b-end/5, b]
        from .curves_maya import MCurve, _new_curve_object
        data = MCurve([tuple(point) for point in cvs], curves_math.clamped_uniform(6, 5), 5)
        curve = _new_curve_object(context, ob.name+'_BridgeCurve', [data], select=False)
        curve.parent = ob
        curve.matrix_basis = Matrix.Identity(4)
        values = dict(params, input_curve=curve.name)
        ob.data[reference_key(curve.name)] = curve
        return values
    finally:
        if temporary is not None:
            temporary.free()


def cleanup(ob, previous, params):
    if previous.get('input_curve') or not params.get('input_curve'):
        return
    key = reference_key(params['input_curve'])
    curve = ob.data.get(key)
    if key in ob.data:
        del ob.data[key]
    if curve is not None and curve.parent == ob:
        data = curve.data
        bpy.data.objects.remove(curve, do_unlink=True)
        if data.users == 0:
            bpy.data.curves.remove(data)


@bpy.app.handlers.persistent
def changed(_scene, depsgraph):
    if _updating:
        return
    for update in depsgraph.updates:
        data = update.id.original
        if isinstance(data, bpy.types.Curve):
            _dirty.add(data.session_uid)
        elif isinstance(data, bpy.types.Object) and data.type == 'CURVE':
            _dirty.add(data.data.session_uid)


def refresh():
    global _updating
    if not _dirty or _updating:
        return .1
    from . import extrude, model_history
    _updating = True
    changed_curves = set(_dirty)
    _dirty.clear()
    try:
        for ob in tuple(bpy.data.objects):
            data = model_history.read(ob)
            if data is None or model_history.ensure(ob) is None:
                continue
            for node in data['nodes']:
                if node['kind'] != 'BRIDGE' or node['params'].get('curve_type') != 2:
                    continue
                try:
                    curve = curve_object(ob, node['params'])
                    if curve.data.session_uid not in changed_curves:
                        continue
                    record = extrude.RECORDS.get(ob.name)
                    if record is not None and node['id'] == record.history_id:
                        extrude.preview(ob, record, dict(record.params), node['unit'])
                        if record.fast_preview:
                            extrude.capture_preview(ob, record)
                        record.live = False
                    else:
                        model_history.edit(ob, node['id'], node['params'])
                except (ValueError, ReferenceError, RuntimeError):
                    continue
    finally:
        _updating = False
    return .1


@bpy.app.handlers.persistent
def save(_dummy=None):
    refresh()


@bpy.app.handlers.persistent
def clear(_dummy=None):
    _dirty.clear()


def register():
    if changed not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(changed)
    if not bpy.app.timers.is_registered(refresh):
        bpy.app.timers.register(refresh, first_interval=.1, persistent=True)
    bpy.app.handlers.save_pre.append(save)
    bpy.app.handlers.load_pre.append(clear)


def unregister():
    _dirty.clear()
    if changed in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(changed)
    if bpy.app.timers.is_registered(refresh):
        bpy.app.timers.unregister(refresh)
    for handlers, callback in ((bpy.app.handlers.save_pre, save), (bpy.app.handlers.load_pre, clear)):
        if callback in handlers:
            handlers.remove(callback)
