# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya 2022 NURBS curve maths, bpy-free.

A curve here = (cvs, knots, degree[, weights]); ``cvs`` are 3-tuples, ``knots`` are Maya's knot list (no phantom end
knots: len = len(cvs) + degree - 1). Coordinates are whatever the caller uses (the tests feed Maya's Y-up numbers,
Blender feeds its Z-up ones: every rule here is rotation-free except the two-point arc normal, which is passed in).
"""

import math

# --- small vector helpers --------------------------------------------------------------------------


def add(a, b):
    return tuple(x + y for x, y in zip(a, b))


def sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def mul(a, s):
    return tuple(x * s for x in a)


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def norm(a):
    return math.sqrt(dot(a, a))


def unit(a):
    n = norm(a)
    return mul(a, 1.0 / n) if n > 1e-15 else a


def lerp(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


# --- knots / evaluation -------------------------------------------------------------------------------

def full(knots):
    """Maya knots -> the full knot vector (phantom first / last knot added)."""
    return [knots[0]] + list(knots) + [knots[-1]]


def maya(full_knots):
    return list(full_knots[1:-1])


def clamped_uniform(n_cvs, degree):
    """Maya's knots of an open uniform curve: 0 (degree times), 1 .. spans - 1, spans (degree times)."""
    spans = n_cvs - degree
    return [0.0] * degree + [float(i) for i in range(1, spans)] + [float(spans)] * degree


def is_clamped_uniform(knots, degree):
    k = list(knots)
    if len(k) < 2 * degree:
        return False
    a, b = k[0], k[-1]
    if any(abs(x - a) > 1e-9 for x in k[:degree]) or any(abs(x - b) > 1e-9 for x in k[-degree:]):
        return False
    inner = [a] + k[degree:len(k) - degree] + [b]
    if len(inner) < 2:
        return False
    step = (b - a) / (len(inner) - 1)
    return step > 1e-12 and all(abs(inner[i] - (a + step * i)) < 1e-7 * max(1.0, abs(b)) for i in range(len(inner)))


def span(U, p, u, n):
    """Index i with U[i] <= u < U[i+1] (n = number of CVs)."""
    if u >= U[n]:
        return n - 1
    if u <= U[p]:
        return p
    lo, hi = p, n
    mid = (lo + hi) // 2
    while u < U[mid] or u >= U[mid + 1]:
        if u < U[mid]:
            hi = mid
        else:
            lo = mid
        mid = (lo + hi) // 2
    return mid


def ders_basis(i, u, p, U, nd):
    """Basis functions and their derivatives up to ``nd`` at u (Piegl & Tiller A2.3)."""
    ndu = [[0.0] * (p + 1) for _ in range(p + 1)]
    ndu[0][0] = 1.0
    left = [0.0] * (p + 1)
    right = [0.0] * (p + 1)
    for j in range(1, p + 1):
        left[j] = u - U[i + 1 - j]
        right[j] = U[i + j] - u
        saved = 0.0
        for r in range(j):
            ndu[j][r] = right[r + 1] + left[j - r]
            temp = ndu[r][j - 1] / ndu[j][r] if ndu[j][r] else 0.0
            ndu[r][j] = saved + right[r + 1] * temp
            saved = left[j - r] * temp
        ndu[j][j] = saved
    ders = [[0.0] * (p + 1) for _ in range(nd + 1)]
    for j in range(p + 1):
        ders[0][j] = ndu[j][p]
    for r in range(p + 1):
        s1, s2 = 0, 1
        a = [[0.0] * (p + 1) for _ in range(2)]
        a[0][0] = 1.0
        for k in range(1, nd + 1):
            d = 0.0
            rk, pk = r - k, p - k
            if r >= k:
                a[s2][0] = a[s1][0] / ndu[pk + 1][rk] if ndu[pk + 1][rk] else 0.0
                d = a[s2][0] * ndu[rk][pk]
            j1 = 1 if rk >= -1 else -rk
            j2 = k - 1 if r - 1 <= pk else p - r
            for j in range(j1, j2 + 1):
                a[s2][j] = (a[s1][j] - a[s1][j - 1]) / ndu[pk + 1][rk + j] if ndu[pk + 1][rk + j] else 0.0
                d += a[s2][j] * ndu[rk + j][pk]
            if r <= pk:
                a[s2][k] = -a[s1][k - 1] / ndu[pk + 1][r] if ndu[pk + 1][r] else 0.0
                d += a[s2][k] * ndu[r][pk]
            ders[k][r] = d
            s1, s2 = s2, s1
    r = p
    for k in range(1, nd + 1):
        for j in range(p + 1):
            ders[k][j] *= r
        r *= (p - k)
    return ders


def evaluate(cvs, knots, degree, u, weights=None, deriv=0):
    """Point (deriv 0) or derivative of the curve at Maya parameter u (rational with ``weights``)."""
    U = full(knots)
    n = len(cvs)
    i = span(U, degree, u, n)
    nd = deriv if weights is None else max(deriv, 0)
    ders = ders_basis(i, u, degree, U, nd)
    if weights is None:
        out = (0.0, 0.0, 0.0)
        for j in range(degree + 1):
            out = add(out, mul(cvs[i - degree + j], ders[deriv][j]))
        return out
    if deriv:
        raise ValueError("rational derivatives not needed")
    w = 0.0
    out = (0.0, 0.0, 0.0)
    for j in range(degree + 1):
        k = i - degree + j
        out = add(out, mul(cvs[k], ders[0][j] * weights[k]))
        w += ders[0][j] * weights[k]
    return mul(out, 1.0 / w)


def samples(cvs, knots, degree, count=50, weights=None):
    a, b = knots[0], knots[-1]
    return [evaluate(cvs, knots, degree, a + (b - a) * i / (count - 1), weights) for i in range(count)]


# --- linear solve -----------------------------------------------------------------------------------

def solve(A, B):
    """Gauss-Jordan with partial pivoting; B is a list of 3-vectors (one right-hand side per row)."""
    n = len(A)
    M = [list(A[r]) + list(B[r]) for r in range(n)]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(M[r][c]))
        M[c], M[piv] = M[piv], M[c]
        pv = M[c][c]
        if abs(pv) < 1e-14:
            raise ValueError("singular system")
        M[c] = [x / pv for x in M[c]]
        for r in range(n):
            if r != c and M[r][c]:
                f = M[r][c]
                M[r] = [x - f * y for x, y in zip(M[r], M[c])]
    return [tuple(M[r][n:]) for r in range(n)]


def _row(U, p, n, u, d):
    i = span(U, p, u, n)
    ders = ders_basis(i, u, p, U, d)
    row = [0.0] * n
    for j in range(p + 1):
        row[i - p + j] = ders[d][j]
    return row


def interpolate(points, params, knots, degree=3, d0=None, d1=None):
    """CVs of the cubic through ``points`` at ``params`` with ``knots``; end conditions = given first derivatives
    (d0, d1) or natural (second derivative 0) — Maya's EP Curve Tool."""
    U = full(knots)
    n = len(points) + 2
    A, B = [], []
    for pnt, u in zip(points, params):
        A.append(_row(U, degree, n, u, 0))
        B.append(tuple(pnt))
    a, b = params[0], params[-1]
    A.append(_row(U, degree, n, a, 1 if d0 is not None else 2))
    B.append(tuple(d0) if d0 is not None else (0.0, 0.0, 0.0))
    A.append(_row(U, degree, n, b, 1 if d1 is not None else 2))
    B.append(tuple(d1) if d1 is not None else (0.0, 0.0, 0.0))
    return solve(A, B)


# --- CV / EP curves, arcs ---------------------------------------------------------------------------

def cv_curve(points, degree=3):
    degree = max(1, min(degree, len(points) - 1))
    return [tuple(p) for p in points], clamped_uniform(len(points), degree), degree


def ep_curve(points, degree=3, uniform=True):
    """Maya EP Curve Tool (default: degree 3, knot spacing Uniform): the curve passes through the points at
    u = 0 .. n-1 (Uniform) or at cumulative chord lengths (Chord length), natural ends."""
    pts = [tuple(p) for p in points]
    if degree == 1 or len(pts) < 3:
        return pts, clamped_uniform(len(pts), 1) if len(pts) >= 2 else [0.0], 1
    if uniform:
        params = [float(i) for i in range(len(pts))]
    else:
        params = [0.0]
        for a, b in zip(pts, pts[1:]):
            params.append(params[-1] + norm(sub(b, a)))
    knots = [params[0]] * 3 + params[1:-1] + [params[-1]] * 3
    return interpolate(pts, params, knots, 3), knots, 3


def _arc_curve(centre, start, axis, sweep, radius, sections=8, degree=3):
    """Maya circular arc node output: edit points on the circle at equal angles, clamped uniform knots
    0 .. sections, end derivatives = tangent x chord."""
    sections = max(4, int(sections))
    u = unit(sub(start, centre))
    v = cross(axis, u)

    def at(t):
        return add(centre, add(mul(u, radius * math.cos(t)), mul(v, radius * math.sin(t))))

    eps = [at(sweep * k / sections) for k in range(sections + 1)]
    if degree == 1:     # a polyline through the arc points, knots = cumulative chord lengths
        knots = [0.0]
        for a, b in zip(eps, eps[1:]):
            knots.append(knots[-1] + norm(sub(b, a)))
        return eps, knots, 1
    chord = 2.0 * radius * math.sin(abs(sweep) / (2 * sections))
    sgn = 1.0 if sweep >= 0 else -1.0

    def tangent(t):
        return unit(mul(add(mul(u, -math.sin(t)), mul(v, math.cos(t))), sgn))

    params = [float(k) for k in range(sections + 1)]
    knots = [0.0] * 3 + params[1:-1] + [float(sections)] * 3
    cvs = interpolate(eps, params, knots, 3, mul(tangent(0.0), chord), mul(tangent(sweep), chord))
    return cvs, knots, 3


def arc3(p1, p2, p3, sections=8, degree=3):
    """Maya Three Point Circular Arc: the circle through the three points, from p1 through p2 to p3."""
    a, b = sub(p2, p1), sub(p3, p1)
    n = cross(a, b)
    if norm(n) < 1e-12:
        return cv_curve([p1, p3], 1)
    nn = dot(n, n)
    centre = add(p1, mul(add(mul(cross(n, a), dot(b, b)), mul(cross(b, n), dot(a, a))), 1.0 / (2 * nn)))
    axis = unit(n)
    radius = norm(sub(p1, centre))
    u, w = unit(sub(p1, centre)), unit(sub(p3, centre))
    sweep = math.atan2(dot(cross(u, w), axis), dot(u, w))
    if sweep <= 0:
        sweep += 2 * math.pi
    return _arc_curve(centre, p1, axis, sweep, radius, sections, degree)


def arc2(p1, p2, normal=(0.0, 0.0, 1.0), radius=None, toggle=False, sections=8, degree=3):
    """Maya Two Point Circular Arc: radius (default half the chord) about ``normal``; the centre on the n x d side,
    the short arc unless ``toggle``."""
    d = sub(p2, p1)
    c = norm(d)
    r = c / 2.0 if radius is None else max(radius, c / 2.0)
    side = unit(cross(normal, unit(d)))
    h = math.sqrt(max(r * r - c * c / 4.0, 0.0))
    centre = add(mul(add(p1, p2), 0.5), mul(side, h))
    # the circle lies in the plane of d and n x d (not necessarily normal to n); the short arc bulges to -(n x d)
    axis = unit(cross(unit(d), side))
    u, w = unit(sub(p1, centre)), unit(sub(p2, centre))
    sweep = math.atan2(dot(cross(u, w), axis), dot(u, w))
    if sweep <= 1e-12:
        sweep += 2 * math.pi
    if toggle:
        sweep -= 2 * math.pi
    return _arc_curve(centre, p1, axis, sweep, r, sections, degree)


# --- knot insertion / split / Bezier --------------------------------------------------------------

def insert_knot(cvs, knots, degree, u, times=1, weights=None):
    """Boehm insertion of u (homogeneous when weighted). Returns (cvs, knots[, weights])."""
    P = [(*mul(c, w), w) for c, w in zip(cvs, weights)] if weights else [(*c, 1.0) for c in cvs]
    U = full(knots)
    p = degree
    for _ in range(times):
        n = len(P)
        k = span(U, p, u, n)
        Q = []
        for i in range(n + 1):
            if i <= k - p:
                Q.append(P[i])
            elif i > k:
                Q.append(P[i - 1])
            else:
                den = U[i + p] - U[i]
                a = (u - U[i]) / den if den else 0.0
                Q.append(tuple(x * (1 - a) + y * a for x, y in zip(P[i - 1], P[i])))
        P = Q
        U = U[:k + 1] + [u] + U[k + 1:]
    if weights:
        return [mul(q[:3], 1.0 / q[3]) for q in P], maya(U), [q[3] for q in P]
    return [q[:3] for q in P], maya(U)


def multiplicity(knots, u):
    return sum(1 for k in knots if abs(k - u) < 1e-9)


def split(cvs, knots, degree, u):
    """Maya Detach at u: insert u up to multiplicity = degree, then cut. Pieces keep their parameters."""
    times = degree - multiplicity(knots, u)
    if times > 0:
        cvs, knots = insert_knot(cvs, knots, degree, u, times)
    idx = max(i for i, k in enumerate(knots) if abs(k - u) < 1e-9)
    # CV on the curve at u = cvs[idx - degree + 1]
    cut = idx - degree + 1
    a = (cvs[:cut + 1], [k for k in knots if k <= u + 1e-9])
    b = (cvs[cut:], [k for k in knots if k >= u - 1e-9])
    return a, b


def to_bezier(cvs, knots, degree=3):
    """Cubic B-spline -> list of Bezier segments (4 points each), exact."""
    if degree != 3:
        raise ValueError("cubic only")
    inner = sorted({k for k in knots[3:-3]})
    for u in inner:
        times = 3 - multiplicity(knots, u)
        if times > 0:
            cvs, knots = insert_knot(cvs, knots, 3, u, times)
    return [cvs[i:i + 4] for i in range(0, len(cvs) - 1, 3)]


# --- Rebuild (a model of Maya's Rebuild, not its exact algorithm) --------------------------

def arc_length_points(cvs, knots, degree, count, weights=None, dense=400):
    a, b = knots[0], knots[-1]
    pts = [evaluate(cvs, knots, degree, a + (b - a) * i / dense, weights) for i in range(dense + 1)]
    acc = [0.0]
    for p, q in zip(pts, pts[1:]):
        acc.append(acc[-1] + norm(sub(q, p)))
    total = acc[-1]
    out = []
    j = 0
    for i in range(count):
        s = total * i / (count - 1)
        while j < dense - 1 and acc[j + 1] < s:
            j += 1
        seg = acc[j + 1] - acc[j]
        t = (s - acc[j]) / seg if seg else 0.0
        out.append(lerp(pts[j], pts[j + 1], t))
    return out, total


def rebuild(cvs, knots, degree, spans=4, new_degree=3, weights=None):
    """Maya Rebuild (default Uniform, 4 spans, degree 3, range 0-1, keep ends): least-squares fit of a clamped uniform
    curve to equal-arc-length points with the end points fixed and the end legs kept on the original end tangents."""
    p = new_degree
    n = spans + p
    knots_out = [k / spans for k in clamped_uniform(n, p)]
    m = max(8 * spans + 1, 40)
    pts, _ = arc_length_points(cvs, knots, degree, m, weights)
    params = [i / (m - 1) for i in range(m)]
    a, b = knots[0], knots[-1]
    t0 = unit(evaluate(cvs, knots, degree, a, deriv=1)) if weights is None else unit(sub(cvs[1], cvs[0]))
    t1 = unit(evaluate(cvs, knots, degree, b, deriv=1)) if weights is None else unit(sub(cvs[-1], cvs[-2]))
    P0, Pn = tuple(cvs[0]), tuple(cvs[-1])
    U = full(knots_out)
    if p == 1 or n <= 4:
        # degree 1 / a single cubic span: fixed ends, the rest least squares
        free = list(range(1, n - 1))
        fixed_end_legs = False
    else:
        free = list(range(2, n - 2))
        fixed_end_legs = True
    rows = [_row(U, p, n, u, 0) for u in params]
    # unknowns: the interior CVs (3 coordinates each) + the two end-leg lengths (normal equations, small)
    nf = len(free)
    N = 3 * nf + (2 if fixed_end_legs else 0)
    M = [[0.0] * N for _ in range(N)]
    R = [0.0] * N
    for row, q in zip(rows, pts):
        base = mul(P0, row[0])
        base = add(base, mul(Pn, row[n - 1]))
        if fixed_end_legs:
            base = add(base, mul(P0, row[1]))
            base = add(base, mul(Pn, row[n - 2]))
        r = sub(q, base)
        for c in range(3):
            coef = [0.0] * N
            for j, idx in enumerate(free):
                coef[3 * j + c] = row[idx]
            if fixed_end_legs:
                coef[3 * nf] = row[1] * t0[c]
                coef[3 * nf + 1] = -row[n - 2] * t1[c]
            for x in range(N):
                if coef[x]:
                    R[x] += coef[x] * r[c]
                    for y in range(N):
                        if coef[y]:
                            M[x][y] += coef[x] * coef[y]
    sol = solve(M, [(v, 0.0, 0.0) for v in R])
    sol = [s[0] for s in sol]
    out = [None] * n
    out[0], out[-1] = P0, Pn
    for j, idx in enumerate(free):
        out[idx] = tuple(sol[3 * j:3 * j + 3])
    if fixed_end_legs:
        out[1] = add(P0, mul(t0, sol[3 * nf]))
        out[n - 2] = sub(Pn, mul(t1, sol[3 * nf + 1]))
    return out, knots_out, p


# --- Attach / Fillet / Straighten / Move Seam ------------------------------------------------------

def reverse(cvs, knots, weights=None):
    a, b = knots[0], knots[-1]
    out = (list(reversed(cvs)), [a + b - k for k in reversed(knots)])
    return out + ((list(reversed(weights)),) if weights else ())


def attach(a, b, degree, method="BLEND", bias=0.5):
    """Maya Attach (default Blend, bias 0.5): the nearest pair of ends joins (``a`` = the first selected curve, turned so
    its near end is its end; ``b`` turned so its near end is its start); B's knots continue from A's end. Blend: A minus
    its last ceil(d/2) CVs, one CV bias*A_end + (1-bias)*B_start, B minus its first d//2 + 1 (joint knot multiplicity
    1). Connect: B's first CV = A's last, joint knot full multiplicity."""
    (ca, ka), (cb, kb) = a, b
    pairs = [(norm(sub(ca[-1], cb[0])), False, False), (norm(sub(ca[-1], cb[-1])), False, True),
             (norm(sub(ca[0], cb[0])), True, False), (norm(sub(ca[0], cb[-1])), True, True)]
    _d, ra, rb = min(pairs, key=lambda x: x[0])
    if ra:
        ca, ka = reverse(ca, ka)
    if rb:
        cb, kb = reverse(cb, kb)
    end = ka[-1]
    shift = end - kb[0]
    if method == "CONNECT":
        cvs = list(ca) + list(cb[1:])
        cvs[len(ca) - 1] = ca[-1]
        knots = list(ka) + [k + shift for k in kb[degree:]]
        return cvs, knots
    drop_a, drop_b = (degree + 1) // 2, degree // 2 + 1       # Maya: d1 1/1, d2 1/2, d3 2/2
    blend = add(mul(ca[-1], bias), mul(cb[0], 1.0 - bias))
    cvs = list(ca[:len(ca) - drop_a]) + [blend] + list(cb[drop_b:])
    knots = list(ka[:len(ka) - (degree - 1)]) + [k2 + shift for k2 in kb[degree:]]
    # joint knot once: A's end knot followed by B's interior knots shifted
    return cvs, knots


def fillet(t1, t2, centre):
    """Maya circular fillet between tangent points t1, t2 of a circle centred at ``centre``: a rational cubic Bezier,
    weights 1, (1+2w)/3, (1+2w)/3, 1 with w = cos(theta/2), knots 0 .. theta (radians)."""
    a, b = unit(sub(t1, centre)), unit(sub(t2, centre))
    theta = math.acos(max(-1.0, min(1.0, dot(a, b))))
    w = math.cos(theta / 2)
    # the control point of the equivalent rational quadratic: tangent lines' intersection C
    r = norm(sub(t1, centre))
    C = add(centre, mul(unit(add(a, b)), r / w))
    k = 1 + 2 * w
    cvs = [tuple(t1), mul(add(t1, mul(C, 2 * w)), 1 / k), mul(add(t2, mul(C, 2 * w)), 1 / k), tuple(t2)]
    weights = [1.0, k / 3, k / 3, 1.0]
    return cvs, [0.0, 0.0, 0.0, theta, theta, theta], weights


def fillet_lines(p0, d0, p1, d1, radius):
    """Circle of ``radius`` tangent to two lines (points p, unit directions d away from their meeting point): returns
    (t1, t2, centre)."""
    n = cross(d0, d1)
    if norm(n) < 1e-12:
        return None
    # intersection of the two lines
    w0 = sub(p0, p1)
    a, b, c = dot(d0, d0), dot(d0, d1), dot(d1, d1)
    d, e = dot(d0, w0), dot(d1, w0)
    den = a * c - b * b
    s = (b * e - c * d) / den
    X = add(p0, mul(d0, s))
    half = math.acos(max(-1.0, min(1.0, dot(unit(d0), unit(d1))))) / 2
    dist = radius / math.tan(half)
    t1 = add(X, mul(unit(d0), dist))
    t2 = add(X, mul(unit(d1), dist))
    bis = unit(add(unit(d0), unit(d1)))
    centre = add(X, mul(bis, radius / math.sin(half)))
    return t1, t2, centre


def straighten(cvs, straightness=1.0, preserve_length=True):
    """Maya Curves > Straighten: with Preserve length
    every CV leg keeps its length and turns towards the CV0 -> CV1 direction by ``straightness`` (1 = on that line);
    without it each CV moves by ``straightness`` towards the evenly spaced line CV0 -> last CV. Straightness 0 or fewer
    than 3 CVs (Maya: nothing to do) keep the CVs; with 1 and Preserve length 2 CVs stay as they are too."""
    cvs = [tuple(c) for c in cvs]
    if straightness == 0.0 or (len(cvs) < 3 and not (straightness == 1.0 and preserve_length)):
        return cvs
    if not preserve_length:
        n = len(cvs) - 1
        step = mul(sub(cvs[-1], cvs[0]), 1.0 / n)
        return [add(mul(add(cvs[0], mul(step, i)), straightness), mul(c, 1.0 - straightness))
                for i, c in enumerate(cvs)]
    d = unit(sub(cvs[1], cvs[0]))
    out = [cvs[0]]
    for a, b in zip(cvs, cvs[1:]):
        leg = sub(b, a)
        length = norm(leg)
        if straightness == 1.0 or length < 1e-12:
            out.append(add(out[-1], mul(d, length)))
            continue
        new_dir = add(mul(d, straightness), mul(leg, (1.0 - straightness) / length))
        k = norm(new_dir)
        out.append(add(out[-1], mul(new_dir, length / k if k > 1e-12 else 0.0)))
    return out


def smooth_cvs(cvs, factor=4):
    """Maya Curves > Smooth (Modify section): ``factor`` + 1 passes,
    each interior CV <- 0.4 x itself + 0.3 x (its neighbours before this pass); the end CVs stay."""
    pts = [tuple(c) for c in cvs]
    if len(pts) < 3:
        return pts
    for _ in range(int(factor + 1.0)):
        prev, cur = pts[0], pts[1]
        for i in range(1, len(pts) - 1):
            nxt = pts[i + 1]
            pts[i] = add(mul(cur, 0.4), mul(add(nxt, prev), 0.3))
            prev, cur = cur, nxt
    return pts


def move_seam(cvs, knots, degree, u):
    """Maya Move Seam on a periodic curve: the CV list turns to the knot nearest u; knots unchanged."""
    inner = knots[degree - 1:len(knots) - degree + 1]
    k = min(range(len(inner)), key=lambda i: abs(inner[i] - u))
    unique = len(cvs) - degree
    k %= unique
    core = cvs[:unique]
    turned = core[k:] + core[:k]
    return turned + turned[:degree]


# --- Cut (intersections) -------------------------------------------------------------------------------

def intersections(ca, cb, tol=1e-6, samples_n=200):
    """Parameters (ua, ub) where two curves cross (3D: closer than tol after refinement)."""
    (cva, ka, da, wa), (cvb, kb, db, wb) = ca, cb
    A = [(ka[0] + (ka[-1] - ka[0]) * i / samples_n) for i in range(samples_n + 1)]
    B = [(kb[0] + (kb[-1] - kb[0]) * i / samples_n) for i in range(samples_n + 1)]
    PA = [evaluate(cva, ka, da, u, wa) for u in A]
    PB = [evaluate(cvb, kb, db, u, wb) for u in B]
    found = []
    for i in range(samples_n):
        for j in range(samples_n):
            ua, ub = (A[i] + A[i + 1]) / 2, (B[j] + B[j + 1]) / 2
            # quick reject by segment boxes
            if norm(sub(lerp(PA[i], PA[i + 1], 0.5), lerp(PB[j], PB[j + 1], 0.5))) > \
                    norm(sub(PA[i], PA[i + 1])) + norm(sub(PB[j], PB[j + 1])):
                continue
            for _ in range(30):     # Gauss-Newton on |A(ua) - B(ub)|^2
                pa, pb = evaluate(cva, ka, da, ua, wa), evaluate(cvb, kb, db, ub, wb)
                ta = _num_d(cva, ka, da, ua, wa)
                tb = _num_d(cvb, kb, db, ub, wb)
                r = sub(pa, pb)
                a11, a12, a22 = dot(ta, ta), -dot(ta, tb), dot(tb, tb)
                g1, g2 = dot(ta, r), -dot(tb, r)
                det = a11 * a22 - a12 * a12
                if abs(det) < 1e-18:
                    break
                dua = -(a22 * g1 - a12 * g2) / det
                dub = -(-a12 * g1 + a11 * g2) / det
                ua = min(max(ua + dua, A[0]), A[-1])
                ub = min(max(ub + dub, B[0]), B[-1])
                if abs(dua) + abs(dub) < 1e-12:
                    break
            if A[i] - 1e-9 <= ua <= A[i + 1] + 1e-9 and norm(sub(evaluate(cva, ka, da, ua, wa),
                                                                  evaluate(cvb, kb, db, ub, wb))) < tol:
                if not any(abs(ua - f[0]) < 1e-6 for f in found):
                    found.append((ua, ub))
    return found


def _num_d(cvs, knots, degree, u, weights, h=1e-6):
    a = evaluate(cvs, knots, degree, max(knots[0], u - h), weights)
    b = evaluate(cvs, knots, degree, min(knots[-1], u + h), weights)
    span_ = min(knots[-1], u + h) - max(knots[0], u - h)
    return mul(sub(b, a), 1.0 / span_)


def _closest_params(ca, cb):
    """Parameters of the two curves' crossing (or closest approach)."""
    hits = intersections(ca, cb, tol=1e-4)
    if hits:
        return hits[0]
    (cva, ka, da, wa), (cvb, kb, db, wb) = ca, cb
    best = None
    for i in range(101):
        ua = ka[0] + (ka[-1] - ka[0]) * i / 100
        pa = evaluate(cva, ka, da, ua, wa)
        for j in range(101):
            ub = kb[0] + (kb[-1] - kb[0]) * j / 100
            dd = norm(sub(pa, evaluate(cvb, kb, db, ub, wb)))
            if best is None or dd < best[0]:
                best = (dd, ua, ub)
    return best[1], best[2]


def fillet_curves(ca, cb, radius=1.0):
    """Maya Fillet (default: circular, radius 1, no trim / join) between two curves (cvs, knots, degree, weights):
    a circle tangent to both curves' tangent lines at their crossing, on each curve's start side (its end side when the
    curve starts at the crossing) — exact for straight curves; a rational cubic."""
    ua, ub = _closest_params(ca, cb)
    out = []
    for (cvs, knots, deg, w), u in ((ca, ua), (cb, ub)):
        X = evaluate(cvs, knots, deg, u, w)
        t = unit(_num_d(cvs, knots, deg, u, w))
        start = evaluate(cvs, knots, deg, knots[0], w)
        toward_start = norm(sub(start, X)) > 1e-6
        out.append((X, mul(t, -1.0) if toward_start else t))
    (xa, da), (xb, db) = out
    res = fillet_lines(xa, da, xb, db, radius)
    if res is None:
        return None
    return fillet(*res)


def piece_length(cvs, knots, degree, weights=None, n=200):
    """Polyline length of ``n`` parameter-even samples (picks the longest Cut piece)."""
    a, b = knots[0], knots[-1]
    pts = [evaluate(cvs, knots, degree, a + (b - a) * i / n, weights) for i in range(n + 1)]
    return sum(norm(sub(q, p)) for p, q in zip(pts, pts[1:]))


def cut_all(curves, last_only=False, keep_longest=False):
    """Maya Cut (default: keep all pieces): every curve is split at each crossing with the others.
    ``curves`` = list of (cvs, knots, degree, weights) -> list per input of its pieces (cvs, knots).
    Cut Options: ``last_only`` = "Using last curve" (only
    the crossings with the last curve; the last curve itself stays whole), ``keep_longest`` = "Longest segments" (one
    piece per curve)."""
    params = [[] for _ in curves]
    last = len(curves) - 1
    for i in range(len(curves)):
        for j in range(i + 1, len(curves)):
            if last_only and j != last:
                continue
            for ua, ub in intersections(curves[i], curves[j], tol=1e-5):
                params[i].append(ua)
                if not last_only:
                    params[j].append(ub)
    result = []
    for (cvs, knots, deg, _w), us in zip(curves, params):
        pieces = []
        cur = (cvs, knots)
        for u in sorted(set(round(x, 9) for x in us)):
            if u <= cur[1][0] + 1e-7 or u >= cur[1][-1] - 1e-7:
                continue
            a, cur = split(cur[0], cur[1], deg, u)
            pieces.append(a)
        pieces.append(cur)
        if keep_longest and len(pieces) > 1:
            pieces = [max(pieces, key=lambda p: piece_length(p[0], p[1], deg))]
        result.append(pieces)
    return result


# --- Curves > Bend / Curl / Scale Curvature ------------------------------------------------------
# Maya's Curves > Bend / Curl / Scale Curvature commands: the CVs become "deflections" — each CV leg
# expressed in a frame carried along the curve (start frame from the first leg with the twist axis taken from Maya's
# Y-up world, each next frame = the previous one turned onto the next leg by half the angle twice). The
# commands edit deflections (or the points) and rebuild the CVs from them. Points are in Maya's Y-up object space.

def _new_frame(new_dir, frame):
    out0 = new_dir
    c = cross(frame[0], new_dir)
    ln = norm(c)
    if ln > 0.0000001:
        c = mul(c, 1.0 / ln)
        if ln > 1.0:
            ln = 1.0
        a = math.asin(ln) / 2.0
        co, si = math.cos(a), math.sin(a)
        w = cross(c, frame[2])
        out2 = add(add(add(mul(frame[2], co * co), mul(w, 2 * si * co)),
                       mul(c, si * si * dot(frame[2], c))), mul(cross(c, w), si * si))
        out1 = cross(new_dir, out2)
    else:
        out2 = mul(frame[2], -1.0) if dot(frame[0], new_dir) < 0 else frame[2]
        out1 = cross(frame[0], out2)
    return [out0, out1, out2]


def _start_frame(along):
    along = mul(along, 1.0 / norm(along))
    ang = math.atan2(along[0], along[2])
    twist = (-math.cos(ang), 0.0, math.sin(ang))
    cr = cross(twist, along)
    cr = mul(cr, 1.0 / norm(cr))
    return [along, cr, twist]


def deflections(points):
    """Curve -> deflections: [first leg] + every leg i >= 1 in the frame carried from leg i - 1."""
    pts = [tuple(p) for p in points]
    if len(pts) < 3:
        return None
    along = sub(pts[1], pts[0])
    frame = _start_frame(along)
    out = [along]
    last = pts[0]
    for p in pts[1:]:
        dif = sub(p, last)
        out.append((dot(dif, frame[0]), dot(dif, frame[1]), dot(dif, frame[2])))
        ln = norm(dif)
        if ln > 0.0000001:
            frame = _new_frame(mul(dif, 1.0 / ln), frame)
        last = p
    return out


def from_deflections(defl, points):
    """Deflections -> curve: CV 0 stays, every next CV = previous + its deflection in the carried frame."""
    pts = [tuple(p) for p in points]
    frame = _start_frame(defl[0])
    last = pts[0]
    for i in range(1, len(pts)):
        d = defl[i]
        world = add(add(mul(frame[0], d[0]), mul(frame[1], d[1])), mul(frame[2], d[2]))
        pts[i] = add(last, world)
        last = pts[i]
        ln = norm(world)
        if ln > 0.0000001:
            frame = _new_frame(mul(world, 1.0 / ln), frame)
    return pts


def bend_cvs(points, amount=0.2, twist=0.0, count=None):
    """Maya Bend (default amount 0.2, twist 0): deflections of the first ``count`` CVs get amount x (twist, 1 - twist)
    added sideways (ramped in over the first 5 CVs), leg lengths kept."""
    pts = [tuple(p) for p in points]
    n = len(pts) if count is None else count
    defl = deflections(pts)
    if defl is None:
        return pts
    yb, zb = amount * twist, amount * (1.0 - twist)
    for i in range(1, n):
        d = defl[i]
        ln = norm(d)
        y, z = yb, zb
        if i < 5.0:
            y *= i / 5.0
            z *= i / 5.0
        nd = (d[0], d[1] + y, d[2] + z)
        nl = norm(nd)
        if nl > 0.000001:
            defl[i] = mul(nd, ln / nl)
    return from_deflections(defl, pts)


def scale_curvature_cvs(points, factor=1.1, max_curvature=0.8, count=None):
    """Maya Scale Curvature (default 1.1, max 0.8): each leg's bend angle (1 - cos-ish of its deflection) scales by
    ``factor`` up to 2 x max, the sideways part scales by the ratio of sines, leg lengths kept."""
    pts = [tuple(p) for p in points]
    n = len(pts) if count is None else count
    if factor == 1.0:
        return pts
    max_curvature *= 2
    defl = deflections(pts)
    if defl is None:
        return pts
    for i in range(1, n):
        d = defl[i]
        ln = norm(d)
        ang = 1.0 - d[0] / ln
        s = math.sin(ang * 0.5 * 3.141592653589793)
        ang *= factor
        if ang > max_curvature:
            ang = max_curvature
        s2 = math.sin(ang * 0.5 * 3.141592653589793)
        ratio = s2 / s if s > 0.000001 else 1.0
        nd = ((1.0 - ang) * ln, d[1] * ratio, d[2] * ratio)
        nl = norm(nd)
        if nl > 0.000001:
            defl[i] = mul(nd, ln / nl)
    return from_deflections(defl, pts)


def _smooth_pass(pts, count):
    if count < 3 or len(pts) < count:
        return
    prev, cur = pts[0], pts[1]
    for i in range(1, count - 1):
        nxt = pts[i + 1]
        pts[i] = add(mul(cur, 0.4), mul(add(nxt, prev), 0.3))
        prev, cur = cur, nxt


def curl_cvs(points, amount=0.3, frequency=1.0, count=None):
    """Maya Curl (default amount 0.3, frequency 1): the CVs of a 4-pass smoothed copy carry the frame; each CV i
    moves by amount x (sin(f i) side + cos(f i) twist axis), ramped in while f i < 2."""
    pts = [tuple(p) for p in points]
    n = len(pts) if count is None else count
    if amount == 0.0 or n < 3 or len(pts) < n:
        return pts
    sm = list(pts)
    for _ in range(4):
        _smooth_pass(sm, len(sm))
    frame = _start_frame(sub(sm[1], sm[0]))
    last = sm[0]
    out = list(pts)
    for i in range(1, n):
        dif = sub(sm[i], last)
        ln = norm(dif)
        param = frequency * float(i)
        curl = amount * (param * 0.5 if param < 2.0 else 1.0)
        off = mul(add(mul(frame[1], math.sin(param)), mul(frame[2], math.cos(param))), curl)
        out[i] = add(pts[i], off)
        if ln > 0.0000001:
            frame = _new_frame(mul(dif, 1.0 / ln), frame)
        last = sm[i]
    # CVs after the range keep their place (Maya leaves them where they are)
    return out


# --- CV Hardness (hardenPointCurve) ----------------------------------------------------------

def harden(knots, degree, cv):
    """Full multiplicity at CV ``cv``: Maya knots cv .. cv + degree - 1 all become knot cv + degree - 1, but only when
    none of them is an end knot (otherwise nothing changes); CVs unchanged."""
    k = list(knots)
    lo, hi = cv, cv + degree - 1
    if lo < 0 or hi >= len(k):
        return k
    if any(abs(k[j] - k[0]) < 1e-12 or abs(k[j] - k[-1]) < 1e-12 for j in range(lo, hi + 1)):
        return k
    for j in range(lo, hi + 1):
        k[j] = k[hi]
    return k


# --- Fit B-spline (fitBspline on a degree-1 curve) ------------------------------------------

def fit_bspline(points):
    """The cubic through the polyline's CVs: chord-length parameters, natural ends, knots scaled to 0 .. n - 1 (the
    polyline's own domain)."""
    pts = [tuple(p) for p in points]
    if len(pts) < 3:
        return pts, clamped_uniform(len(pts), 1), 1
    t = [0.0]
    for a, b in zip(pts, pts[1:]):
        t.append(t[-1] + norm(sub(b, a)))
    span_ = float(len(pts) - 1)
    params = [x / t[-1] * span_ for x in t]
    knots = [params[0]] * 3 + params[1:-1] + [params[-1]] * 3
    return interpolate(pts, params, knots, 3), knots, 3


# --- Align (alignCurve, default position + tangent continuity) ------------------------------------

def align_ends(a, b):
    """Maya Align with the first selected curve ``a`` moving: the closest pair of ends (a start / end, b start / end)
    is joined by translating all of ``a``; a's end leg then points away from b's end leg (tangent continuity), keeping
    its length. ``b`` doesn't change. Returns a's new CVs."""
    a = [tuple(p) for p in a]
    b = [tuple(p) for p in b]
    ends = [(i, j) for i in (0, -1) for j in (0, -1)]
    ia, ib = min(ends, key=lambda e: (norm(sub(a[e[0]], b[e[1]])), ends.index(e)))
    t = sub(b[ib], a[ia])
    a = [add(p, t) for p in a]
    nxt_a = 1 if ia == 0 else -2
    nxt_b = 1 if ib == 0 else -2
    inward_b = unit(sub(b[nxt_b], b[ib]))
    leg = norm(sub(a[nxt_a], a[ia]))
    a[nxt_a] = sub(a[ia], mul(inward_b, leg))
    return a


# --- Lock Length (kit rule) ----------------------------------------------------------

def keep_leg_lengths(old, new):
    """After CVs of a length-locked curve moved (``old`` -> ``new``), the moved CVs stay and every other CV follows
    its neighbour towards the moved ones so each CV leg keeps its old length (Maya's locked curve keeps its length
    under the CV manipulator; the exact solver is)."""
    old = [tuple(p) for p in old]
    new = [tuple(p) for p in new]
    if len(old) != len(new) or len(old) < 2:
        return new
    moved = [i for i, (p, q) in enumerate(zip(old, new)) if norm(sub(p, q)) > 1e-9]
    if not moved:
        return new
    out = list(new)
    legs = [norm(sub(old[i + 1], old[i])) for i in range(len(old) - 1)]
    lo, hi = moved[0], moved[-1]
    for i in range(hi + 1, len(out)):
        d = sub(out[i], out[i - 1])
        out[i] = add(out[i - 1], mul(unit(d) if norm(d) > 1e-12 else unit(sub(old[i], old[i - 1])), legs[i - 1]))
    for i in range(lo - 1, -1, -1):
        d = sub(out[i], out[i + 1])
        out[i] = add(out[i + 1], mul(unit(d) if norm(d) > 1e-12 else unit(sub(old[i], old[i + 1])), legs[i]))
    return out
