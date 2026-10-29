# SPDX-License-Identifier: GPL-3.0-or-later
"""Cached, antialiased Quad Draw display; no mesh, material or theme changes."""
import numpy as np
import gpu
from gpu_extras.batch import batch_for_shader

from . import poly_draw, preselect

_shaders = {}
_cached = None
_hover = None
_bias = None
_bytes = 0
_topology = None
_revision = -1
_diagnostics = None
_diagnostic_bytes = 0
_delete_preview=None
_relax_preview=None


def clear():
    global _cached, _hover, _bias, _bytes, _topology, _revision,_delete_preview,_relax_preview
    _cached = _hover = _bias = None
    _bytes = 0
    _topology=None;_revision=-1
    clear_symmetry()
    _delete_preview=_relax_preview=None


def clear_symmetry():
    global _diagnostics,_diagnostic_bytes
    _diagnostics=None;_diagnostic_bytes=0


def buffer_bytes():
    """Retained geometry payload (driver allocation overhead excluded)."""
    extra=(_delete_preview[-1] if _delete_preview else 0)+(_relax_preview[-1] if _relax_preview else 0)
    return _bytes+_diagnostic_bytes+extra


_DEPTH = '''
    vec4 project_point(vec3 p, float bias) {
        vec4 clip = mvp * vec4(p, 1.0);
        float z = dot(view_z, vec4(p, 1.0));
        float offset = max(depth_params.w, bias);
        if (depth_params.z == 0.0) {
            offset = min(offset, max(0.0, -z * 0.5));
            if (abs(z * (z + offset)) > 1e-12)
                clip.z += depth_params.y * offset / (z * (z + offset)) * clip.w;
        } else clip.z += depth_params.x * offset * clip.w;
        clip.z -= 0.000002 * abs(clip.w);
        return clip;
    }
'''


def shader(kind='FACE'):
    if kind in _shaders:
        return _shaders[kind]
    info = gpu.types.GPUShaderCreateInfo()
    info.push_constant('MAT4', 'mvp')
    info.push_constant('VEC4', 'view_z')
    info.push_constant('VEC4', 'depth_params')
    info.push_constant('VEC4', 'color')
    info.vertex_in(0, 'VEC3', 'pos')
    info.vertex_in(1, 'FLOAT', 'bias')
    info.fragment_out(0, 'VEC4', 'fragColor')
    if kind in {'FACE','AREA'}:
        info.push_constant('BOOL', 'cull_faces')
        if kind=='AREA':
            info.vertex_in(2,'FLOAT','weight')
            interface=gpu.types.GPUStageInterfaceInfo('qd_area');interface.smooth('FLOAT','influence');info.vertex_out(interface)
            info.vertex_source(_DEPTH+'void main() { gl_Position = project_point(pos,bias); influence=weight; }')
            info.fragment_source('''void main() {
                if (cull_faces && !gl_FrontFacing) discard;
                float w=clamp(influence,0.0,1.0);
                if (w<=0.0) discard;
                vec3 ramp=w<0.5 ? vec3(w*2.0,0.0,0.0) : vec3(1.0,(w-0.5)*2.0,0.0);
                fragColor=vec4(ramp,w*color.a);
            }''')
        else:
            info.vertex_source(_DEPTH + 'void main() { gl_Position = project_point(pos, bias); }')
            info.fragment_source('''void main() {
            if (cull_faces && !gl_FrontFacing) discard;
            fragColor = color;
        }''')
    else:
        # One aligned vector keeps the complete push block within 128 bytes.
        info.push_constant('VEC4', 'viewport')
        info.vertex_in(2, 'VEC3', 'end')
        info.vertex_in(3, 'VEC2', 'corner')
        interface = gpu.types.GPUStageInterfaceInfo('qd_' + kind.lower())
        interface.no_perspective('VEC2', 'edge_coord')
        interface.flat('FLOAT', 'edge_length')
        info.vertex_out(interface)
        info.vertex_source(_DEPTH + '''void main() {
            float width = viewport.z;
            vec4 a = project_point(pos, bias), b = project_point(end, bias);
            vec2 delta = (b.xy / b.w - a.xy / a.w) * viewport.xy * 0.5;
            float length_px = length(delta);
            vec2 tangent = length_px > 0.001 ? delta / length_px : vec2(1.0, 0.0);
            vec2 normal = vec2(-tangent.y, tangent.x);
            float radius = width * 0.5 + 1.0;
            gl_Position = mix(a, b, corner.x);
            vec2 extension = tangent * mix(-radius, radius, corner.x) + normal * corner.y * radius;
            gl_Position.xy += extension * 2.0 / viewport.xy * gl_Position.w;
            edge_coord = vec2(mix(-radius, length_px + radius, corner.x), corner.y * radius);
            edge_length = length_px;
        }''')
        distance = ('abs(length(edge_coord) - width * 0.34) - width * 0.16'
                    if kind == 'POINT' else
                    'length(vec2(max(max(-edge_coord.x, edge_coord.x-edge_length), 0.0), edge_coord.y)) - width * 0.5')
        info.fragment_source('''void main() {
            float width = viewport.z;
            float d = ''' + distance + ''';
            float coverage = 1.0 - smoothstep(-0.5, 0.5, d);
            if (coverage <= 0.0) discard;
            fragColor = vec4(color.rgb, color.a * coverage);
        }''')
    _shaders[kind] = gpu.shader.create_from_info(info)
    return _shaders[kind]


def _wire(points, edges, bias, kind='WIRE'):
    if not len(edges):
        return None
    # Two triangles per capsule. Expansion happens in pixels in the vertex shader,
    # so orbit/zoom/DPI changes only uniforms, never the retained buffers.
    corners = np.tile(np.array(((0,-1),(1,-1),(1,1),(0,1)), dtype='float32'), (len(edges),1))
    indices = (np.arange(len(edges),dtype='int32')[:,None,None]*4 +
               np.array(((0,1,2),(0,2,3)),dtype='int32')).reshape(-1,3)
    return batch_for_shader(shader(kind), 'TRIS', {
        'pos': np.repeat(points[edges[:,0]],4,axis=0).astype('float32'),
        'end': np.repeat(points[edges[:,1]],4,axis=0).astype('float32'),
        'bias': np.repeat(bias,4).astype('float32'), 'corner': corners}, indices=indices)


def batches(context):
    global _cached, _hover, _bias, _bytes, _topology, _revision
    ob = context.edit_object
    c = next((c for candidate,c in preselect.caches(context) if candidate == ob), None)
    if c is None:
        return None
    changed=_cached is None or _cached[0] is not c
    revision=getattr(c,'revision',0)
    if changed or _revision!=revision:
        positions = c.co.astype('float32')
        edges = c.edges[c.eok].astype('int32')
        face_bias = np.zeros(len(c.bm.faces), dtype='float32')
        vertex_bias = np.zeros(len(c.co), dtype='float32')
        # Coarse faces need clearance above curved references. Local bias prevents
        # one long, unrelated edge from lifting the entire mesh over occluders.
        if changed:
            visible = [f for f in c.bm.faces if not f.hide]
            sizes = np.fromiter((len(f.verts) for f in visible),dtype='int32',count=len(visible))
            face_ids = np.fromiter((f.index for f in visible),dtype='int32',count=len(visible))
            starts = np.r_[0,np.cumsum(sizes)[:-1]] if len(sizes) else np.empty(0,dtype='int32')
            vertex_ids = np.fromiter((v.index for f in visible for v in f.verts),dtype='int32',count=int(sizes.sum()))
            following = np.roll(vertex_ids,-1)
            if len(sizes):following[np.cumsum(sizes)-1] = vertex_ids[starts]
            triangles = c.bm.calc_loop_triangles()
            tri_faces = np.fromiter((tri[0].face.index for tri in triangles),dtype='int32',count=len(triangles))
            ids = np.fromiter((loop.vert.index for tri in triangles for loop in tri),dtype='int32',count=len(triangles)*3).reshape(-1,3)
            _topology=sizes,face_ids,starts,vertex_ids,following,tri_faces,ids
        sizes,face_ids,starts,vertex_ids,following,tri_faces,ids=_topology
        if len(sizes):
            lengths = np.linalg.norm(positions[vertex_ids]-positions[following],axis=1)
            biases = np.maximum.reduceat(lengths,starts)*.5
            face_bias[face_ids] = biases
            np.maximum.at(vertex_bias,vertex_ids,np.repeat(biases,sizes))
        shown = face_bias[tri_faces]>0
        ids = ids[shown].ravel()
        values = np.repeat(face_bias[tri_faces[shown]],3)
        faces = batch_for_shader(shader(), 'TRIS', {'pos': positions[ids], 'bias': values}) if len(ids) else None
        edge_bias = vertex_bias[edges].max(axis=1) if len(edges) else np.empty(0)
        wires = _wire(positions, edges, edge_bias)
        _bytes = len(ids)*16 + len(edges)*(4*36+6*4)
        _bias = vertex_bias, face_bias
        _hover = None
        _cached = c, faces, wires, float(face_bias.max()) if len(face_bias) else 0
        _revision=revision
    return _cached[1:]


def _hover_batches(c, comp):
    global _hover
    key = tuple(comp[:2])
    if _hover is not None and _hover[:2] == (c, key):
        return _hover[2:]
    kind, i = key
    points = c.co
    faces = wires = marker = None
    if kind == 'VERT':
        marker = _wire(points, np.array(((i,i),),dtype='int32'), [_bias[0][i]], 'POINT')
    elif kind == 'EDGE':
        e = c.edges[i:i+1]
        wires = _wire(points,e,[_bias[0][e].max()])
    else:
        f = c.bm.faces[i]
        ids = [v.index for v in f.verts]
        e = np.array(list(zip(ids,ids[1:]+ids[:1])),dtype='int32')
        wires = _wire(points,e,[_bias[1][i]]*len(e))
        from mathutils import Vector
        from mathutils.geometry import tessellate_polygon
        tris = [points[ids[j]] for tri in tessellate_polygon([[Vector(points[j]) for j in ids]]) for j in tri]
        faces = batch_for_shader(shader(), 'TRIS', {'pos': np.asarray(tris,dtype='float32'), 'bias': np.full(len(tris),_bias[1][i],dtype='float32')})
    _hover = c,key,faces,wires,marker
    return faces,wires,marker


def _bind(context, kind, color, width=1.8, cull=False):
    from . import quad_draw
    sh = shader(kind)
    rv = context.region_data
    sh.bind()
    sh.uniform_float('mvp',rv.perspective_matrix)
    sh.uniform_float('view_z',rv.view_matrix[2])
    p = rv.window_matrix
    saved = quad_draw.STATE['overlays'].get(context.space_data.as_pointer())
    offset = saved[2] if saved is not None else context.space_data.overlay.retopology_offset
    sh.uniform_float('depth_params',(p[2][2],p[2][3],p[3][3],offset))
    sh.uniform_float('color',color)
    if kind in {'FACE','AREA'}:
        sh.uniform_bool('cull_faces',cull)
    else:
        sh.uniform_float('viewport',(context.region.width,context.region.height,
                                    max(2.0,width*(context.preferences.system.ui_scale or 1)),0))
    return sh


def _draw_symmetry(context,c):
    """Draw cached seam/counterpart strokes after the base wire, with the same depth clearance."""
    global _diagnostics,_diagnostic_bytes
    from . import quad_draw
    sym=context.scene.allset_symmetry;info=quad_draw.STATE.get('topology_info')
    if not sym.on or sym.about!='TOPOLOGY' or not info or info['object']!=c.name:return
    if _diagnostics is None or _diagnostics[0] is not c or _diagnostics[1] is not info or _diagnostics[7]!=_revision:
        edges=np.asarray(info.get('seam_ids',()),dtype='int32').reshape(-1,2)
        seam=_wire(c.co,edges,_bias[0][edges].max(axis=1)) if len(edges) else None
        _diagnostics=[c,info,seam,None,None,0,len(edges)*168,_revision]
    comp=quad_draw.STATE.get('hover_component') if quad_draw.STATE.get('topology_hover') else None
    key=tuple(comp) if comp else None
    if _diagnostics[3]!=key:
        _diagnostics[3]=key;_diagnostics[4]=None;_diagnostics[5]=0
        if comp and comp[0]==c.name:
            kind,i=comp[1:];pairs=info['pairs']
            ids=[i] if kind=='VERT' else [v.index for v in (c.bm.edges[i].verts if kind=='EDGE' else c.bm.faces[i].verts)]
            if all(i in pairs for i in ids):
                ids=[pairs[i] for i in ids]
                edges=np.asarray([(ids[0],ids[0])] if kind=='VERT' else list(zip(ids,ids[1:]+ids[:1])) if kind=='FACE' else [ids],dtype='int32')
                _diagnostics[4]=_wire(c.co,edges,_bias[0][edges].max(axis=1),'POINT' if kind=='VERT' else 'WIRE')
                _diagnostics[5]=len(edges)*168
    _diagnostic_bytes=_diagnostics[6]+_diagnostics[5]
    if _diagnostics[2] is not None:_diagnostics[2].draw(_bind(context,'WIRE',(1,.75,.12,1),2.2))
    if _diagnostics[4] is not None:
        point=comp[1]=='VERT';_diagnostics[4].draw(_bind(context,'POINT' if point else 'WIRE',(.15,1,.4,1),8 if point else 2.2))


def _draw_delete_loop(context,c):
    global _delete_preview
    from . import quad_draw as q
    data=q.STATE.get('delete_edges');pv=q.STATE.get('preview')
    if not pv or pv[0]!='DELETE_LOOP' or not data or data[0]!=c.name:
        _delete_preview=None;return
    sym=context.scene.allset_symmetry;info=q.STATE.get('topology_info')
    key=(c,c.revision,data[1],sym.on,sym.about,sym.axis,id(info))
    if _delete_preview is None or _delete_preview[0]!=key:
        edges=c.edges[list(data[1])];points=c.co[edges].reshape(-1,3)
        bias=_bias[0][edges].max(axis=1)
        if sym.on and sym.about!='TOPOLOGY':
            ob=context.edit_object
            matrix=np.asarray(ob.matrix_world@q.quad_draw_symmetry.reflection(ob,sym.about,'XYZ'.index(sym.axis))@ob.matrix_world.inverted_safe())
            points=np.concatenate((points,points@matrix[:3,:3].T+matrix[:3,3]));bias=np.tile(bias,2)
        elif sym.on and info:
            pairs=info['pairs'];mirrored=np.asarray([(pairs[a],pairs[b]) for a,b in edges if a in pairs and b in pairs],dtype='int32').reshape(-1,2)
            if len(mirrored):points=np.concatenate((points,c.co[mirrored].reshape(-1,3)));bias=np.r_[bias,_bias[0][mirrored].max(axis=1)]
        segments=np.arange(len(points),dtype='int32').reshape(-1,2)
        _delete_preview=key,_wire(points,segments,bias),len(segments)*168
    if _delete_preview[1] is not None:_delete_preview[1].draw(_bind(context,'WIRE',(1,.055,.035,1),2.2))


def _draw_relax_area(context,c):
    global _relax_preview
    from . import quad_draw as q
    area=q.STATE.get('relax_area')
    if not context.scene.allset_soft_select or not area or area['cache'] is not c:
        _relax_preview=None;return
    weights=area['weights'];key=(c,c.revision,id(weights))
    if _relax_preview is None or _relax_preview[0]!=key:
        ids=_topology[6];faces=_topology[5]
        mask=(weights[ids]>0).any(axis=1);triangles=ids[mask].ravel()
        batch=None
        if len(triangles):
            bias=np.repeat(_bias[1][faces[mask]],3)
            batch=batch_for_shader(shader('AREA'),'TRIS',{'pos':c.co[triangles].astype('float32'),'bias':bias.astype('float32'),'weight':weights[triangles].astype('float32')})
        _relax_preview=key,weights,batch,weights.nbytes+len(triangles)*20
    if _relax_preview[2] is not None:_relax_preview[2].draw(_bind(context,'AREA',(1,1,1,.9),cull=True))


def draw(context):
    from . import quad_draw
    quad_draw.sync_overlays(context)
    if context.region_data is None:
        return
    s = poly_draw.settings(context)
    data = batches(context)
    if data is None:
        return
    faces,wires,_ = data
    depth,mask,blend = gpu.state.depth_test_get(),gpu.state.depth_mask_get(),gpu.state.blend_get()
    try:
        gpu.state.depth_test_set('LESS_EQUAL')
        gpu.state.depth_mask_set(False)
        gpu.state.blend_set('ALPHA')
        if faces is not None and s.qd_mesh_color_on and s.qd_mesh_alpha > 0:
            faces.draw(_bind(context,'FACE',(*s.qd_mesh_color,s.qd_mesh_alpha),cull=True))
        _draw_relax_area(context,_cached[0])
    finally:
        gpu.state.depth_test_set(depth)
        gpu.state.depth_mask_set(mask)
        gpu.state.blend_set(blend)


def draw_front(context):
    """POST_PIXEL follows native edit wires; retain depth-tested world projection.

    Native retopology wires otherwise paint intermittent cyan over our strokes
    near curved references. No global theme/overlay visibility changes are needed.
    """
    from . import quad_draw
    if _cached is None or context.region_data is None:
        return
    pv = quad_draw.STATE['preview']
    comp = quad_draw.STATE.get('hover_component')
    depth,mask,blend = gpu.state.depth_test_get(),gpu.state.depth_mask_get(),gpu.state.blend_get()
    try:
        gpu.state.depth_test_set('LESS_EQUAL')
        gpu.state.depth_mask_set(False)
        gpu.state.blend_set('ALPHA')
        s = poly_draw.settings(context)
        wires = _cached[2]
        if wires is not None and s.qd_wire_overlay:
            wires.draw(_bind(context,'WIRE',(*s.qd_wire_color,1)))
        _draw_delete_loop(context,_cached[0])
        _draw_symmetry(context,_cached[0])
        if not pv or pv[0] != 'HOVER' or not comp:
            return
        if context.edit_object is None or comp[0] != context.edit_object.name:
            return
        face,wire,point = _hover_batches(_cached[0],comp[1:])
        if face is not None:
            face.draw(_bind(context,'FACE',(1,1,1,.17),cull=True))
        if wire is not None:
            wire.draw(_bind(context,'WIRE',(1,.055,.035,1),1.8))
        if point is not None:
            point.draw(_bind(context,'POINT',(1,.055,.035,1),8))
    finally:
        gpu.state.depth_test_set(depth)
        gpu.state.depth_mask_set(mask)
        gpu.state.blend_set(blend)
