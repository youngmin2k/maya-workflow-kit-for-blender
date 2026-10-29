# SPDX-License-Identifier: GPL-3.0-or-later
"""Temporary Quad Draw display, without changing materials or the user's theme.

The edited mesh shares preselect's geometry cache. A single set of GPU batches is retained,
rebuilt only on geometry/transform changes, and released when Quad Draw ends.
"""
import gpu
from gpu_extras.batch import batch_for_shader

from . import poly_draw, preselect

_shader = None
_cached = None


def clear():
    global _cached
    _cached = None


def shader():
    global _shader
    if _shader is None:
        info = gpu.types.GPUShaderCreateInfo()
        info.vertex_in(0, 'VEC3', 'pos')
        info.push_constant('MAT4', 'mvp')
        info.push_constant('VEC4', 'view_z')
        info.push_constant('VEC4', 'depth_params')
        info.push_constant('VEC4', 'color')
        info.push_constant('BOOL', 'cull_faces')
        info.fragment_out(0, 'VEC4', 'fragColor')
        info.vertex_source('''
            void main() {
                gl_Position = mvp * vec4(pos, 1.0);
                float z = dot(view_z, vec4(pos, 1.0));
                float offset = depth_params.w;
                if (depth_params.z == 0.0) {
                    offset = min(offset, -z * 0.5);
                    gl_Position.z += depth_params.y * offset / (z * (z + offset)) * gl_Position.w;
                } else {
                    gl_Position.z += depth_params.x * offset * gl_Position.w;
                }
                gl_Position.z -= 0.000002 * abs(gl_Position.w);
            }
        ''')
        info.fragment_source('''
            void main() {
                if (cull_faces && !gl_FrontFacing) discard;
                fragColor = color;
            }
        ''')
        _shader = gpu.shader.create_from_info(info)
    return _shader


def batches(context):
    global _cached
    ob = context.edit_object
    c = next((c for candidate, c in preselect.caches(context) if candidate == ob), None)
    if c is None:
        return None
    if _cached is None or _cached[0] is not c:
        sh = shader()
        tris = [tuple(loop.vert.index for loop in tri) for tri in c.bm.calc_loop_triangles()
                if not tri[0].face.hide]
        edges = c.edges[c.eok].astype('int32')
        positions = c.co.astype('float32')
        faces = batch_for_shader(sh, 'TRIS', {'pos': positions}, indices=tris) if tris else None
        wires = batch_for_shader(sh, 'LINES', {'pos': positions}, indices=edges) if len(edges) else None
        # The default 0.01-unit native bias hides coarse quads inside curved references.
        # Scale the temporary display bias with the edited edges, without moving vertices.
        bias = float(((c.co[edges[:, 0]]-c.co[edges[:, 1]])**2).sum(axis=1).max()**.5)*.5 if len(edges) else 0
        _cached = c, faces, wires, bias
    return _cached[1:]


def draw(context):
    from . import quad_draw
    quad_draw.sync_overlays()
    s = poly_draw.settings(context)
    if not s.qd_mesh_color_on and not s.qd_wire_overlay:
        return
    data = batches(context)
    if data is None:
        return
    faces, wires, bias = data
    sh = shader()
    rv = context.region_data
    if rv is None:
        return
    saved = quad_draw.STATE['overlays'].get(context.space_data.as_pointer())
    if saved is not None:
        desired = max(saved[2], bias)
        if abs(context.space_data.overlay.retopology_offset-desired) > 1e-6:
            context.space_data.overlay.retopology_offset = desired
    sh.bind()
    sh.uniform_float('mvp', rv.perspective_matrix)
    sh.uniform_float('view_z', rv.view_matrix[2])
    # Match the native retopology depth prepass, retaining depth occlusion rather than
    # painting through every object. This display bias never changes mesh coordinates.
    p = rv.window_matrix
    sh.uniform_float('depth_params', (p[2][2], p[2][3], p[3][3], context.space_data.overlay.retopology_offset))
    depth, mask, blend = gpu.state.depth_test_get(), gpu.state.depth_mask_get(), gpu.state.blend_get()
    width = gpu.state.line_width_get()
    try:
        gpu.state.depth_test_set('LESS_EQUAL')
        gpu.state.depth_mask_set(False)
        gpu.state.blend_set('ALPHA')
        if faces is not None and s.qd_mesh_color_on and s.qd_mesh_alpha > 0:
            sh.uniform_bool('cull_faces', True)
            sh.uniform_float('color', (*s.qd_mesh_color, s.qd_mesh_alpha))
            faces.draw(sh)
        if wires is not None and s.qd_wire_overlay:
            gpu.state.line_width_set(2.0 * (context.preferences.system.ui_scale or 1.0))
            sh.uniform_bool('cull_faces', False)
            sh.uniform_float('color', (*s.qd_wire_color, 1.0))
            wires.draw(sh)
    finally:
        gpu.state.depth_test_set(depth)
        gpu.state.depth_mask_set(mask)
        gpu.state.blend_set(blend)
        gpu.state.line_width_set(width)
