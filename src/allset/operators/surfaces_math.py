# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya NURBS surface maths, bpy-free.

Conventions (Maya's):
- knot lists are Maya lists (no phantom end knots: len = CVs + degree - 1);
- ``Surf.cvs[u][v]`` is u-major like Maya ``.cv[u][v]`` (cvs[i] = the CV row of U index i, running along V);
- periodic directions carry the ``degree`` wrapping CVs (the last ``degree`` CVs repeat the first ones);
- every rule is rotation-free, so it works in any right-handed frame (the tests feed Maya's Y-up numbers, Blender feeds
  its Z-up ones: Maya (X, Y, Z) -> Blender (X, -Z, Y) is a rotation). Revolve takes its axis, Extrude Distance its
  direction, as vectors in the caller's frame.
Outputs are non-rational (Maya's outputs here all have weight 1).
"""

import math
from collections import namedtuple

from . import curves_math as cm

# --- small helpers --------------------------------------------------------------------------------

Crv = namedtuple("Crv", "cvs knots degree periodic")
Crv.__new__.__defaults__ = (False,)

add, sub, mul, dot, cross, norm = cm.add, cm.sub, cm.mul, cm.dot, cm.cross, cm.norm
EPS = 1e-9


def unit(a):
    n = norm(a)
    if n < 1e-15:
        raise ValueError("zero-length vector")
    return mul(a, 1.0 / n)


def _dist(a, b):
    return norm(sub(a, b))


def _mv(M, v):
    return tuple(sum(M[i][j] * v[j] for j in range(3)) for i in range(3))


def _mm(A, B):
    return [[sum(A[i][k] * B[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def _tr(A):
    return [[A[j][i] for j in range(3)] for i in range(3)]


_I3 = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]


def axis_rot(k, th):
    """Right-hand rotation by ``th`` radians about the axis ``k`` (Rodrigues)."""
    k = unit(k)
    K = [[0.0, -k[2], k[1]], [k[2], 0.0, -k[0]], [-k[1], k[0], 0.0]]
    K2 = _mm(K, K)
    s, c = math.sin(th), 1.0 - math.cos(th)
    return [[_I3[i][j] + s * K[i][j] + c * K2[i][j] for j in range(3)] for i in range(3)]


def rot_between(a, b):
    """Minimal rotation taking direction a onto direction b (opposite directions: half turn about any normal)."""
    a, b = unit(a), unit(b)
    v = cross(a, b)
    s = norm(v)
    if s < 1e-12:
        if dot(a, b) > 0:
            return [r[:] for r in _I3]
        helper = (1.0, 0.0, 0.0) if abs(a[0]) < 0.9 else (0.0, 1.0, 0.0)
        return axis_rot(cross(a, helper), math.pi)
    return axis_rot(v, math.atan2(s, dot(a, b)))


def domain(knots, degree):
    """Parameter range of a Maya knot list."""
    return knots[degree - 1], knots[len(knots) - degree]


def greville(knots, degree, n):
    """Greville abscissae of the ``n`` CVs of a Maya knot list."""
    U = cm.full(knots)
    return [sum(U[j + 1:j + degree + 1]) / degree for j in range(n)]


def _basis_row(knots, degree, n, t, der=0):
    """Basis values (or derivative ``der``) of all n CVs at t."""
    U = cm.full(knots)
    i = cm.span(U, degree, t, n)
    d = cm.ders_basis(i, t, degree, U, der)
    row = [0.0] * n
    for j in range(degree + 1):
        row[i - degree + j] = d[der][j]
    return row


def _combine(row, pts):
    out = (0.0, 0.0, 0.0)
    for w, p in zip(row, pts):
        if w:
            out = add(out, mul(p, w))
    return out


def _is_uniform(knots):
    d = [b - a for a, b in zip(knots, knots[1:])]
    return bool(d) and min(d) > 1e-12 and max(d) - min(d) < 1e-7 * max(1.0, abs(knots[-1]))


def _reverse_curve(c):
    a, b = c.knots[0], c.knots[-1]
    return Crv(list(reversed(c.cvs)), [a + b - k for k in reversed(c.knots)], c.degree, c.periodic)


def _crv(c):
    """Anything curve-like (Crv, (cvs, knots, degree[, periodic]) or a JSON dict) -> Crv."""
    if isinstance(c, Crv):
        return Crv([tuple(p) for p in c.cvs], list(c.knots), c.degree, c.periodic)
    if isinstance(c, dict):
        return Crv([tuple(p) for p in c["cvs"]], list(c["knots"]), c["degree"], c.get("form") == "periodic")
    cvs, knots, degree = c[0], c[1], c[2]
    return Crv([tuple(p) for p in cvs], list(knots), degree, bool(c[3]) if len(c) > 3 else False)


def _normalise(knots):
    a, b = knots[0], knots[-1]
    return [(k - a) / (b - a) for k in knots] if b - a > 1e-15 else list(knots)


# --- surface ----------------------------------------------------------------------------------------

class Surf:
    """A non-rational NURBS surface in Maya's conventions (see the module docstring)."""

    __slots__ = ("degree_u", "degree_v", "knots_u", "knots_v", "periodic_u", "periodic_v", "cvs")

    def __init__(self, cvs, knots_u, knots_v, degree_u=3, degree_v=3, periodic_u=False, periodic_v=False):
        self.cvs = [[tuple(p) for p in row] for row in cvs]
        self.knots_u = [float(k) for k in knots_u]
        self.knots_v = [float(k) for k in knots_v]
        self.degree_u, self.degree_v = int(degree_u), int(degree_v)
        self.periodic_u, self.periodic_v = bool(periodic_u), bool(periodic_v)
        nu, nv = len(self.cvs), len(self.cvs[0])
        if len(self.knots_u) != nu + self.degree_u - 1 or len(self.knots_v) != nv + self.degree_v - 1:
            raise ValueError("knot count does not match the CV count (%d x %d, knots %d / %d)"
                             % (nu, nv, len(self.knots_u), len(self.knots_v)))

    def copy(self):
        return Surf(self.cvs, self.knots_u, self.knots_v, self.degree_u, self.degree_v, self.periodic_u,
                    self.periodic_v)

    @property
    def num_cvs(self):
        return len(self.cvs), len(self.cvs[0])

    def domain_u(self):
        return domain(self.knots_u, self.degree_u)

    def domain_v(self):
        return domain(self.knots_v, self.degree_v)

    def point(self, u, v):
        nu, nv = self.num_cvs
        ru = _basis_row(self.knots_u, self.degree_u, nu, u)
        rv = _basis_row(self.knots_v, self.degree_v, nv, v)
        out = (0.0, 0.0, 0.0)
        for i, wu in enumerate(ru):
            if wu:
                out = add(out, mul(_combine(rv, self.cvs[i]), wu))
        return out

    # lines: along U (one per V index) / along V (one per U index)
    def lines_u(self):
        nu, nv = self.num_cvs
        return [[self.cvs[i][j] for i in range(nu)] for j in range(nv)]

    def __repr__(self):
        return "Surf(%dx%d, degree %d/%d, knots_u %s, knots_v %s%s%s)" % (
            len(self.cvs), len(self.cvs[0]), self.degree_u, self.degree_v, self.knots_u, self.knots_v,
            ", periodic u" if self.periodic_u else "", ", periodic v" if self.periodic_v else "")


def _from_lines_u(lines, knots_u, s, degree_u=None, periodic_u=None):
    """lines along U (one per V index) -> Surf with s's V side."""
    cvs = [[lines[j][i] for j in range(len(lines))] for i in range(len(lines[0]))]
    return Surf(cvs, knots_u, s.knots_v, s.degree_u if degree_u is None else degree_u, s.degree_v,
                s.periodic_u if periodic_u is None else periodic_u, s.periodic_v)


def transpose(s):
    """Swap U and V (Maya Reverse Direction "Swap")."""
    nu, nv = s.num_cvs
    cvs = [[s.cvs[i][j] for i in range(nu)] for j in range(nv)]
    return Surf(cvs, s.knots_v, s.knots_u, s.degree_v, s.degree_u, s.periodic_v, s.periodic_u)


# --- curve helpers shared by the commands ------------------------------------------------------------

def project(src, knots, degree):
    """Exact re-representation of curve ``src`` (Crv, already on the target's parameter range) in the spline space
    (knots, degree) that contains it (knot insertion / degree elevation): interpolate at the target's Greville points."""
    n = len(knots) - degree + 1
    g = greville(knots, degree, n)
    A = [_basis_row(knots, degree, n, t) for t in g]
    B = [cm.evaluate(src.cvs, src.knots, src.degree, t) for t in g]
    return cm.solve(A, B)


def _remap(c, a, b):
    """Curve reparameterised linearly onto [a, b] (its knots mapped, CVs unchanged)."""
    c0, c1 = domain(c.knots, c.degree)
    f = (b - a) / (c1 - c0)
    return Crv(c.cvs, [a + (k - c0) * f for k in c.knots], c.degree, c.periodic)


def compatible(curves):
    """Maya loft compatibility: curves that already share degree and knots stay as they are
    (periodic circles stay periodic); otherwise every curve is reparameterised linearly onto the FIRST curve's domain,
    raised to the highest degree and given the union of the interior knots with the maximum multiplicity (a degree-p
    curve's knots gain p_max - p). Returns (knots, degree, [cvs per curve]), shapes unchanged."""
    curves = [_crv(c) for c in curves]
    c0 = curves[0]
    if all(c.degree == c0.degree and len(c.knots) == len(c0.knots)
           and all(abs(x - y) < EPS for x, y in zip(c.knots, c0.knots)) for c in curves):
        return list(c0.knots), c0.degree, [list(c.cvs) for c in curves]
    if any(c.periodic for c in curves):
        # mixed periodic / open curves unknown: periodic ones are opened over their domain first
        curves = [open_periodic_curve(c) if c.periodic else c for c in curves]
        c0 = curves[0]
    p = max(c.degree for c in curves)
    D0, D1 = domain(c0.knots, c0.degree)
    mult = {}
    for c in curves:
        a, b = domain(c.knots, c.degree)
        local = {}
        for k in c.knots:
            if a + EPS < k < b - EPS:
                kk = round(D0 + (k - a) * (D1 - D0) / (b - a), 9)
                local[kk] = local.get(kk, 0) + 1
        for kk, m in local.items():
            mult[kk] = max(mult.get(kk, 0), m + p - c.degree)
    knots = [D0] * p + sorted(k for k, m in mult.items() for _ in range(m)) + [D1] * p
    return knots, p, [project(_remap(c, D0, D1), knots, p) for c in curves]


def open_periodic_curve(c, at=None):
    """Periodic curve -> the same shape as an open (clamped) curve over one period starting at ``at`` (default the
    domain start): the CV list is unrolled over two periods, ``at`` and ``at`` + period are inserted to multiplicity
    = degree (Boehm), the CVs outside are dropped. Also clamps an unclamped open curve (``at`` ignored)."""
    c = _crv(c)
    d = c.degree
    a, b = domain(c.knots, d)
    cvs, knots = list(c.cvs), list(c.knots)
    if c.periodic:
        per = b - a
        t0 = a if at is None else a + ((at - a) % per)
        if t0 > b - EPS:
            t0 = a
        nu = len(cvs) - d
        cvs = cvs[:nu] * 2 + cvs[:d]
        while len(knots) < len(cvs) + d - 1:
            knots.append(knots[len(knots) - nu] + per)
        lo, hi = t0, t0 + per
    else:
        lo, hi = a, b
    for t in (lo, hi):
        times = d - cm.multiplicity(knots, t)
        if times > 0:
            cvs, knots = cm.insert_knot(cvs, knots, d, t, times)
    i0 = min(i for i, k in enumerate(knots) if abs(k - lo) < EPS)
    i1 = max(i for i, k in enumerate(knots) if abs(k - hi) < EPS)
    k_out = knots[i0:i1 + 1]
    return Crv(cvs[i0:i0 + len(k_out) - d + 1], k_out, d, False)


# --- 4.1 Loft ------------------------------------------------------------------------------------------

def _circle_tangent(P0, P1, P2, at=0):
    a, b = sub(P1, P0), sub(P2, P0)
    n = cross(a, b)
    if norm(n) < 1e-12:
        return unit(sub(P2, P0))
    c = add(P0, mul(add(mul(cross(n, a), dot(b, b)), mul(cross(b, n), dot(a, a))), 1.0 / (2 * dot(n, n))))
    return unit(cross(n, sub((P0, P1, P2)[at], c)))


def _lagrange_d0(ts, P):
    """Derivative at ts[0] of the polynomial through P at ts."""
    m = len(P)
    out = (0.0, 0.0, 0.0)
    for i in range(m):
        others = [ts[j] for j in range(m) if j != i]
        den = 1.0
        for o in others:
            den *= ts[i] - o
        dn = 0.0
        for a in range(len(others)):
            pr = 1.0
            for b in range(len(others)):
                if b != a:
                    pr *= ts[0] - others[b]
            dn += pr
        out = add(out, mul(P[i], dn / den))
    return out


def end_direction(P, at_end=False):
    """Loft interpolation end tangent (direction of travel): 3 points = the circle through them, >= 4 points = the
    derivative of the cubic through the first (last) 4 points with chord-length parameters."""
    if len(P) == 3:
        return _circle_tangent(P[0], P[1], P[2], 2 if at_end else 0)
    Q = P[-4:][::-1] if at_end else P[:4]
    ts = [0.0]
    for i in range(1, 4):
        ts.append(ts[-1] + _dist(Q[i], Q[i - 1]))
    d = unit(_lagrange_d0(ts, Q))
    return mul(d, -1.0) if at_end else d


def _interp_open(P, params, knots):
    n = len(P)
    if n == 2:
        return [P[0], cm.lerp(P[0], P[1], 1 / 3.0), cm.lerp(P[0], P[1], 2 / 3.0), P[1]]
    if _dist(P[1], P[0]) < 1e-15 and all(_dist(p, P[0]) < 1e-15 for p in P):
        return [P[0]] * (n + 2)          # a collapsed CV column (all curves share the point)
    d0 = mul(end_direction(P), _dist(P[1], P[0]) / (params[1] - params[0]))
    d1 = mul(end_direction(P, True), _dist(P[-1], P[-2]) / (params[-1] - params[-2]))
    return cm.interpolate(P, params, knots, 3, d0, d1)


def _interp_periodic(P, knots):
    """Periodic uniform cubic through P at v = domain start + k (Maya periodic list), n unique CVs + 3 wrap."""
    n = len(P)
    t0 = knots[2]
    rows = []
    for k in range(n):
        b = _basis_row(knots, 3, n + 3, t0 + k)
        row = [0.0] * n
        for i, w in enumerate(b):
            row[i % n] += w
        rows.append(row)
    c = cm.solve(rows, [tuple(p) for p in P])
    return list(c) + list(c[:3])


def _auto_reverse(curves):
    """Factory Auto reverse [I criterion]: flip a curve whose ends are nearer the previous curve's opposite ends."""
    out = [curves[0]]
    for c in curves[1:]:
        a0, a1 = out[-1].cvs[0], out[-1].cvs[-1]
        b0, b1 = c.cvs[0], c.cvs[-1]
        if _dist(a0, b1) + _dist(a1, b0) < _dist(a0, b0) + _dist(a1, b1):
            c = _reverse_curve(c)
        out.append(c)
    return out


def loft(curves, uniform=True, close=False, degree=3, section_spans=1, auto_reverse=True):
    """Maya Loft. U = the compatible curves, V = across them (curve k = iso v_k)."""
    curves = [_crv(c) for c in curves]
    if len(curves) < 2:
        raise ValueError("loft needs 2 or more curves")
    if auto_reverse:
        curves = _auto_reverse(curves)
    knots_u, p, cc = compatible(curves)
    periodic_u = curves[0].periodic and all(c.periodic for c in curves) and knots_u == list(curves[0].knots)
    n, ncv = len(cc), len(cc[0])
    ss = max(1, int(section_spans))
    if degree == 1:
        if close:       # unknown: the first curve again at the end (closed form)
            cc = cc + [cc[0]]
            n += 1
        chord = [0.0]
        for k in range(1, n):
            chord.append(chord[-1] + sum(_dist(cc[k][i], cc[k - 1][i]) for i in range(ncv)) / ncv)
        kv = []
        for k in range(n - 1):
            for s in range(ss):
                kv.append(chord[k] + (chord[k + 1] - chord[k]) * s / ss)
        kv.append(chord[-1])
        cols = []
        for i in range(ncv):
            col = []
            for k in range(n - 1):
                for s in range(ss):
                    col.append(cm.lerp(cc[k][i], cc[k + 1][i], s / float(ss)))
            col.append(cc[-1][i])
            cols.append(col)
        return Surf(cols, knots_u, kv, p, 1, periodic_u, False)
    if degree != 3:
        raise ValueError("loft degree 1 or 3")
    if uniform:
        params = [float(k) for k in range(n)]
    else:
        params = [0.0]
        for k in range(1, n):
            params.append(params[-1] + sum(_dist(cc[k][i], cc[k - 1][i]) for i in range(ncv)) / ncv)
    if close:
        if n < 3:
            raise ValueError("a closed loft needs 3 or more curves")
        kv = [float(k) for k in range(n + 5)]
        cols = [_interp_periodic([cc[k][i] for k in range(n)], kv) for i in range(ncv)]
        # section spans on a closed loft unknown: ignored
        return Surf(cols, knots_u, kv, p, 3, periodic_u, True)
    kv = [params[0]] * 3 + [params[1]] * 3 if n == 2 else [params[0]] * 2 + params + [params[-1]] * 2
    cols = [_interp_open([cc[k][i] for k in range(n)], params, kv) for i in range(ncv)]
    s = Surf(cols, knots_u, kv, p, 3, periodic_u, False)
    if ss > 1:
        for k in range(n - 1):
            for j in range(1, ss):
                s = insert_knot(s, "V", params[k] + (params[k + 1] - params[k]) * j / ss)
    return s


# --- 4.3 Revolve ----------------------------------------------------------------------------------------

def revolve(profile, axis=(0.0, 1.0, 0.0), pivot=(0.0, 0.0, 0.0), start=0.0, end=360.0, segments=8, degree=3):
    """Maya Revolve. U = the profile, V = around ``axis`` through ``pivot``; the point at sweep
    angle a = the profile point turned by -a about the axis (right-hand rule). Angles in degrees."""
    pr = _crv(profile)
    s = max(1, int(segments))
    k_ax = unit(axis)
    pivot = tuple(pivot)
    sweep = end - start
    if abs(sweep) < 1e-12:
        raise ValueError("revolve sweep is 0")
    full_turn = abs(abs(sweep) - 360.0) < 1e-9
    d = math.radians(sweep) / s
    a0 = math.radians(start)

    def turn(q, a):
        return add(pivot, _mv(axis_rot(k_ax, -a), sub(q, pivot)))

    def foot(q):
        return add(pivot, mul(k_ax, dot(sub(q, pivot), k_ax)))

    rows = []
    if degree == 1:
        for q in pr.cvs:
            rows.append([turn(q, a0 + k * d) for k in range(s + 1)])
        kv = [k * 2.0 * math.sin(abs(d) / 2.0) for k in range(s + 1)]      # chord of a unit circle
        return Surf(rows, pr.knots, kv, pr.degree, 1, pr.periodic, False)
    if degree != 3:
        raise ValueError("revolve degree 1 or 3")
    if full_turn:
        f = 6.0 / (4.0 + 2.0 * math.cos(d))
        for q in pr.cvs:
            fq = foot(q)
            ring = [add(fq, mul(sub(turn(q, a0 + (k - 1) * d), fq), f)) for k in range(s)]
            rows.append(ring + ring[:3])
        kv = [float(i - 2) for i in range(s + 5)]
        return Surf(rows, pr.knots, kv, pr.degree, 3, pr.periodic, True)
    kv = [0.0] * 3 + [float(k) for k in range(1, s)] + [float(s)] * 3
    params = [float(k) for k in range(s + 1)]
    sgn = 1.0 if sweep > 0 else -1.0
    for q in pr.cvs:
        fq = foot(q)
        r = _dist(q, fq)
        pts = [turn(q, a0 + k * d) for k in range(s + 1)]
        if r < 1e-12:
            rows.append([pts[0]] * (s + 3))
            continue
        chord = 2.0 * r * math.sin(abs(d) / 2.0)

        def tangent(a):         # d/da of turn(q, a) = -k x (point - foot), times the sweep direction
            return mul(unit(cross(k_ax, sub(turn(q, a), fq))), -sgn)
        rows.append(cm.interpolate(pts, params, kv, 3, mul(tangent(a0), chord), mul(tangent(a0 + s * d), chord)))
    return Surf(rows, pr.knots, kv, pr.degree, 3, pr.periodic, False)


# --- 4.4 Extrude ----------------------------------------------------------------------------------------

def newell(P):
    """Unit Newell normal of the polygon P (right-hand rule)."""
    n = (0.0, 0.0, 0.0)
    m = len(P)
    for a in range(m):
        p, q = P[a], P[(a + 1) % m]
        n = add(n, ((p[1] - q[1]) * (p[2] + q[2]), (p[2] - q[2]) * (p[0] + q[0]), (p[0] - q[0]) * (p[1] + q[1])))
    return unit(n)


def _unique(c):
    return c.cvs[:len(c.cvs) - c.degree] if c.periodic else c.cvs


def _smallest_axis(P):
    """Unit normal of the least-squares plane through the points P (eigenvector of the smallest eigenvalue of
    their covariance; cyclic Jacobi sweeps on the symmetric 3 x 3 matrix)."""
    m = len(P)
    c = [sum(p[k] for p in P) / m for k in range(3)]
    A = [[sum((p[i] - c[i]) * (p[j] - c[j]) for p in P) for j in range(3)] for i in range(3)]
    V = [[1.0 if i == j else 0.0 for j in range(3)] for i in range(3)]
    for _sweep in range(50):
        off = abs(A[0][1]) + abs(A[0][2]) + abs(A[1][2])
        if off < 1e-30:
            break
        for p, q in ((0, 1), (0, 2), (1, 2)):
            if abs(A[p][q]) < 1e-300:
                continue
            theta = (A[q][q] - A[p][p]) / (2.0 * A[p][q])
            t = (1.0 if theta >= 0 else -1.0) / (abs(theta) + math.sqrt(theta * theta + 1.0))
            cs = 1.0 / math.sqrt(t * t + 1.0)
            sn = t * cs
            for k in range(3):          # A <- J^T A J, V <- V J
                akp, akq = A[k][p], A[k][q]
                A[k][p], A[k][q] = cs * akp - sn * akq, sn * akp + cs * akq
            for k in range(3):
                apk, aqk = A[p][k], A[q][k]
                A[p][k], A[q][k] = cs * apk - sn * aqk, sn * apk + cs * aqk
            for k in range(3):
                vkp, vkq = V[k][p], V[k][q]
                V[k][p], V[k][q] = cs * vkp - sn * vkq, sn * vkp + cs * vkq
    i = min(range(3), key=lambda k: A[k][k])
    return unit((V[0][i], V[1][i], V[2][i]))


def profile_normal(profile):
    """Maya profile normal: the least-squares plane of the CVs (periodic: the unique CVs), turned like the Newell
    normal of the CV polygon (equal for a planar profile); None for a straight profile."""
    P = _unique(_crv(profile))
    try:
        n = newell(P)
    except ValueError:
        return None
    fit = _smallest_axis(P)
    return fit if dot(fit, n) >= 0.0 else mul(fit, -1.0)


def _path_dirs(P):
    out = [unit(sub(P[1], P[0]))]
    for j in range(1, len(P) - 1):
        out.append(unit(add(unit(sub(P[j + 1], P[j])), unit(sub(P[j], P[j - 1])))))
    out.append(unit(sub(P[-1], P[-2])))
    return out


def extrude_tube(profile, path, pivot=(0.0, 0.0, 0.0), at_path=False, component_pivot=False):
    """Maya Extrude, style Tube. U = profile, V = path; every CV ring is a rigid copy of the
    profile CVs carried by the discrete parallel transport of the path CV directions. ``pivot`` = the profile
    transform's world rotate pivot (used At path only). A straight profile (no Newell normal) is not turned onto
    the path. Exact on cubic paths; along a degree-1 path Maya's interior ring directions are not the
    control-polygon bisectors used here (an approximation there). Rotation / Scale are not modelled."""
    pr, pa = _crv(profile), _crv(path)
    P = pa.cvs
    dirs = _path_dirs(P)
    n_prof = profile_normal(pr)
    if n_prof is not None and dot(n_prof, dirs[0]) < 0.0:
        n_prof = mul(n_prof, -1.0)      # like Maya: the profile faces along the path start, whatever its CV order
    R0 = rot_between(n_prof, dirs[0]) if n_prof is not None else [r[:] for r in _I3]
    frames, acc = [], [r[:] for r in _I3]
    for j in range(len(P)):
        if j:
            acc = _mm(rot_between(dirs[j - 1], dirs[j]), acc)
        frames.append(_mm(acc, R0))
    R0t = _tr(R0)
    pivot = tuple(pivot)
    P0 = P[0]       # the profile turns about the path's start point (Maya's closest end point pivot)
    rows = []
    for q in pr.cvs:
        row = []
        for j in range(len(P)):
            if not at_path:
                x = add(P0, _mv(R0t, add(sub(P[j], P0), _mv(frames[j], sub(q, P0)))))
            elif component_pivot:
                x = add(P[j], _mv(frames[j], sub(q, pivot)))
            else:
                x = sub(add(add(P[j], _mv(frames[j], sub(q, P0))), P0), pivot)
            row.append(x)
        rows.append(row)
    return Surf(rows, pr.knots, pa.knots, pr.degree, pa.degree, pr.periodic, pa.periodic)


def extrude_flat(profile, path):
    """Maya Extrude, style Flat: U = path, V = profile (swapped); the profile translated along the path CVs."""
    pr, pa = _crv(profile), _crv(path)
    rows = [[add(q, sub(p, pa.cvs[0])) for q in pr.cvs] for p in pa.cvs]
    return Surf(rows, pa.knots, pr.knots, pa.degree, pr.degree, pa.periodic, pr.periodic)


def extrude_distance(profile, direction=None, length=1.0):
    """Maya Extrude, style Distance: U = profile, V degree 1 (knots 0 1): q and q + unit(direction) * length.
    ``direction`` None = the profile normal (a straight profile then raises ValueError)."""
    pr = _crv(profile)
    if direction is None:
        direction = profile_normal(pr)
        if direction is None:
            raise ValueError("a straight profile has no normal: give a direction")
    off = mul(unit(direction), length)
    rows = [[q, add(q, off)] for q in pr.cvs]
    return Surf(rows, pr.knots, [0.0, 1.0], pr.degree, 1, pr.periodic, False)


# --- 4.5 Birail 1 ------------------------------------------------------------------------------------------

def birail1(profile, rail1, rail2, proportional=True):
    """Maya Birail 1: U = rails (knots normalised 0..1), V = profile (normalised). At each rail Greville
    parameter the profile is mapped by the transform taking (profile start, profile end) onto (rail1 point, rail2
    point): minimal rotation of the chord, scale uniform (proportional) or along the chord only; the CV rows then
    interpolate those mapped profiles. Exact for rails whose chords stay in one plane; twisted rails are an
    approximation. Rails with different knots are made compatible (loft rule) first; periodic rails map their CV
    pairs directly."""
    pr = _crv(profile)
    r1, r2 = _crv(rail1), _crv(rail2)
    knots_u, du, (c1, c2) = compatible([r1, r2])
    Q = pr.cvs
    a0 = Q[0]
    ch0 = sub(Q[-1], a0)
    L0 = norm(ch0)
    if L0 < 1e-12:
        raise ValueError("the profile's ends meet")
    e = mul(ch0, 1.0 / L0)

    def mapped(A, B):
        c = sub(B, A)
        R = rot_between(ch0, c) if norm(c) > 1e-12 else [r[:] for r in _I3]
        k = norm(c) / L0
        row = []
        for q in Q:
            v = sub(q, a0)
            v = mul(v, k) if proportional else add(v, mul(e, dot(v, e) * (k - 1.0)))
            row.append(add(A, _mv(R, v)))
        return row

    periodic_u = r1.periodic and r2.periodic and knots_u == list(r1.knots)
    if r1.periodic or r2.periodic:
        rows = [mapped(A, B) for A, B in zip(c1, c2)]
    else:
        n = len(c1)
        g = greville(knots_u, du, n)
        at = [mapped(cm.evaluate(c1, knots_u, du, t), cm.evaluate(c2, knots_u, du, t)) for t in g]
        M = [_basis_row(knots_u, du, n, t) for t in g]
        cols = [cm.solve(M, [at[j][i] for j in range(n)]) for i in range(len(Q))]
        rows = [[cols[i][j] for i in range(len(Q))] for j in range(n)]
    return Surf(rows, _normalise(knots_u), _normalise(pr.knots), du, pr.degree, periodic_u, pr.periodic)


# --- 4.6 Boundary / Square ------------------------------------------------------------------------------------

def order_boundary(curves):
    """Maya "Automatic" curve ordering: start with curves[0] as drawn, then chain the remaining curves
    head to tail by the nearest end point (reversing a curve whose end is the nearer one)."""
    rest = [_crv(c) for c in curves]
    chain = [rest.pop(0)]
    while rest:
        tail = chain[-1].cvs[-1]
        best = min(((min(_dist(tail, c.cvs[0]), _dist(tail, c.cvs[-1])), i) for i, c in enumerate(rest)))
        c = rest.pop(best[1])
        if _dist(tail, c.cvs[-1]) < _dist(tail, c.cvs[0]):
            c = _reverse_curve(c)
        chain.append(c)
    return chain


def coons(edge_v0, edge_v1, edge_u0, edge_u1, gu, gv):
    """Bilinearly blended Coons patch of four compatible CV nets: edge_v0[i] / edge_v1[i] = the v = 0 / 1 edges (over
    U), edge_u0[j] / edge_u1[j] = the u = 0 / 1 edges (over V); gu / gv = the normalised Greville parameters. Exact:
    the linear blends are reproduced by Greville weights (multi-span sides)."""
    c00, c10, c01, c11 = edge_v0[0], edge_v0[-1], edge_v1[0], edge_v1[-1]
    out = []
    for i, u in enumerate(gu):
        row = []
        for j, v in enumerate(gv):
            p = add(add(mul(edge_v0[i], 1 - v), mul(edge_v1[i], v)), add(mul(edge_u0[j], 1 - u), mul(edge_u1[j], u)))
            b = add(add(mul(c00, (1 - u) * (1 - v)), mul(c10, u * (1 - v))),
                    add(mul(c01, (1 - u) * v), mul(c11, u * v)))
            row.append(sub(p, b))
        out.append(row)
    return out


def _domain(c):
    return c.knots[-1] - c.knots[0]


def boundary(curves, square=False):
    """Maya Boundary / Square (factory, no neighbouring surfaces): 3 or 4 curves head to tail in the order given
    (c1..c4). 4 curves: v = 0 edge = c1, u = 1 edge = c2, v = 1 edge = c3 reversed, u = 0 edge = c4 reversed.
    3 curves: v = 0 edge = c1, v = 1 edge = c2 reversed, u = 0 edge = c3 reversed, u = 1 edge collapsed to the
    c1-end corner. Opposite sides are made compatible (loft rule), CVs = Coons blend. Knot range of a direction =
    the mean of its two sides' domains (0..1 and 0..2 -> 0..1.5); ``square`` (Maya Square) keeps U at 0..1."""
    cs = [_crv(c) for c in curves]
    if any(c.periodic for c in cs):
        raise ValueError("boundary curves must be open")
    if len(cs) == 4:
        sv0, sv1 = cs[0], _reverse_curve(cs[2])
        su0, su1 = _reverse_curve(cs[3]), cs[1]
    elif len(cs) == 3:
        sv0, sv1, su0 = cs[0], _reverse_curve(cs[1]), _reverse_curve(cs[2])
        su1 = None
    else:
        raise ValueError("boundary needs 3 or 4 curves")
    ku, du, (ev0, ev1) = compatible([sv0, sv1])
    ku = _normalise(ku)
    span_u = 1.0 if square else (_domain(sv0) + _domain(sv1)) / 2.0
    if su1 is None:
        kv, dv = _normalise(su0.knots), su0.degree
        span_v = _domain(su0)
        eu0 = list(su0.cvs)
        eu1 = [ev0[-1]] * len(eu0)
    else:
        kv, dv, (eu0, eu1) = compatible([su0, su1])
        kv = _normalise(kv)
        span_v = (_domain(su0) + _domain(su1)) / 2.0
    gu = greville(ku, du, len(ev0))          # Coons blend on the 0..1 parameters
    gv = greville(kv, dv, len(eu0))
    return Surf(coons(ev0, ev1, eu0, eu1, gu, gv), [k * span_u for k in ku], [k * span_v for k in kv], du, dv)


# --- 4.7 Attach --------------------------------------------------------------------------------------------------

def _edges(s):
    """(name, CV line) of the four edges: U start / end run along V, V start / end run along U."""
    nu, nv = s.num_cvs
    return [("U0", list(s.cvs[0])), ("U1", list(s.cvs[-1])),
            ("V0", [s.cvs[i][0] for i in range(nu)]), ("V1", [s.cvs[i][-1] for i in range(nu)])]


def reverse(s, mode="U"):
    """Maya Reverse Direction: "U" (factory) = CV rows reversed, U knots mirrored; "V";
    "BOTH"; "SWAP" = transpose (knots swapped)."""
    mode = mode.upper()
    if mode == "SWAP":
        return transpose(s)
    out = s.copy()
    if mode in ("U", "BOTH"):
        a, b = out.knots_u[0], out.knots_u[-1]
        out.cvs = out.cvs[::-1]
        out.knots_u = [a + b - k for k in reversed(out.knots_u)]
    if mode in ("V", "BOTH"):
        a, b = out.knots_v[0], out.knots_v[-1]
        out.cvs = [row[::-1] for row in out.cvs]
        out.knots_v = [a + b - k for k in reversed(out.knots_v)]
    if mode not in ("U", "V", "BOTH"):
        raise ValueError(mode)
    return out


def _orient(s, edge, to_end):
    """s turned so ``edge`` becomes its U end (to_end) or its U start."""
    if edge[0] == "V":
        s = transpose(s)
    at_end = edge[1] == "1"
    if at_end != to_end:
        s = reverse(s, "U")
    return s


def _join_line(ca, ka, cb, kb, degree, method, bias):
    """The curve Attach (cm.attach) with the ends already chosen: A's end meets B's start."""
    shift = ka[-1] - kb[0]
    if method == "CONNECT":
        return list(ca) + list(cb[1:]), list(ka) + [k + shift for k in kb[degree:]]
    drop_a, drop_b = (degree + 1) // 2, degree // 2 + 1
    blend = add(mul(ca[-1], bias), mul(cb[0], 1.0 - bias))
    return (list(ca[:len(ca) - drop_a]) + [blend] + list(cb[drop_b:]),
            list(ka[:len(ka) - (degree - 1)]) + [k + shift for k in kb[degree:]])


def attach(a, b, method="BLEND", bias=0.5):
    """Maya Attach: the pair of edges (a's vs b's) whose CV lines are nearest (mean CV distance,
    either line direction) joins; copies are turned so a's U end meets b's U start, then the curve rule
    (Blend: bias, joint knot multiplicity 1; Connect: full multiplicity) runs on every CV line along U."""
    best = None
    for ea in _edges(a):
        for eb in _edges(b):
            if len(ea[1]) != len(eb[1]):
                continue
            for flip in (False, True):
                lb = eb[1][::-1] if flip else eb[1]
                dmean = sum(_dist(p, q) for p, q in zip(ea[1], lb)) / len(lb)
                if best is None or dmean < best[0] - 1e-12:
                    best = (dmean, ea[0], eb[0], flip)
    if best is None:
        raise ValueError("no edges with the same CV count")
    _d, e_a, e_b, flip = best
    A = _orient(a, e_a, True)
    B = _orient(b, e_b, False)
    if flip:
        B = reverse(B, "V")
    if A.degree_u != B.degree_u or A.num_cvs[1] != B.num_cvs[1]:
        raise ValueError("surfaces not compatible along the joined edge")
    lines, knots = [], None
    for la, lb in zip(A.lines_u(), B.lines_u()):
        cvs, knots = _join_line(la, A.knots_u, lb, B.knots_u, A.degree_u, method.upper(), bias)
        lines.append(cvs)
    return _from_lines_u(lines, knots, A, periodic_u=False)


# --- 4.8 Insert / Detach / patch ---------------------------------------------------------------------------------

def _along(s, direction):
    """(surface with the given direction as U, undo function)."""
    if direction.upper() == "U":
        return s, lambda x: x
    if direction.upper() == "V":
        return transpose(s), transpose
    raise ValueError(direction)


def open_periodic(s, direction, at=None):
    """A periodic direction re-written as an open (clamped) one over one period starting at ``at`` (default its
    domain start), same shape."""
    t, back = _along(s, direction)
    if not t.periodic_u:
        return s.copy()
    lines, knots = [], None
    for line in t.lines_u():
        c = open_periodic_curve(Crv(line, t.knots_u, t.degree_u, True), at)
        lines.append(c.cvs)
        knots = c.knots
    return back(_from_lines_u(lines, knots, t, periodic_u=False))


def insert_knot(s, direction, t, times=1):
    """Maya Insert Isoparms (Boehm insertion, shape unchanged). A periodic direction is opened first (Maya's
    periodic insert keeps the form)."""
    if times < 1:
        return s.copy()
    w, back = _along(s, direction)
    if w.periodic_u:
        w = open_periodic(w, "U")
    lines, knots = [], None
    for line in w.lines_u():
        cvs, knots = cm.insert_knot(line, w.knots_u, w.degree_u, t, times)
        lines.append(cvs)
    return back(_from_lines_u(lines, knots, w))


def detach(s, direction, t):
    """Maya Detach at the isoparm ``t``: insertion to full multiplicity, split; the pieces keep
    the original parameters. A periodic direction is opened at ``t`` instead: returns (that open surface, None)."""
    w, back = _along(s, direction)
    if w.periodic_u:
        return back(open_periodic(w, "U", t)), None
    firsts, seconds, k1, k2 = [], [], None, None
    for line in w.lines_u():
        (c1, k1), (c2, k2) = cm.split(line, w.knots_u, w.degree_u, t)
        firsts.append(c1)
        seconds.append(c2)
    return back(_from_lines_u(firsts, k1, w)), back(_from_lines_u(seconds, k2, w))


def sub_patch(s, u0, u1, v0, v1):
    """Maya Duplicate NURBS Patches on the patch [u0, u1] x [v0, v1]: detach twice per direction, the original
    parameters kept."""
    out = s
    for direction, a, b in (("U", u0, u1), ("V", v0, v1)):
        w, _back = _along(out, direction)
        if w.periodic_u:
            out = open_periodic(out, direction)
        lo, hi = (out.domain_u() if direction == "U" else out.domain_v())
        if a > lo + EPS:
            out = detach(out, direction, a)[1]
        if b < hi - EPS:
            out = detach(out, direction, b)[0]
    return out


# --- 4.9 Rebuild (Maya algorithm) -----------------------------------------------------------------------------

def rebuild(s, spans_u=4, spans_v=4, degree_u=3, degree_v=3):
    """Maya Rebuild (factory Uniform, 4 x 4 spans, cubic, range 0..1, keep ends) [U algorithm]: per direction, every
    CV line is mapped linearly onto 0..1 and interpolated at the Greville points of the default knots (clamped
    uniform over 0..1, exact). Exact when the new space contains the old one (e.g. 2 -> 4 spans); otherwise
    an approximation (the curve model, equal-arc-length least squares per line, fits worse: per-line arc
    lengths disagree)."""
    out = s
    for direction, spans, deg in (("U", spans_u, degree_u), ("V", spans_v, degree_v)):
        w, _back = _along(out, direction)
        if w.periodic_u:
            out = open_periodic(out, direction)
            w, _back = _along(out, direction)
        deg = max(1, int(deg))
        spans = max(1, int(spans))
        knots = [k / spans for k in cm.clamped_uniform(spans + deg, deg)]
        lines = [project(_remap(Crv(line, w.knots_u, w.degree_u), 0.0, 1.0), knots, deg) for line in w.lines_u()]
        out = _back(_from_lines_u(lines, knots, w, degree_u=deg, periodic_u=False))
    return out


# --- Blender legacy NURBS representation -----------------------------------

def _direction_mode(knots, degree, periodic, n):
    if degree == 1:
        return "CYCLIC" if periodic else "ENDPOINT"
    if periodic and _is_uniform(knots) and n - degree >= degree + 1:
        return "CYCLIC"
    if not periodic and cm.is_clamped_uniform(knots, degree):
        return "ENDPOINT"
    return "BEZIER"


def _bezier_lines(t):
    """U of ``t`` (open or periodic) Boehm-decomposed to Bezier spans: every interior knot at multiplicity degree."""
    if t.periodic_u or not (cm.multiplicity(t.knots_u, t.knots_u[0]) >= t.degree_u
                            and cm.multiplicity(t.knots_u, t.knots_u[-1]) >= t.degree_u):
        t = _open_any(t)
    d = t.degree_u
    a, b = t.domain_u()
    inner = sorted({round(k, 12) for k in t.knots_u if a + EPS < k < b - EPS})
    lines, knots = [], None
    for line in t.lines_u():
        cvs, kn = list(line), list(t.knots_u)
        for u in inner:
            times = d - cm.multiplicity(kn, u)
            if times > 0:
                cvs, kn = cm.insert_knot(cvs, kn, d, u, times)
        lines.append(cvs)
        knots = kn
    return lines, knots


def _open_any(t):
    """U clamped at its domain ends (periodic or unclamped open)."""
    lines, knots = [], None
    for line in t.lines_u():
        c = open_periodic_curve(Crv(line, t.knots_u, t.degree_u, t.periodic_u))
        lines.append(c.cvs)
        knots = c.knots
    return _from_lines_u(lines, knots, t, periodic_u=False)


def _breaks(knots, degree, mode, n):
    """Piecewise-linear map Maya parameter -> Blender parameter: [(maya_t, blender_t), ...] at the breakpoints."""
    a, b = domain(knots, degree)
    k = degree + 1
    if mode == "CYCLIC":
        nu = n - degree
        if degree == 1:
            pts = sorted(set(knots[degree - 1:len(knots) - degree + 1]))
            return [(t, i + 1.0) for i, t in enumerate(pts)] if len(pts) == nu + 1 else [(a, k - 1.0),
                                                                                       (b, k - 1.0 + nu)]
        return [(a, k - 1.0), (b, k - 1.0 + nu)]
    if mode == "ENDPOINT":
        if degree == 1:
            return [(t, float(i)) for i, t in enumerate(knots)]
        spans = n - degree
        return [(a, 0.0), (b, float(spans))]
    pts = sorted({round(x, 12) for x in knots if a - EPS <= x <= b + EPS})
    return [(t, float(i)) for i, t in enumerate(pts)]


def blender_grid(s):
    """Surf -> Blender legacy NURBS surface data (exact geometry):
    rows[j][i] = CV i along u of row j (Blender row j = Maya V index j, ``spline.points[j * nu + i]``), orders,
    cyclic / endpoint / bezier flags per direction, plus map_u / map_v = [(maya_t, blender_t)] breakpoints of the
    piecewise-linear parameter map. Clamped uniform -> endpoint; periodic uniform -> cyclic with the unique CVs only
    (Maya's and Blender's domains both start on CVs 0..degree); degree 1 -> order 2 endpoint (cyclic when periodic);
    anything else -> Boehm decomposition to Bezier spans + bezier + endpoint (non-uniform periodic opened first)."""
    out = {}
    cur = s
    for direction in ("U", "V"):
        t, back = _along(cur, direction)
        n = t.num_cvs[0]
        mode = _direction_mode(t.knots_u, t.degree_u, t.periodic_u, n)
        if mode == "CYCLIC":
            nu = n - t.degree_u
            lines = [line[:nu] for line in t.lines_u()]
            t2 = _from_lines_u(lines, [float(i) for i in range(nu + t.degree_u - 1)], t, periodic_u=False)
            brk = _breaks(t.knots_u, t.degree_u, mode, n)
        elif mode == "ENDPOINT":
            t2 = t
            brk = _breaks(t.knots_u, t.degree_u, mode, n)
        else:
            lines, knots = _bezier_lines(t)
            t2 = _from_lines_u(lines, knots, t, periodic_u=False)
            brk = _breaks(knots, t.degree_u, mode, len(lines[0]))
        cur = back(t2)
        key = direction.lower()
        out["order_" + key] = t.degree_u + 1
        out["cyclic_" + key] = mode == "CYCLIC"
        out["endpoint_" + key] = mode != "CYCLIC"
        out["bezier_" + key] = mode == "BEZIER"
        out["map_" + key] = brk
    nu, nv = cur.num_cvs
    out["rows"] = [[cur.cvs[i][j] for i in range(nu)] for j in range(nv)]
    if out["order_u"] > nu or out["order_v"] > nv:
        raise ValueError("order larger than the CV count")
    return out


def map_param(brk, t):
    """Maya parameter -> Blender parameter through blender_grid's map_u / map_v (clamped to the domain)."""
    if t <= brk[0][0]:
        return brk[0][1]
    for (a, x), (b, y) in zip(brk, brk[1:]):
        if t <= b:
            return min(y, x + (t - a) * (y - x) / (b - a)) if b > a else x
    return brk[-1][1]


def _knots_from_flags(n, order, cyclic, endpoint, bezier):
    d = order - 1
    if cyclic:
        return [float(i - d + 1) for i in range(n + 2 * d - 1)], True   # curves_maya._periodic_knots
    if bezier and endpoint and d > 1 and (n - 1) % d == 0:
        m = (n - 1) // d
        return [float(x) for x in range(m + 1) for _ in range(d)], False
    if endpoint or d == 1:
        return cm.clamped_uniform(n, d), False
    return [float(i) for i in range(1, n + d)], False       # Blender plain uniform (unclamped)


def from_blender_grid(rows, order_u, order_v, cyclic_u=False, cyclic_v=False, endpoint_u=True, endpoint_v=True,
                      bezier_u=False, bezier_v=False):
    """Blender legacy NURBS surface (rows[j][i], flags) -> Surf with Maya knot lists: endpoint = clamped uniform
    0..spans, cyclic = periodic uniform (wrap CVs added), bezier + endpoint = knots of multiplicity degree."""
    nv, nu = len(rows), len(rows[0])
    du, dv = order_u - 1, order_v - 1
    ku, pu = _knots_from_flags(nu, order_u, cyclic_u, endpoint_u, bezier_u)
    kv, pv = _knots_from_flags(nv, order_v, cyclic_v, endpoint_v, bezier_v)
    cvs = [[tuple(rows[j][i]) for j in range(nv)] for i in range(nu)]
    if pv:
        cvs = [row + row[:dv] for row in cvs]
    if pu:
        cvs = cvs + cvs[:du]
    return Surf(cvs, ku, kv, du, dv, pu, pv)


# --- Duplicate Surface Curves --------------------------------------------------------------------

def isoparm(s, direction, t):
    """The isoparm of ``s`` as a curve: direction "U" = Maya ``u[t]`` (runs along V: CV j = column j's U-curve at t,
    knots / degree of V), "V" = ``v[t]`` (runs along U). Exact for non-rational surfaces."""
    nu = len(s.cvs)
    nv = len(s.cvs[0])
    if direction == "U":
        cvs = [cm.evaluate([s.cvs[i][j] for i in range(nu)], s.knots_u, s.degree_u, t) for j in range(nv)]
        return Crv(cvs, list(s.knots_v), s.degree_v, s.periodic_v)
    cvs = [cm.evaluate(list(s.cvs[i]), s.knots_v, s.degree_v, t) for i in range(nu)]
    return Crv(cvs, list(s.knots_u), s.degree_u, s.periodic_u)


def visible_isoparms(s):
    """Maya "Visible surface isoparms" (factory) with the surface selected: every span boundary, ends included, U first."""
    out = []
    for direction, knots, degree in (("U", s.knots_u, s.degree_u), ("V", s.knots_v, s.degree_v)):
        lo, hi = knots[degree - 1], knots[len(knots) - degree]
        for t in sorted({round(k, 12) for k in knots if lo - 1e-12 <= k <= hi + 1e-12}):
            out.append((direction, t))
    return out
