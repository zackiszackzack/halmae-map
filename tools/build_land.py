#!/usr/bin/env python3
"""roads/L_<ty>_<tx>.json land tiles (0.25°) from a provinces GeoJSON, plus roads/land_index.json.

  python3 tools/build_land.py skorea-provinces-2018-geo.json roads/

Land = union of all provinces (KOSTAT 2018, southkorea/southkorea-maps). Each tile is either fully land
(listed with 1 in the index, no file), fully sea (absent) or partial (2 + file with encoded rings, filled even-odd).
"""
import sys, os, json, math
from shapely.geometry import shape, box, Polygon, MultiPolygon
from shapely.ops import unary_union

src, out = sys.argv[1], sys.argv[2]
T = 0.25
feats = json.load(open(src))["features"]
land = unary_union([shape(f["geometry"]).buffer(0) for f in feats]).simplify(0.00004, preserve_topology=True)

def enc_num(n):
    n = ~(n << 1) if n < 0 else n << 1; s = ""
    while n >= 32: s += chr((32 | (n & 31)) + 63); n >>= 5
    return s + chr(n + 63)

minx, miny, maxx, maxy = land.bounds
idx = {}
total = 0
for ty in range(math.floor(miny / T), math.floor(maxy / T) + 1):
    for tx in range(math.floor(minx / T), math.floor(maxx / T) + 1):
        b = box(tx * T, ty * T, (tx + 1) * T, (ty + 1) * T)
        if not land.intersects(b):
            continue
        part = land.intersection(b)
        if part.is_empty or part.area < 1e-9:
            continue
        if part.area >= b.area * 0.9999:
            idx[f"{ty}_{tx}"] = 1; continue
        polys = [part] if isinstance(part, Polygon) else [g for g in getattr(part, "geoms", []) if isinstance(g, Polygon)]
        rings = []
        for p in polys:
            rings.append(list(p.exterior.coords)); rings += [list(r.coords) for r in p.interiors]
        st = [0, 0]; strs = []
        for r in rings:
            pts = [(round(x * 1e5), round(y * 1e5)) for x, y in r]
            pts = [q for i, q in enumerate(pts) if i == 0 or q != pts[i - 1]]
            if len(pts) < 4: continue
            s = enc_num(pts[0][0] - st[0]) + enc_num(pts[0][1] - st[1]); st = list(pts[0])
            for (a, c), (d, e) in zip(pts, pts[1:]): s += enc_num(d - a) + enc_num(e - c)
            strs.append(s)
        if not strs: continue
        fn = os.path.join(out, f"L_{ty}_{tx}.json")
        json.dump({"p": strs}, open(fn, "w"), separators=(",", ":"))
        total += os.path.getsize(fn)
        idx[f"{ty}_{tx}"] = 2
json.dump(idx, open(os.path.join(out, "land_index.json"), "w"), separators=(",", ":"))
print("tiles", len(idx), "partial", sum(1 for v in idx.values() if v == 2), "bytes", total)
