# usage: python3 tools/build_overview.py roads roads/overview.json 0.0025 3e-4 40
# Build roads/overview.json: one small, simplified national layer (big parks/forests, lakes, big rivers,
# motorways/trunk roads) drawn from the first screen until the detailed 0.25° tiles take over.
import json, glob, sys, math, os
src = sys.argv[1]; out = sys.argv[2]
TOL = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0012
MINA = float(sys.argv[4]) if len(sys.argv) > 4 else 4e-6   # deg² (~0.05 km²)

def dec(s, st):
    v = []; i = 0
    while i < len(s):
        r = sh = 0
        while True:
            b = ord(s[i]) - 63; i += 1; r |= (b & 31) << sh; sh += 5
            if b < 32: break
        v.append(~(r >> 1) if r & 1 else r >> 1)
    v[0] += st[0]; v[1] += st[1]; st[0], st[1] = v[0], v[1]
    return v

def pts_of(v):
    x = y = 0; P = []
    for i in range(0, len(v) - 1, 2):
        x += v[i]; y += v[i + 1]; P.append((x, y))
    return P

def decall(lst):
    st = [0, 0]; res = []
    for item in lst or []:
        if isinstance(item, str): res.append((None, pts_of(dec(item, st))))
        else: res.append((item[0], pts_of(dec(item[1], st))))
    return res

def dp(P, tol):
    if len(P) < 3: return P
    keep = [False] * len(P); keep[0] = keep[-1] = True; stack = [(0, len(P) - 1)]
    while stack:
        a, b = stack.pop(); ax, ay = P[a]; bx, by = P[b]; dx, dy = bx - ax, by - ay; L = math.hypot(dx, dy) or 1e-9
        best, bi = -1, -1
        for i in range(a + 1, b):
            px, py = P[i]; d = abs(dy * (px - ax) - dx * (py - ay)) / L
            if d > best: best, bi = d, i
        if best > tol: keep[bi] = True; stack += [(a, bi), (bi, b)]
    return [p for p, k in zip(P, keep) if k]

def dp_ring(P, tol):
    if len(P) < 4: return P
    x0, y0 = P[0]; m = max(range(len(P)), key=lambda i: (P[i][0]-x0)**2 + (P[i][1]-y0)**2)
    return dp(P[:m + 1], tol)[:-1] + dp(P[m:], tol)

def area(P):
    s = 0
    for i in range(len(P)):
        x1, y1 = P[i]; x2, y2 = P[(i + 1) % len(P)]; s += x1 * y2 - x2 * y1
    return abs(s) / 2 / 1e10

def length(P):
    return sum(math.hypot(P[i+1][0]-P[i][0], P[i+1][1]-P[i][1]) for i in range(len(P)-1)) / 1e5

def enc_num(n):
    n = ~(n << 1) if n < 0 else n << 1; s = ""
    while n >= 32: s += chr((32 | (n & 31)) + 63); n >>= 5
    return s + chr(n + 63)

class Enc:
    def __init__(s): s.st = (0, 0)
    def __call__(s, P):
        P = [(round(x / Q_) * Q_, round(y / Q_) * Q_) for x, y in P]
        P = [p for i, p in enumerate(P) if i == 0 or p != P[i - 1]]
        x0, y0 = P[0]; out = enc_num(x0 - s.st[0]) + enc_num(y0 - s.st[1]); s.st = (x0, y0)
        for (a, b), (c, d) in zip(P, P[1:]): out += enc_num(c - a) + enc_num(d - b)
        return out

T = TOL * 1e5
Q_ = int(sys.argv[5]) if len(sys.argv) > 5 else 40
A, Wl, R = [], [], []
seen = set()
for f in sorted(glob.glob(os.path.join(src, "M_*.json"))):
    d = json.load(open(f))
    for k, P in decall(d.get("a")):
        if len(P) < 4 or area(P) < (MINA / 10 if k == 0 else MINA): continue
        Q = dp_ring(P, T * (1.0 if k == 0 else 1.6))
        if len(Q) >= 4: A.append((k, Q))
    for k, P in decall(d.get("w")):
        if k != 0 or length(P) < 0.02: continue
        Q = dp(P, T)
        if len(Q) >= 2: Wl.append((k, Q))
    for k, P in decall(d.get("r")):
        if k not in (0, 1) or length(P) < (0.01 if k == 0 else 0.04): continue
        Q = dp(P, T)
        key = (k, Q[0], Q[-1])
        if key in seen: continue
        seen.add(key); R.append((k, Q))
res = {}
for name, lst in (("a", A), ("w", Wl), ("r", R)):
    e = Enc(); res[name] = [[k, e(P)] for k, P in lst]
json.dump(res, open(out, "w"), separators=(",", ":"))
print("areas", len(A), "rivers", len(Wl), "roads", len(R), "bytes", os.path.getsize(out))
