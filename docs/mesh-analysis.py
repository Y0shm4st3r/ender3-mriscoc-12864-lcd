#!/usr/bin/env python3
"""
mesh-analysis.py - separate TILT from WARP in a Marlin bed mesh.

Why this matters
----------------
`G29` gives you a range (say 2.00 mm), but that single number mixes two defects
that are physically different and are fixed in completely different ways:

  * TILT: the bed or the gantry is mounted crooked, but as a plane.
    Fixed with the levelling knobs or by levelling the Z axis. It is assembly
    geometry.
  * WARP: the plate itself is not flat. No amount of tightening fixes it.
    It is material geometry.

Mechanical analogy: a four-legged table with one short leg wobbles, but its top
is still flat - you shim it. A table with a bowed top is not fixed by shimming -
you replace the top. This script tells you which one you have.

Method
------
Least-squares plane fit (z = a*x + b*y + c) over the mesh points. Coefficients
a and b are the tilt, in mm/m. The RESIDUAL - what is left after subtracting
that plane - is the real non-planar error of the plate.

A 2 mm range with a 0.17 mm residual is a flat plate that is badly mounted.
A 0.4 mm range with a 0.35 mm residual is a warped plate.
The second case is far worse even though the headline number is smaller.

Usage
-----
    python3 mesh-analysis.py mesh.txt

where mesh.txt holds the `G29 W` lines copied straight out of `M503`:

    G29 W I0 J0 Z-0.92250
    G29 W I1 J0 Z-0.53750
    ...

Mesh bounds are read from a `C29 L.. R.. F.. B..` line if one is present in the
file; otherwise they default to MESH_INSET 25 on an Ender 3 (L25 R204 F25 B205).
"""

import re
import sys
import statistics as st


def parse(text):
    """Extract (i, j, z) points and, if present, the mesh bounds."""
    pts = {}
    for m in re.finditer(r"G29\s+W\s+I(\d+)\s+J(\d+)\s+Z([-+]?\d*\.?\d+)", text):
        i, j, z = int(m.group(1)), int(m.group(2)), float(m.group(3))
        pts[(i, j)] = z

    bounds = (25.0, 204.0, 25.0, 205.0)  # L R F B fallback
    b = re.search(
        r"C29\s+L([-+]?[\d.]+)\s+R([-+]?[\d.]+)\s+F([-+]?[\d.]+)\s+B([-+]?[\d.]+)",
        text,
    )
    if b:
        bounds = tuple(float(g) for g in b.groups())
    return pts, bounds, b is not None


def solve3(A, b):
    """Gaussian elimination with partial pivoting for a 3x3 system."""
    A = [row[:] for row in A]
    b = b[:]
    for k in range(3):
        p = max(range(k, 3), key=lambda r: abs(A[r][k]))
        A[k], A[p] = A[p], A[k]
        b[k], b[p] = b[p], b[k]
        for r in range(k + 1, 3):
            f = A[r][k] / A[k][k]
            for c in range(k, 3):
                A[r][c] -= f * A[k][c]
            b[r] -= f * b[k]
    x = [0.0] * 3
    for k in (2, 1, 0):
        x[k] = (b[k] - sum(A[k][c] * x[c] for c in range(k + 1, 3))) / A[k][k]
    return x


def main():
    if len(sys.argv) < 2:
        text = sys.stdin.read()
    else:
        with open(sys.argv[1], encoding="utf-8", errors="replace") as fh:
            text = fh.read()

    pts, (L, R, F, B), bounds_found = parse(text)
    if len(pts) < 4:
        sys.exit("No `G29 W I.. J.. Z..` points found in the input.")

    nx = max(i for i, _ in pts) + 1
    ny = max(j for _, j in pts) + 1
    if len(pts) != nx * ny:
        sys.exit(f"Incomplete mesh: expected {nx*ny} points, found {len(pts)}.")

    xs = [L + i * (R - L) / (nx - 1) for i in range(nx)]
    ys = [F + j * (B - F) / (ny - 1) for j in range(ny)]
    flat = [pts[(i, j)] for j in range(ny) for i in range(nx)]

    print(f"mesh {nx}x{ny}  |  X {L:.0f}..{R:.0f}  Y {F:.0f}..{B:.0f} mm"
          f"  ({'bounds read from C29' if bounds_found else 'bounds assumed'})")
    print()
    print("-- raw --")
    print(f"  n       {len(flat)}")
    print(f"  min/max {min(flat):+.5f} / {max(flat):+.5f}")
    print(f"  range   {max(flat) - min(flat):.5f} mm")
    print(f"  sigma   {st.pstdev(flat):.5f} mm")
    print(f"  mean    {st.mean(flat):+.5f} mm")

    # Normal equations for the least-squares plane fit.
    n = len(flat)
    sx = sum(xs) * ny
    sy = sum(ys) * nx
    sxx = sum(x * x for x in xs) * ny
    syy = sum(y * y for y in ys) * nx
    sxy = sum(x * y for y in ys for x in xs)
    sz = sum(flat)
    sxz = sum(pts[(i, j)] * xs[i] for j in range(ny) for i in range(nx))
    syz = sum(pts[(i, j)] * ys[j] for j in range(ny) for i in range(nx))

    a, b, c = solve3([[sxx, sxy, sx], [sxy, syy, sy], [sx, sy, n]], [sxz, syz, sz])
    res = [pts[(i, j)] - (a * xs[i] + b * ys[j] + c)
           for j in range(ny) for i in range(nx)]

    print()
    print("-- fitted plane (TILT: correctable with knobs / Z axis) --")
    print(f"  dZ/dX   {a*1000:+.2f} mm/m   ({'right' if a > 0 else 'left'} side high)")
    print(f"  dZ/dY   {b*1000:+.2f} mm/m   ({'back' if b > 0 else 'front'} high)")
    print(f"  total drop across X: {a*(R-L):+.3f} mm")
    print(f"  total drop across Y: {b*(B-F):+.3f} mm")

    print()
    print("-- residual (real WARP of the plate: NOT correctable by tightening) --")
    print(f"  range   {max(res) - min(res):.4f} mm")
    print(f"  sigma   {st.pstdev(res):.4f} mm")

    frac = (max(res) - min(res)) / (max(flat) - min(flat)) if max(flat) != min(flat) else 0
    print()
    if frac < 0.25:
        print(f"  => {(1-frac)*100:.0f}% of the error is tilt. The plate is fine;")
        print("     the problem is assembly. Level it and measure again.")
    elif frac > 0.6:
        print(f"  => {frac*100:.0f}% of the error is warp. Levelling will not fix this;")
        print("     you need permanent mesh compensation or a new plate.")
    else:
        print(f"  => mixed: {frac*100:.0f}% warp. Level first, then re-evaluate how")
        print("     much residual is left.")

    print()
    print("-- residual map (mm, back of bed at top) --")
    for j in range(ny - 1, -1, -1):
        row = "  ".join(f"{res[j*nx+i]:+.3f}" for i in range(nx))
        print(f"  J{j}  {row}")


if __name__ == "__main__":
    main()
