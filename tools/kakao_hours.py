#!/usr/bin/env python3
"""카카오맵 장소 정보에서 전화번호·영업시간을 가져온다.

  python3 tools/kakao_hours.py 9469190 191148965          # 장소 id 몇 개 시험
  HALMAE_PW=.. python3 tools/kakao_hours.py --map out.json  # 지도에서 영업시간이 빈 가게(카카오 장소 링크 있는 것)만 조회
      → out.json = [{"pid": 노션 페이지 id, "name", "kid", "hours", "tels"}] (노션 반영용), 지도에도 바로 반영(저장은 호출한 쪽이 커밋)

장소 정보: https://place.map.kakao.com/places/panel3/{id} (헤더 pf: PC). 이 주소가 허용 목록에 있어야 한다.
"""
import sys, os, re, json, time, urllib.request

H = {"pf": "PC", "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36",
     "Referer": "https://place.map.kakao.com/"}
ORDER = "월화수목금토일"


def fetch(kid):
    req = urllib.request.Request(f"https://place.map.kakao.com/places/panel3/{kid}", headers=H)
    return json.load(urllib.request.urlopen(req, timeout=15))


def fmt(j):
    tels = [x.get("tel") for x in (j.get("summary") or {}).get("phone_numbers") or [] if x.get("tel")]
    o = j.get("open_hours") or {}
    D, notes = {}, []
    for p in (o.get("week_from_today") or {}).get("week_periods") or []:
        if p.get("day_time_desc") and p["day_time_desc"] not in notes:
            notes.append(p["day_time_desc"])
        for d in p.get("days") or []:
            c = (d.get("day_of_the_week_desc") or " ")[0]
            od = d.get("on_days")
            if od:
                s = re.sub(r"\s", "", od.get("start_end_time_desc") or "")
                bt = re.search(r"(\d\d:\d\d) ~ (\d\d:\d\d) 브레이크타임", json.dumps(od, ensure_ascii=False))
                if bt:
                    s += f" (브레이크 {bt.group(1)}~{bt.group(2)})"
                D[c] = s
            else:
                D[c] = "휴무"
    parts, i = [], 0
    while i < 7:
        c = ORDER[i]
        if c not in D:
            i += 1; continue
        k = i
        while k + 1 < 7 and D.get(ORDER[k + 1]) == D[c]:
            k += 1
        parts.append((f"{c}-{ORDER[k]}" if k > i else c) + " " + D[c])
        i = k + 1
    h = ", ".join(parts)
    if len(parts) == 1 and parts[0].startswith("월-일 "):
        h = "매일 " + D["월"]
    add = (o.get("headline_addition") or {}).get("current_off_day_desc")
    if add and not re.fullmatch(r"매주 .요일 휴무", add) and add not in notes:
        notes.append(add)
    if notes:
        h += (" · " if h else "") + " · ".join(notes)
    return {"hours": h, "tels": tels}


def kid_of(u):
    m = re.search(r"place\.map\.kakao\.com/(\d+)", u or "")
    return m.group(1) if m else ""


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["--map"]:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import update_rows as U
        pw = os.environ["HALMAE_PW"]
        h, m, rows = U.load(pw)
        out, n = [], 0
        for r in rows:
            while len(r) < 16:
                r.append("")
            k = kid_of(r[10])
            if not k or r[15] or r[1] in ("촬영완료", "거절", "대상 아님", "폐업"):
                continue
            try:
                res = fmt(fetch(k))
            except Exception as e:
                print("fail", r[0], k, str(e)[:60], file=sys.stderr); time.sleep(1); continue
            time.sleep(0.4)
            if not res["hours"] and not (res["tels"] and not r[6]):
                continue
            if res["hours"]:
                r[15] = res["hours"]
            if not r[6] and res["tels"]:
                r[6] = res["tels"][0]
            out.append({"pid": r[14], "name": r[0], "kid": k, "hours": res["hours"], "tel": r[6] if res["tels"] else ""})
            n += 1
        U.save(h, m, rows, pw)
        json.dump(out, open(a[1], "w", encoding="utf-8"), ensure_ascii=False)
        print("filled", n)
    else:
        for k in a:
            print(k, fmt(fetch(k)))
