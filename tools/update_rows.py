#!/usr/bin/env python3
"""섭외 지도(index.html)의 암호화된 가게 목록을 고친다.

  HALMAE_PW=<비밀번호> python3 tools/update_rows.py patch.json      # 행 추가/갱신
  HALMAE_PW=<비밀번호> python3 tools/update_rows.py --dump out.json # 현재 목록 꺼내기
  HALMAE_PW=<옛 비번> HALMAE_NEWPW=<새 비번> python3 tools/update_rows.py --repw  # 비밀번호 변경

patch.json = 행 배열. 행 형식:
  [상호, 섭외상태, 지역, 구, 동, 주소, 전화, 메모, 위도, 경도, 카카오맵, 네이버지도, 인스타릴스, 우선섭외 0/1]
같은 상호+주소(또는 같은 카카오맵 주소)인 행이 있으면 그 행을 바꾸고, 없으면 추가한다. 삭제는 하지 않는다.
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
    patch = json.load(open(a[0], encoding="utf-8"))
    added = changed = 0
    for r in patch:
        assert isinstance(r, list) and len(r) == 14, r
        hit = None
        for i, o in enumerate(rows):
            if (norm(o[0]) == norm(r[0]) and norm(o[5]) == norm(r[5])) or (r[10] and o[10] == r[10] and "place.map.kakao.com" in str(r[10])):
                hit = i; break
        if hit is None:
            rows.append(r); added += 1
        elif rows[hit] != r:
            rows[hit] = r; changed += 1
    save(h, m, rows, pw)
    print(f"added {added}, changed {changed}, total {len(rows)}")


if __name__ == "__main__":
    main()
