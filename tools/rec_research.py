#!/usr/bin/env python3
"""장부에 이미 있는 가게를 네이버 블로그로 다시 조사해 '섭외추천' 판단 자료를 모은다.

  NAVER_ID=.. NAVER_SECRET=.. python3 tools/rec_research.py rows.json out.json [--status "섭외 전"] [--skip-memo "10/31 조사"]

rows.json = update_rows.py --dump 결과. 가게마다 '상호 + 동(없으면 구·시)'으로 블로그를 검색해 상호가 들어간 글만 남기고,
요약(최대 6개)과 상위 2개 글 본문에서 사연·업력·정성·비주얼 신호가 있는 문장을 뽑는다. 판단(섭외추천 여부)은 사람이/Claude가 한다.
"""
import sys, os, re, json, argparse
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scout import naver, clean, norm, fetch_post, sentences

SIG = re.compile(r"(눈물|사연|남편|먼저 떠|홀로|혼자|평생|[3-9]0\s?년(?:째| 넘| 동안| 전통| 가까이| 세월)|반세기|19[4-8]\d년|새벽\s?\d시|직접 (?:빚|만드|뽑|담그|키우|농사|기른|재배)|손으로 (?:빚|밀)|손수|정성|가마솥|장작|연탄|맷돌|홍두깨|수타|손칼국수|손만두|비주얼|푸짐|산더미|노포|할머니|할아버지|노부부|어르신|[7-9]0\s?대|[7-9]\d\s?세|방송|생활의 달인|백년가게)")


def place_word(r):
    dong = (r[4] or "").split()
    if dong:
        return dong[-1]
    gu = (r[3] or "").split()
    if gu:
        return gu[-1]
    return r[2] or ""


def research(r):
    name, n = r[0], norm(r[0])
    q = f"{re.sub(r'[(].*?[)]', '', name).strip()} {place_word(r)}".strip()
    items = naver("blog", q, 1, 30)
    keep = []
    for it in items:
        t, d = clean(it.get("title")), clean(it.get("description"))
        if n and len(n) >= 2 and (n in norm(t) or n in norm(d)):
            keep.append({"title": t[:80], "desc": d[:220], "link": it.get("link", ""), "date": it.get("postdate", "")})
    keep.sort(key=lambda x: x["date"], reverse=True)
    sig = []
    for it in keep[:2]:
        p = fetch_post(it["link"])
        if not p:
            continue
        for s in sentences(p["text"]):
            if SIG.search(s) and len(sig) < 8:
                sig.append({"s": s[:200], "link": it["link"], "date": it["date"]})
    return {"name": name, "status": r[1], "sido": r[2], "gu": r[3], "dong": r[4], "addr": r[5], "memo": (r[7] or "")[:600],
            "reel": r[12] or "", "query": q, "posts": keep[:6], "signals": sig}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("rows"); ap.add_argument("out")
    ap.add_argument("--status", default="섭외 전")
    ap.add_argument("--skip-memo", default="")
    a = ap.parse_args()
    rows = [r for r in json.load(open(a.rows, encoding="utf-8")) if r[1] == a.status and not (a.skip_memo and a.skip_memo in (r[7] or ""))
            and "[섭외추천]" not in (r[7] or "")]
    with ThreadPoolExecutor(6) as ex:
        res = list(ex.map(research, rows))
    json.dump(res, open(a.out, "w", encoding="utf-8"), ensure_ascii=False)
    print("rows", len(res), "with posts", sum(1 for x in res if x["posts"]), file=sys.stderr)
