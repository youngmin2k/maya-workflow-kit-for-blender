# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya ikRPsolver on chains of 3+ bones (#181): how Maya splits the bend over the in-between joints.

No bpy: plain maths on numpy arrays (column vectors), so the rule can be tested headless.

Maya 2026's rule, in the order it runs:
1. The degrees of freedom are the rotate X / Y / Z (radians, each joint's own rotate order) of every joint from the start
   joint to the last-but-one joint. The chain starts at its preferred angles ("rest"). Distances are taken from the start
   joint (reach² = |end − start|²).
2. Every objective is divided by N = the largest squared bone length of the chain (the translates of the joints after
   the start joint).
3. Near table: a BFGS run (below) shrinks reach² from the rest; after each line search that lowered the objective the
   state is recorded (an entry whose reach² is within tol·E of the last one replaces it; E = max(chain length², rest
   reach²)). First step length min(n / 57, π / n).
4. Reach estimate: E := 2·(tol + E); a BFGS run that pushes reach² up to E (objective max(0, E − reach²)) from the rest;
   when it gets within tol of E (or past it) E := 2·max(E, reach²) and again, else E := the reach² it got to.
5. Far table: one BFGS run toward the point 1.5·√(E / rest reach²) × the rest end offset (objective |end − point|²),
   first step n / 57; its final state is the one far entry.
6. Solve for the goal distance r² (at least tol²·E): inside the rest reach the near table, else the far table (rest,
   far entry). Beyond the last entry: its state. Else a bracketed Newton search along the straight line between the two
   entries around r² (secant start, Newton with a one-third guard, halving where the line's reach² doesn't grow), until
   reach² is within tol·(far reach²) of r².
7. Root: the start joint's own rotation from the table state is dropped (back to its preferred angle). The whole chain
   then turns about the start joint: first the shortest turn that points the end at the goal, then about that line so
   the chain's plane normal (from the rest pose: the in-between joint with the largest |p × d|; a straight chain: the
   world axis of d's smallest component made perpendicular to d) lines up with pole vector × goal direction, plus twist.

BFGS: identity start Hessian, the standard inverse update, restart (H = I) when s·y ≤ 0 or the objective drops by
≤ tol / 80, at most min(20, n) restarts and 150 iterations; it stops at f < tol, |g| < √tol / 10 or a slope near zero.
Line search: two phases with ρ = σ = 0.01, extrapolation up to 9 × the last step, sectioning inside [0.1, 0.5] of the
bracket, cubic interpolation, a minimum step of 1e-6 in angle space. tol = 1e-5.
"""

import math

import numpy as np

TOL = 1e-5
RHO = SIGMA = 0.01
EXTRAPOLATE = 9.0
SECTION_LO, SECTION_HI = 0.1, 0.5
MIN_STEP = 1e-6
MAX_ITER = 150
ORDERS = ("xyz", "yzx", "zxy", "xzy", "yxz", "zyx")      # Maya rotateOrder 0 .. 5
_AXIS = {"x": 0, "y": 1, "z": 2}


def axis_rotation(axis, angle):
    """Column-vector rotation by ``angle`` (radians, right-handed) about basis axis 0 / 1 / 2."""
    c, s = math.cos(angle), math.sin(angle)
    if axis == 0:
        return np.array(((1.0, 0.0, 0.0), (0.0, c, -s), (0.0, s, c)))
    if axis == 1:
        return np.array(((c, 0.0, s), (0.0, 1.0, 0.0), (-s, 0.0, c)))
    return np.array(((c, -s, 0.0), (s, c, 0.0), (0.0, 0.0, 1.0)))


def euler_matrix(angles, order=0):
    """Column-vector matrix of Maya rotate (radians) in rotate order ``order``: the first axis of the order turns
    first."""
    m = np.eye(3)
    for ch in ORDERS[order]:
        k = _AXIS[ch]
        m = axis_rotation(k, angles[k]) @ m
    return m


def euler_from_matrix(m, order=0):
    """Maya rotate (radians) of a column-vector rotation matrix for rotate order ``order``."""
    i, j, k = (_AXIS[c] for c in ORDERS[order])
    sign = 1.0 if (j - i) % 3 == 1 else -1.0       # an even permutation of x y z
    # m = R_k(c) R_j(b) R_i(a)
    sb = -sign * m[k, i]
    sb = max(-1.0, min(1.0, sb))
    b = math.asin(sb)
    if abs(sb) < 1.0 - 1e-12:
        a = math.atan2(sign * m[k, j], m[k, k])
        c = math.atan2(sign * m[j, i], m[i, i])
    else:
        a = math.atan2(-sign * m[j, k], m[j, j])
        c = 0.0
    out = [0.0, 0.0, 0.0]
    out[i], out[j], out[k] = a, b, c
    return out


def _cross_matrix(k):
    return np.array(((0.0, -k[2], k[1]), (k[2], 0.0, -k[0]), (-k[1], k[0], 0.0)))


def rotation_about(axis, angle):
    k = np.asarray(axis, float)
    k = k / np.linalg.norm(k)
    kk = _cross_matrix(k)
    return np.eye(3) + math.sin(angle) * kk + (1.0 - math.cos(angle)) * kk @ kk


def rotation_between(a, b):
    """The shortest rotation taking direction ``a`` to direction ``b``."""
    a = np.asarray(a, float) / np.linalg.norm(a)
    b = np.asarray(b, float) / np.linalg.norm(b)
    v = np.cross(a, b)
    s = float(np.linalg.norm(v))
    if s < 1e-15:
        return np.eye(3)
    return rotation_about(v / s, math.atan2(s, float(a @ b)))


class Chain:
    """A Maya joint chain, column vectors. ``parent`` = the start joint's parent rotation, ``origin`` = the start joint's
    position, ``orients`` = jointOrient matrices (column, one per joint, the end joint's too), ``offsets`` = each joint's
    translate in its parent joint's frame (the first is unused), ``orders`` = rotate orders, ``preferred`` = preferred
    angles (radians, one triple per joint)."""

    def __init__(self, parent, origin, orients, offsets, orders, preferred):
        self.parent = np.asarray(parent, float)
        self.origin = np.asarray(origin, float)
        self.orients = [np.asarray(m, float) for m in orients]
        self.offsets = [np.asarray(t, float) for t in offsets]
        self.orders = list(orders)
        self.joints = len(self.orients)
        self.rest = np.concatenate([np.asarray(preferred[i], float) for i in range(self.joints - 1)])
        self.n = len(self.rest)

    def frames(self, x):
        """(positions (J, 3), joint frames [3x3]) for DOF vector ``x``."""
        pos = [self.origin]
        frames = []
        w = self.parent
        for i in range(self.joints):
            if i > 0:
                pos.append(pos[-1] + frames[-1] @ self.offsets[i])
            rot = euler_matrix(x[3 * i:3 * i + 3], self.orders[i]) if i < self.joints - 1 else np.eye(3)
            w = (frames[-1] if frames else self.parent) @ self.orients[i] @ rot
            frames.append(w)
        return np.array(pos), frames

    def axes(self, x):
        """(positions, [(DOF index, world axis, pivot joint)]) for the analytic gradient."""
        pos = [self.origin]
        out = []
        prev = self.parent
        for i in range(self.joints - 1):
            if i > 0:
                pos.append(pos[-1] + prev @ self.offsets[i])
            base = prev @ self.orients[i]
            order = ORDERS[self.orders[i]]
            # the rotation is R_last ... R_first: an axis turns by every rotation applied after it
            after = np.eye(3)
            mats = {}
            for ch in reversed(order):
                k = _AXIS[ch]
                mats[k] = base @ after
                after = after @ axis_rotation(k, x[3 * i + k])
            for k in range(3):
                out.append((3 * i + k, mats[k][:, k], i))
            prev = base @ euler_matrix(x[3 * i:3 * i + 3], self.orders[i])
        pos.append(pos[-1] + prev @ self.offsets[-1])
        return np.array(pos), out

    def reach2(self, x):
        p, _f = self.frames(x)
        d = p[-1] - p[0]
        return float(d @ d)

    def reach2_grad(self, x):
        p, axes = self.axes(x)
        d = p[-1] - p[0]
        g = np.zeros(self.n)
        for k, axis, j in axes:
            g[k] = 2.0 * float(d @ np.cross(axis, p[-1] - p[j]))
        return float(d @ d), g

    def goal_grad(self, x, goal):
        """|end − start − goal|² and its gradient (``goal`` relative to the start joint)."""
        p, axes = self.axes(x)
        d = p[-1] - p[0] - goal
        g = np.zeros(self.n)
        for k, axis, j in axes:
            g[k] = 2.0 * float(d @ np.cross(axis, p[-1] - p[j]))
        return float(d @ d), g


# --- BFGS with a two-phase line search ----------------------------------------------------------------------------

def _cubic_min(fa, fb, h, ga, gb):
    """Minimiser offset (from a, over an interval of length h) of the cubic through two values and slopes; −1 when it
    has none."""
    if h == 0.0:
        return 0.0
    z = (fa - fb) / h
    w1 = ga + gb + 2.0 * z
    w2 = w1 + z + ga
    disc = w2 * w2 - 3.0 * w1 * ga
    if disc >= 0.0:
        s = math.sqrt(disc)
        if w2 < s - 1e-10:
            return h * ga / (w2 - s)
    return -1.0


def line_search(fun, x, d, f0, slope0, first_len):
    """Step along ``d`` from ``x``: (alpha, f, g) with f < f0, or (0, f0, None)."""
    nd = float(np.linalg.norm(d))
    amin = MIN_STEP / nd
    bound = ((0.0 - f0) / RHO) / slope0
    alpha = min(first_len / nd, bound * 0.25)

    def at(a):
        f, g = fun(x + a * d)
        return f, float(g @ d), g
    prev = (0.0, f0, slope0)
    last = None
    lo_pt = hi_pt = None
    while True:                                             # bracketing
        fa, sa, ga = at(alpha)
        last = (alpha, fa, ga)
        if fa <= 0.0:
            return _result(last, f0)
        if fa > f0 + RHO * alpha * slope0 or prev[1] <= fa:
            lo_pt, hi_pt = prev, (alpha, fa, sa)
            break
        if abs(sa) <= -SIGMA * slope0:
            return _result(last, f0)
        if sa >= 0.0:
            lo_pt, hi_pt = (alpha, fa, sa), prev
            break
        if abs(alpha - bound) <= 1e-10:
            return _result(last, f0)
        lo = 2.0 * alpha - prev[0]
        if lo < bound:
            hi = min(bound, (alpha - prev[0]) * EXTRAPOLATE + alpha)
            c = _cubic_min(prev[1], fa, alpha - prev[0], prev[2], sa) + prev[0]
            nxt = min(c, hi) if lo <= c else lo
        else:
            nxt = bound
        prev = (alpha, fa, sa)
        alpha = nxt
    while True:                                             # sectioning
        (a, fa_, sa_), (b, fb, sb) = lo_pt, hi_pt
        span = b - a
        if abs(span) < amin:
            break
        lo, hi = span * SECTION_LO + a, b - span * SECTION_HI
        if b <= a:
            c = _cubic_min(fb, fa_, a - b, sb, sa_) + b
            alpha = hi if c < hi else min(c, lo)
        else:
            c = _cubic_min(fa_, fb, span, sa_, sb) + a
            alpha = lo if c < lo else min(c, hi)
        f, s, g = at(alpha)
        last = (alpha, f, g)
        if f > f0 + RHO * alpha * slope0 or (fa_ <= f and f != fa_):
            hi_pt = (alpha, f, s)
        else:
            if s <= 0.0 and -s <= -SIGMA * slope0:
                break
            if span * s >= 0.0:
                hi_pt = lo_pt
            lo_pt = (alpha, f, s)
    return _result(last, f0)


def _result(last, f0):
    alpha, f, g = last
    return (alpha, f, g) if f < f0 else (0.0, f0, None)


def bfgs(fun, x0, first_len, record=None, ftarget=TOL):
    """Minimise ``fun`` (returns f, gradient) from ``x0``; ``record(x)`` after every step that lowered f. Returns x."""
    n = len(x0)
    x = np.array(x0, float)
    f, g = fun(x)
    if f < ftarget:
        return x
    h = np.eye(n)
    d = -g
    restarts, f_restart = 0, f
    restart_limit = min(20, n)
    small = ftarget / 80.0
    kt = math.sqrt(ftarget) / 10.0
    for _it in range(MAX_ITER + 1):
        if np.linalg.norm(g) < kt:
            break
        nd = float(np.linalg.norm(d))
        slope = float(g @ d)
        if slope / nd >= -kt * f / math.sqrt(n):
            alpha, fn, gn = 0.0, f, None
        else:
            alpha, fn, gn = line_search(fun, x, d, f, slope, first_len)
        drop = f - fn
        if drop > 0.0 and record is not None:
            record(x + alpha * d)
        if fn < ftarget:
            return x + alpha * d
        if drop <= small or gn is None:
            if drop > 0.0:
                x, f, g = x + alpha * d, fn, gn
            restarts += 1
            if restarts > restart_limit or f_restart - f < small:
                break
            f_restart, h, d = f, np.eye(n), -g
            continue
        s = alpha * d
        y = gn - g
        sy = float(s @ y)
        x, f, g = x + s, fn, gn
        if sy <= 0.0:
            restarts += 1
            if restarts > restart_limit or f_restart - f < small:
                break
            f_restart, h, d = f, np.eye(n), -g
            continue
        hy = h @ y
        h = h + ((1.0 + float(y @ hy) / sy) / sy) * np.outer(s, s) - (np.outer(s, hy) + np.outer(hy, s)) / sy
        d = -h @ g
    return x


# --- tables, solve, root ------------------------------------------------------------------------------------------

class Solver:
    """Maya's precalculated tables for one chain (rebuilt when the chain's bones, orients or preferred angles change)."""

    def __init__(self, chain):
        self.chain = chain
        c = chain
        x0 = c.rest
        p0, _f = c.frames(x0)
        self.rest_pos = p0
        bones = [float(np.sum((p0[i + 1] - p0[i]) ** 2)) for i in range(len(p0) - 1)]
        self.norm = max(max(bones), 1e-12)     # every joint after the start joint: its translate = one bone
        rest_r2 = c.reach2(x0)
        length = sum(math.sqrt(b) for b in bones)
        e = max(length * length, rest_r2)
        norm = self.norm

        def near_fun(x):
            f, g = c.reach2_grad(x)
            return f / norm, g / norm
        self.near = [(x0.copy(), rest_r2)]

        def record(x):
            r2 = c.reach2(x)
            if len(self.near) > 1 and abs(r2 - self.near[-1][1]) <= TOL * e:
                self.near[-1] = (x.copy(), r2)
            else:
                self.near.append((x.copy(), r2))
        n = c.n
        bfgs(near_fun, x0, min(n / 57.0, math.pi / n), record)
        e = 2.0 * (TOL + e)
        for _ in range(40):
            def far_fun(x, e=e):
                f, g = c.reach2_grad(x)
                v = e - f
                return (v, -g) if v >= 0.0 else (0.0, np.zeros_like(g))
            r2 = c.reach2(bfgs(far_fun, x0, n / 57.0))
            if e - r2 < TOL or e <= r2:
                e = 2.0 * max(e, r2)
                continue
            e = r2
            break
        point = 1.5 * math.sqrt(e / rest_r2) * (p0[-1] - p0[0]) if rest_r2 > 0.0 else p0[-1] - p0[0]

        def goal_fun(x):
            f, g = c.goal_grad(x, point)
            return f / norm, g / norm
        xg = bfgs(goal_fun, x0, n / 57.0)
        self.far = [(x0.copy(), rest_r2), (xg, c.reach2(xg))]
        self.e = max(e, self.far[-1][1])
        start = _f[0]           # the start joint's frame at rest: the straight-chain fallback is taken in it
        self.normal = start @ chain_normal([start.T @ (q - p0[0]) for q in p0])

    def state(self, r2):
        """DOF vector whose reach² is ``r2`` (Maya's table + bracketed Newton search)."""
        c = self.chain
        r2 = max(r2, TOL * self.e * TOL)
        far_r2 = self.far[-1][1]
        tol = TOL * far_r2
        rest = self.near[0]
        if c.n < 4 or far_r2 <= self.near[-1][1]:
            return rest[0].copy()
        if r2 <= rest[1]:
            ent = self.near[1:]
            if not ent or ent[-1][1] >= r2:
                return (ent[-1] if ent else rest)[0].copy()
            k = next(i for i in range(len(ent)) if ent[i][1] < r2)
            x_lo, v_lo = ent[k]
            x_hi, v_hi = ent[k - 1] if k > 0 else rest
        else:
            ent = self.far[1:]
            if ent[-1][1] < r2:
                return ent[-1][0].copy()
            k = next(i for i in range(len(ent)) if ent[i][1] >= r2)
            x_hi, v_hi = ent[k]
            x_lo, v_lo = ent[k - 1] if k > 0 else rest
        lo, hi, t, secant, x = 0.0, 1.0, 0.0, True, None
        for it in range(100):
            if abs(v_hi - v_lo) <= tol:
                if it == 0:
                    x = 0.5 * (x_hi + x_lo)
                break
            if secant:
                t = (hi - lo) * (r2 - v_lo) / (v_hi - v_lo) + lo
            x = t * x_hi + (1.0 - t) * x_lo
            f, g = c.reach2_grad(x)
            fd = f - r2
            if abs(fd) <= tol:
                break
            der = float((x_hi - x_lo) @ g)
            if der <= 0.0:
                if fd > 0.0:
                    v_hi = f
                    t, hi = 0.5 * (t + lo), t
                elif fd < 0.0:
                    v_lo = f
                    t, lo = 0.5 * (t + hi), t
                secant = False
                continue
            tn = t - fd / der
            if fd <= 0.0 or (2.0 * lo + t) / 3.0 < tn:
                if fd < 0.0 and (2.0 * hi + t) / 3.0 <= tn:
                    v_lo, lo, secant = f, t, True
                    continue
                t, secant = tn, False
                continue
            v_hi, hi, secant = f, t, True
        return x

    def solve(self, goal, pole, twist=0.0):
        """(DOF vector with the start joint at its preferred angle, root turn 3x3, joint positions) for ``goal``
        (a position) and pole vector ``pole`` (a direction), both in the chain's space; ``twist`` in radians."""
        c = self.chain
        goal = np.asarray(goal, float)
        r2 = float(np.sum((goal - c.origin) ** 2))
        x = self.state(r2)
        x[:3] = c.rest[:3]
        p, _f = c.frames(x)
        u = goal - c.origin
        if float(u @ u) < 1e-24:
            return x, np.eye(3), p
        u = u / np.linalg.norm(u)
        turn = rotation_between(p[-1] - p[0], u)
        n = turn @ self.normal
        n = n - u * float(n @ u)
        ref = np.cross(np.asarray(pole, float), u)
        if np.linalg.norm(n) > 1e-12 and np.linalg.norm(ref) > 1e-12:
            n = n / np.linalg.norm(n)
            ref = ref / np.linalg.norm(ref)
            angle = math.atan2(float(np.cross(n, ref) @ u), float(n @ ref))
        else:
            angle = 0.0
        turn = rotation_about(u, angle + twist) @ turn
        return x, turn, np.array([c.origin + turn @ (q - c.origin) for q in p])


def chain_normal(points):
    """The chain plane's normal at rest: p × d of the in-between joint with the largest |p × d|² (a joint replaces
    the current best only when larger by 1e-10; the first needs 1e-10); a straight chain: |d|²·e_k − d_k·d with k the
    axis of d's smallest component."""
    points = [np.asarray(q, float) for q in points]
    r = points[0]
    d = points[-1] - r
    best, best2 = None, 1e-10
    for q in points[1:-1]:
        c = np.cross(q - r, d)
        c2 = float(c @ c)
        if c2 >= best2 + (1e-10 if best is not None else 0.0):
            best, best2 = c, c2
    if best is not None:
        return best
    k = int(np.argmin(np.abs(d)))
    e = np.zeros(3)
    e[k] = 1.0
    return float(d @ d) * e - d[k] * d


def chain_from_maya(wm, jo, ro, pa):
    """A Chain from Maya joint data: world matrices (16 values, row-vector layout) at rest, jointOrient / preferred
    angles in degrees, rotate orders."""
    mats = [np.array(m, float).reshape(4, 4) for m in wm]
    rot = [m[:3, :3] for m in mats]
    pos = [m[3, :3] for m in mats]
    orients = [euler_matrix(np.radians(j), 0) for j in jo]
    offsets = [np.zeros(3)] + [rot[i - 1] @ (pos[i] - pos[i - 1]) for i in range(1, len(mats))]
    preferred = [np.radians(p) for p in pa]
    return Chain(np.eye(3), pos[0], orients, offsets, ro, preferred)
