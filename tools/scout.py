#!/usr/bin/env python3
"""네이버 블로그·카페에서 '어르신이 직접 운영' 근거가 있는 식당 후보를 모은다.

  NAVER_ID=.. NAVER_SECRET=.. python3 tools/scout.py search --region "김해" --ledger rows.json --out cand.json [--pages 4]
  KAKAO_KEY=.. python3 tools/scout.py enrich chosen.json --out pages.json

search: 지역 × 근거 문구로 검색 → 요약에 근거가 있는 글만 → 블로그 본문을 열어 지도 위젯(상호·주소·좌표)과
        근거 문장·반대 신호·스토리 신호를 뽑는다 → 장부(rows.json = update_rows.py --dump 결과)에 있는 가게는 뺀다.
enrich: Claude가 고른 후보 [{name,address,lat,lng,memo,...}]에 카카오 위치·전화·법정동을 붙여 노션 속성 형태로 만든다.
키는 환경변수로만 받는다(저장소에 쓰지 않음).
"""
import sys, os, re, json, time, html, math, argparse, urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor

UA = {"User-Agent": "Mozilla/5.0"}
KEYWORDS = [
    "할머니 혼자 운영", "할머니가 운영하는 식당", "할머니 사장님", "노부부가 운영", "노부부 식당", "할아버지 할머니 운영",
    "80대 사장님", "70대 사장님", "어르신이 운영", "할머니 손맛 노포", "할머니 국수", "할머니 칼국수", "할머니 백반",
    "할머니 순대국", "할머니 분식", "할머니 시장 맛집", "할머니 혼자 장사", "할머니 50년", "할머니 40년 장사",
    "노포 할머니", "시장 할머니 식당", "할머니 김밥", "할머니 손만두", "할머니 보리밥", "할머니 국밥",
]
OLD = r"(할머니|할매|할아버지|할배|노부부|어르신|노모|[6-9]0\s?대|[6-9]\d\s?세|칠순|팔순|구순|연세(?: 지긋| 많| 있))"
OWN = r"(운영|사장|주인|장사|혼자\s?(?:하|일|운영|장사|꾸려)|직접\s?(?:만드|끓이|빚|담그|밀|썰|굽)|손수)"
EVID = re.compile(OLD + r"[^.!?\n]{0,30}" + OWN + r"|" + r"(사장님|주인장|주인)[^.!?\n]{0,15}" + OLD)
FAMILY = re.compile(r"(우리|울|저희|외|친)\s?(할머니|할매|할아버지)|할머니(?:께|와|랑|께서도| 모시고| 생신)|어르신(?:들|분들)(?:은|이|도|께)")
NONFOOD = re.compile(r"(요양|센터|주차|마트|로또|복권|웨딩|컨벤션|호텔|리조트|분양|도장|열쇠|토이|병원|의원|약국|학원|교회|성당|부동산|안경|미용|헤어|네일|보험|은행|우체국|공원$|시청|구청|주민센터|모텔|펜션|캠핑|키즈|모래놀이|영농|조합)")
COUNTER = re.compile(r"(아드님|아들|따님|딸|며느리|자녀|사위|조카|2대|3대|대를 이어|물려받|인수|새 ?주인|사장님이 바뀌|폐업|문을 닫)")
STORY = re.compile(r"(눈물|사연|남편|먼저 떠|홀로|평생|[4-9]0\s?년(?:째| 넘| 동안| 전통| 가까이)|반세기|새벽\s?\d시|직접 (?:빚|만드|뽑|담그|키우)|손으로 (?:빚|밀)|정성|가마솥|장작|연탄|맷돌|손칼국수|한 그릇에 [\d,]+원|[2-6],?000원)")


def naver(kind, q, start=1, n=100):
    u = f"https://naverapihub.apigw.ntruss.com/search/v1/{kind}?" + urllib.parse.urlencode({"query": q, "display": n, "start": start, "sort": "sim"})
    h = {"X-NCP-APIGW-API-KEY-ID": os.environ["NAVER_ID"], "X-NCP-APIGW-API-KEY": os.environ["NAVER_SECRET"]}
    for t in range(4):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(u, headers=h), timeout=15)).get("items", [])
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(2 + 2 * t); continue
            return []
        except Exception:
            time.sleep(1)
    return []


def clean(s):
    return html.unescape(re.sub(r"</?b>", "", s or ""))


def norm(s):
    return re.sub(r"[\s()\[\]·.,'\"-]|본점|식당$", "", str(s or ""))


def dist(a, b, c, d):
    return math.hypot((a - c) * 111000, (b - d) * 111000 * math.cos(math.radians(a)))


def fetch_post(link):
    m = re.search(r"blog\.naver\.com/([^/?]+)/(\d+)", link)
    if not m:
        return None
    u = f"https://m.blog.naver.com/PostView.naver?blogId={m.group(1)}&logNo={m.group(2)}"
    try:
        t = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=15).read().decode("utf-8", "ignore")
    except Exception:
        return None
    places = []
    for pm in re.finditer(r'"name"\s*:\s*"([^"]+)",\s*"address"\s*:\s*"([^"]*)",\s*"latitude"\s*:\s*"([\d.]+)",\s*"longitude"\s*:\s*"([\d.]+)"', t):
        places.append(dict(name=html.unescape(pm.group(1)), address=html.unescape(pm.group(2)), lat=float(pm.group(3)), lng=float(pm.group(4)), pos=pm.start()))
    i = t.find("se-main-container")
    body = t[i:] if i > 0 else t
    body = re.sub(r"<script.*?</script>|<style.*?</style>", " ", body, flags=re.S)
    # keep map positions as markers in text
    text = html.unescape(re.sub(r"<[^>]+>", " ", body))
    text = re.sub(r"\s+", " ", text)
    return dict(places=places, text=text[:40000])


def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?。])\s+|\s{2,}", text) if 8 <= len(s.strip()) <= 220]


def cmd_search(a):
    ledger = json.load(open(a.ledger, encoding="utf-8")) if a.ledger else []
    led = [(norm(r[0]), r[8], r[9], r[5]) for r in ledger]
    region = a.region
    queries = [f"{region} {k}" for k in KEYWORDS]
    jobs = [(kind, q, 1 + 100 * p) for q in queries for kind in ("blog", "cafearticle") for p in range(a.pages)]
    items = {}
    calls = 0
    with ThreadPoolExecutor(6) as ex:
        for (kind, q, st), res in zip(jobs, ex.map(lambda j: naver(*j), jobs)):
            calls += 1
            for it in res:
                link = it.get("link")
                if link in items:
                    continue
                snip = clean(it.get("title")) + " " + clean(it.get("description"))
                if not EVID.search(snip):
                    continue
                items[link] = dict(kind=kind, link=link, title=clean(it.get("title")), snip=clean(it.get("description")),
                                   date=it.get("postdate") or "", q=q)
    print(f"naver calls {calls}, evidence snippets {len(items)}", file=sys.stderr)
    blogs = [x for x in items.values() if x["kind"] == "blog"][: a.max_posts]
    with ThreadPoolExecutor(8) as ex:
        posts = list(ex.map(lambda x: (x, fetch_post(x["link"])), blogs))
    cand = {}
    keys = [re.sub(r"(특별시|광역시|특별자치시|특별자치도|도|시|군|구)$", "", w) or w for w in region.split()]
    for x, p in posts:
        if not p or not p["places"]:
            continue
        sents = sentences(p["text"])
        ev = [s for s in sents if EVID.search(s) and not FAMILY.search(s)]
        if not ev:
            continue
        multi = len({pl["name"] for pl in p["places"]}) > 1
        for pl in p["places"]:
            if not all(k in pl["address"] for k in keys):
                continue
            if NONFOOD.search(pl["name"]):
                continue
            if multi:  # list posts: keep only places named near an evidence sentence
                nm = pl["name"][:6]
                near = [s for s in ev if nm and nm in p["text"][max(0, p["text"].find(s) - 400): p["text"].find(s) + 400]]
                if not near:
                    continue
                pev = near
            else:
                pev = ev
            n = norm(pl["name"])
            if any((n and ln and (n in ln or ln in n) and (lat is None or dist(pl["lat"], pl["lng"], lat, lng) < 400)) for ln, lat, lng, _ in led):
                continue
            key = n + "|" + pl["address"]
            c = cand.setdefault(key, dict(name=pl["name"], address=pl["address"], lat=pl["lat"], lng=pl["lng"], posts=[]))
            if len(c["posts"]) >= 4:
                continue
            c["posts"].append(dict(link=x["link"], date=x["date"], title=x["title"], multi=multi,
                                   evidence=[p["text"][max(0, p["text"].find(e) - 120): p["text"].find(e) + len(e) + 60] for e in pev[:3]], counter=[s for s in sents if COUNTER.search(s) and (not multi or pl["name"][:6] in s)][:2],
                                   story=[s for s in sents if STORY.search(s) and (not multi or pl["name"][:6] in s)][:3]))
    # cafe items: no body access, keep snippet as weak lead
    leads = [x for x in items.values() if x["kind"] == "cafearticle"][:40]
    out = sorted(cand.values(), key=lambda c: (-len(c["posts"]), -max(int(p["date"] or 0) for p in c["posts"])))
    json.dump(dict(region=region, naver_calls=calls, candidates=out[: a.max_cand], cafe_leads=leads), open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"candidates {len(out)} (kept {min(len(out), a.max_cand)}), cafe leads {len(leads)}", file=sys.stderr)


SHORT = {"서울특별시": "서울", "경기도": "경기", "인천광역시": "인천", "부산광역시": "부산", "대구광역시": "대구", "광주광역시": "광주", "대전광역시": "대전",
         "울산광역시": "울산", "세종특별자치시": "세종", "강원특별자치도": "강원", "충청북도": "충북", "충청남도": "충남", "전북특별자치도": "전북",
         "전라남도": "전남", "경상북도": "경북", "경상남도": "경남", "제주특별자치도": "제주"}
GU_OK = set("""경기 고양시,경기 광명시,경기 광주시,경기 구리시,경기 김포시,경기 남양주시,경기 부천시,경기 성남시,경기 수원시,경기 시흥시,경기 안양시,경기 양주시,경기 양평군,경기 용인시,경기 의정부시,경기 이천시,경기 파주시,경기 평택시,경기 포천시,경기 하남시,서울 강남구,서울 강동구,서울 강북구,서울 강서구,서울 관악구,서울 광진구,서울 구로구,서울 금천구,서울 노원구,서울 도봉구,서울 동대문구,서울 동작구,서울 마포구,서울 서대문구,서울 서초구,서울 성동구,서울 성북구,서울 송파구,서울 영등포구,서울 용산구,서울 은평구,서울 종로구,서울 중구,서울 중랑구,인천 강화군,인천 계양구,인천 남동구,인천 동구,인천 미추홀구,인천 부평구,인천 서구,인천 서해구,인천 연수구,인천 영종구,인천 제물포구,인천 중구""".split(","))


def kakao(path, **q):
    u = "https://dapi.kakao.com/v2/local/" + path + "?" + urllib.parse.urlencode(q)
    return json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"Authorization": "KakaoAK " + os.environ["KAKAO_KEY"]}), timeout=10))


def cmd_enrich(a):
    chosen = json.load(open(a.file, encoding="utf-8"))
    pages = []
    for c in chosen:
        lat, lng, name = c.get("lat"), c.get("lng"), c["name"]
        place = None
        try:
            ds = kakao("search/keyword.json", query=name, y=lat, x=lng, radius=300, sort="distance")["documents"] if lat else []
            for d in ds:
                if norm(d["place_name"])[:3] == norm(name)[:3] or norm(name) in norm(d["place_name"]) or norm(d["place_name"]) in norm(name):
                    place = d; break
        except Exception:
            pass
        if place:
            lat, lng = float(place["y"]), float(place["x"])
        reg = None
        if lat:
            try:
                reg = [r for r in kakao("geo/coord2regioncode.json", x=lng, y=lat)["documents"] if r["region_type"] == "B"][0]
            except Exception:
                pass
        addr = (place and (place.get("road_address_name") or place.get("address_name"))) or c.get("address") or ""
        r1 = SHORT.get(reg["region_1depth_name"], "") if reg else ""
        r2 = reg["region_2depth_name"] if reg else ""
        p = {"상호": name, "섭외 상태": "섭외 전", "주소": addr, "메모": c["memo"]}
        if r1:
            p["지역"] = r1
        if r1 in ("서울", "경기", "인천") and r2 and f"{r1} {r2.split()[0]}" in GU_OK:
            p["구"] = f"{r1} {r2.split()[0]}"
        if reg and reg.get("region_3depth_name"):
            p["동"] = f"{r2.split()[-1]} {reg['region_3depth_name']}"
        if place and place.get("phone"):
            p["전화번호"] = place["phone"]
        if lat:
            p.update({"place:위치:name": name, "place:위치:address": addr, "place:위치:latitude": round(lat, 7), "place:위치:longitude": round(lng, 7)})
            p["카카오맵"] = place["place_url"] if place else f"https://map.kakao.com/link/map/{urllib.parse.quote(name)},{lat:.7f},{lng:.7f}"
        p["네이버지도"] = "https://map.naver.com/p/search/" + urllib.parse.quote(f"{name} {r2.split()[0] if r2 else ''}".strip())
        pages.append({"properties": p})
    json.dump(pages, open(a.out, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"pages {len(pages)}", file=sys.stderr)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("search"); s.add_argument("--region", required=True); s.add_argument("--ledger"); s.add_argument("--out", required=True)
    s.add_argument("--pages", type=int, default=3); s.add_argument("--max-posts", type=int, default=600); s.add_argument("--max-cand", type=int, default=80)
    e = sp.add_parser("enrich"); e.add_argument("file"); e.add_argument("--out", required=True)
    a = ap.parse_args()
    cmd_search(a) if a.cmd == "search" else cmd_enrich(a)
