# usage: python3 tools/build_land_lo.py skorea-provinces-2018-geo.json roads/land_lo.json 0.0003
# roads/land_lo.json: whole-country land outline, simplified (~50 m) — drawn when zoomed out / before tiles load
import sys, json
from shapely.geometry import shape, Polygon
from shapely.ops import unary_union
src, out, tol = sys.argv[1], sys.argv[2], float(sys.argv[3])
land = unary_union([shape(f["geometry"]).buffer(0) for f in json.load(open(src))["features"]]).simplify(tol, preserve_topology=True)
def enc_num(n):
    n = ~(n << 1) if n < 0 else n << 1; s = ""
    while n >= 32: s += chr((32 | (n & 31)) + 63); n >>= 5
    return s + chr(n + 63)
polys = [land] if isinstance(land, Polygon) else list(land.geoms)
st = [0, 0]; strs = []
for p in polys:
    if p.area < 2e-7: continue      # drop specks (< ~2,000 m²)
    for r in [p.exterior] + list(p.interiors):
        pts = [(round(x * 1e5), round(y * 1e5)) for x, y in r.coords]
        pts = [q for i, q in enumerate(pts) if i == 0 or q != pts[i - 1]]
        if len(pts) < 4: continue
        s = enc_num(pts[0][0] - st[0]) + enc_num(pts[0][1] - st[1]); st = list(pts[0])
        for (a, c), (d, e) in zip(pts, pts[1:]): s += enc_num(d - a) + enc_num(e - c)
        strs.append(s)
json.dump({"p": strs}, open(out, "w"), separators=(",", ":"))
import os; print("rings", len(strs), "bytes", os.path.getsize(out))
