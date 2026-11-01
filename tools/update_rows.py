#!/usr/bin/env python3
"""섭외 지도(index.html)의 암호화된 가게 목록을 고친다.

  HALMAE_PW=<비밀번호> python3 tools/update_rows.py patch.json      # 행 추가/갱신
  HALMAE_PW=<비밀번호> python3 tools/update_rows.py --dump out.json # 현재 목록 꺼내기
  HALMAE_PW=<옛 비번> HALMAE_NEWPW=<새 비번> python3 tools/update_rows.py --repw  # 비밀번호 변경

  HALMAE_PW=<비밀번호> python3 tools/update_rows.py --from-notion rows.json  # 노션 rows 조회 결과로 갱신
  HALMAE_PW=<비밀번호> python3 tools/update_rows.py --from-notion rows.json --since-file tools/last_sync.txt
      # last_sync.txt 시각 이후에 고친 행만 반영하고, 반영한 마지막 '최종 편집' 시각을 그 파일에 적는다
  HALMAE_PW=<비밀번호> python3 tools/update_rows.py --remove 상호 주소          # 한 곳 빼기

patch.json = 행 배열. 행 형식:
  [상호, 섭외상태, 지역, 구, 동, 주소, 전화, 메모, 위도, 경도, 카카오맵, 네이버지도, 인스타릴스, 우선섭외 0/1, (노션 페이지 id), (영업시간)]
rows.json = 노션 query-data-sources(rows 모드) 결과의 "results" 배열들을 이어 붙인 JSON 배열(값은 받은 그대로).
같은 노션 페이지 id → 같은 카카오 place 링크 → 같은 상호+주소 → (하나뿐인) 같은 상호 순으로 찾아 바꾸고, 없으면 추가한다.
비밀번호는 저장소에 절대 쓰지 말 것(환경변수로만 받는다).
"""
import sys, os, re, json, base64, datetime
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(HERE, "..", "index.html")
BLOB_RE = re.compile(r"^const __BLOB=(\{.*\});$", re.M)


def kdf(pw, salt, n):
    return PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=n).derive(pw.encode())


def load(pw):
    h = open(INDEX, encoding="utf-8").read()
    m = BLOB_RE.search(h)
    b = json.loads(m.group(1))
    key = kdf(pw, base64.b64decode(b["s"]), b["n"])
    rows = json.loads(AESGCM(key).decrypt(base64.b64decode(b["i"]), base64.b64decode(b["c"]), None))
    return h, m, rows


def save(h, m, rows, pw, n=250000):
    salt, iv = os.urandom(16), os.urandom(12)
    ct = AESGCM(kdf(pw, salt, n)).encrypt(iv, json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode(), None)
    blob = {"s": base64.b64encode(salt).decode(), "i": base64.b64encode(iv).decode(), "n": n, "c": base64.b64encode(ct).decode()}
    h = h[:m.start(1)] + json.dumps(blob) + h[m.end(1):]
    today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).strftime("%Y-%m-%d")
    h = re.sub(r'const SNAP = "\d{4}-\d{2}-\d{2}";', f'const SNAP = "{today}";', h, count=1)
    open(INDEX, "w", encoding="utf-8").write(h)


def norm(s):
    return re.sub(r"\s+", "", str(s or ""))


def md_plain(t):
    t = str(t or "")
    t = re.sub(r"\[([^\]]*)\]\((https?://[^)\s]+)\)", lambda m: m.group(2) if m.group(1).strip() in ("", m.group(2)) else f"{m.group(1)} {m.group(2)}", t)
    t = re.sub(r"\\([\\`*_{}\[\]()#+\-.!|~>])", r"\1", t)
    t = re.sub(r"\s·\s+/\s", " · ", t.replace("**", ""))  # empty memo between a prefix and an appended note
    return t.strip()


def pid(u):
    m = re.search(r"([0-9a-f]{32})", str(u or "").replace("-", ""))
    return m.group(1) if m else ""


def from_notion(o):
    lat, lng = o.get("place:위치:latitude"), o.get("place:위치:longitude")
    num = lambda v: round(float(v), 6) if v not in (None, "") else None
    return [md_plain(o.get("상호")), o.get("섭외 상태") or "섭외 전", o.get("지역") or "", o.get("구") or "", o.get("동") or "",
            md_plain(o.get("주소")), o.get("전화번호") or "", md_plain(o.get("메모")), num(lat), num(lng),
            o.get("카카오맵") or "", o.get("네이버지도") or "", o.get("인스타 릴스") or "",
            1 if o.get("우선 섭외") in ("__YES__", True) else 0, pid(o.get("url")), md_plain(o.get("영업시간"))]


def find(rows, r):
    rid = r[14] if len(r) > 14 else ""
    if rid:
        for i, o in enumerate(rows):
            if len(o) > 14 and o[14] == rid:
                return i
    if r[10] and "place.map.kakao.com" in str(r[10]):
        for i, o in enumerate(rows):
            if o[10] == r[10] and not (rid and len(o) > 14 and o[14] and o[14] != rid):
                return i
    for i, o in enumerate(rows):
        if norm(o[0]) == norm(r[0]) and norm(o[5]) == norm(r[5]) and not (rid and len(o) > 14 and o[14] and o[14] != rid):
            return i
    # same name only counts when it is in the same area (another city with the same 상호 is a different shop)
    same = [i for i, o in enumerate(rows) if norm(o[0]) == norm(r[0]) and not (len(o) > 14 and o[14])
            and o[2] == r[2] and (not o[3] or not r[3] or o[3] == r[3])]
    return same[0] if len(same) == 1 and rid else None


def main():
    pw = os.environ.get("HALMAE_PW")
    if not pw:
        sys.exit("HALMAE_PW 환경변수가 없어요")
    h, m, rows = load(pw)
    a = sys.argv[1:]
    if a[:1] == ["--dump"]:
        json.dump(rows, open(a[1], "w", encoding="utf-8"), ensure_ascii=False)
        print("dumped", len(rows)); return
    if a[:1] == ["--repw"]:
        new = os.environ.get("HALMAE_NEWPW")
        if not new:
            sys.exit("HALMAE_NEWPW 환경변수가 없어요")
        save(h, m, rows, new); print("password changed,", len(rows), "rows"); return
    if a[:1] == ["--remove"]:
        keep = [o for o in rows if not (norm(o[0]) == norm(a[1]) and (len(a) < 3 or norm(o[5]) == norm(a[2])))]
        print("removed", len(rows) - len(keep)); save(h, m, keep, pw); return
    if a[:1] == ["--from-notion"]:
        src = json.load(open(a[1], encoding="utf-8"))
        if isinstance(src, dict):
            src = src.get("results", [])
        since_file = a[a.index("--since-file") + 1] if "--since-file" in a else None
        since = open(since_file).read().strip() if since_file else ""
        ts = lambda o: str(o.get("최종 편집") or "")
        if since:
            src = [o for o in src if ts(o) >= since]
        seen, uniq = set(), []
        for o in sorted(src, key=ts, reverse=True):
            k = pid(o.get("url")) or o.get("상호")
            if k not in seen:
                seen.add(k); uniq.append(o)
        patch = [from_notion(o) for o in uniq if o.get("상호")]
        if since_file and uniq:
            open(since_file, "w").write(max(ts(o) for o in uniq) + "\n")
        print("notion rows since", since or "-", ":", len(patch))
    else:
        patch = json.load(open(a[0], encoding="utf-8"))
    added = changed = 0
    report = []
    NAMES = ["상호", "섭외 상태", "지역", "구", "동", "주소", "전화", "메모", "위도", "경도", "카카오맵", "네이버지도", "인스타 릴스", "우선 섭외", "노션 id", "영업시간"]
    for r in patch:
        assert isinstance(r, list) and len(r) in (14, 15, 16), r
        hit = find(rows, r)
        if hit is not None:  # keep columns the patch doesn't carry (page id, 영업시간)
            r = list(r)
            while len(r) < len(rows[hit]):
                r.append(rows[hit][len(r)])
        where = " ".join(x for x in (r[2], r[4] or r[3]) if x)
        pin = "지도에 점 표시" if r[8] is not None else "좌표 없음 — 검색으로만 보임"
        if hit is None:
            rows.append(r); added += 1
            report.append(f"ADDED\t{r[0]}\t{where}\t{r[1]}\t{pin}\t{'릴스 있음' if r[12] else ''}")
        elif rows[hit] != r:
            o = rows[hit]
            diff = []
            for k in range(min(len(o), len(r))):
                if k == 14: continue
                if o[k] != r[k]:
                    if k == 1: diff.append(f"섭외 상태 '{o[1]}' → '{r[1]}'")
                    elif k in (8, 9): diff.append("위치") if "위치" not in diff else None
                    else: diff.append(NAMES[k])
            rows[hit] = r
            if diff:
                changed += 1
                report.append(f"CHANGED\t{r[0]}\t{where}\t{', '.join(diff)}\t{pin}")
    save(h, m, rows, pw)
    for line in report:
        print(line)
    print(f"added {added}, changed {changed}, total {len(rows)}")


if __name__ == "__main__":
    main()
