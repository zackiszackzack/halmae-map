# roads/stations.json: subway/rail stations (Kakao local category SW8) with their exits, for the map overlay
import json, sys
LINES = {
 "수도권1호선":("#0052A4","1"),"수도권2호선":("#00A84D","2"),"수도권3호선":("#EF7C1C","3"),"수도권4호선":("#00A5DE","4"),
 "수도권5호선":("#996CAC","5"),"수도권6호선":("#CD7C2F","6"),"수도권7호선":("#747F00","7"),"수도권8호선":("#E6186C","8"),
 "수도권9호선":("#BDB092","9"),"수인분당선":("#F5A200","수인분당"),"경의중앙선":("#77C4A3","경의중앙"),"신분당선":("#D4003B","신분당"),
 "공항철도":("#0090D2","공항"),"경춘선":("#0C8E72","경춘"),"경강선":("#003DA5","경강"),"서해선":("#8FC31F","서해"),
 "인천1호선":("#7CA8D5","인천1"),"인천2호선":("#ED8B00","인천2"),"우이신설경전철":("#B0CE18","우이신설"),"신림선":("#6789CA","신림"),
 "의정부경전철":("#FDA600","의정부"),"용인에버라인":("#509F22","에버라인"),"김포골드라인":("#A17800","김포골드"),"GTX-A":("#9A6292","A"),
 "부산1호선":("#F06A00","1"),"부산2호선":("#81BF48","2"),"부산3호선":("#BB8C00","3"),"부산4호선":("#217DCB","4"),
 "동해선":("#0054A6","동해"),"부산김해경전철":("#8652A1","부산김해"),"대구1호선":("#D93F5C","1"),"대구2호선":("#00AA80","2"),
 "대구3호선":("#FFB100","3"),"대경선":("#1E64B4","대경"),"대전1호선":("#007448","1"),"광주1호선":("#009088","1"),
}
EXALIAS = {"1호선":"1","2호선":"2","3호선":"3","4호선":"4","5호선":"5","6호선":"6","7호선":"7","8호선":"8","9호선":"9"}
g = json.load(open(sys.argv[1]))
names = list(LINES)
out = {"L": [[k, LINES[k][0], LINES[k][1]] for k in names], "S": []}
for s in g:
    li = [names.index(l) for l in s["lines"] if l in LINES]
    if not li: continue
    ex = []
    for e in s["exits"]:
        # which of the station's lines this exit belongs to (text between station name and number, e.g. "2호선", "부산1호선", "수인분당선")
        lab = e["line"]; idx = li[0]
        for j in li:
            full, short = names[j], names[j].replace("수도권", "")
            if lab and (lab == full or lab == short or lab in full or full.endswith(lab)): idx = j; break
        ex.append([e["n"], e["lat"], e["lng"], idx])
    out["S"].append([s["name"], round(s["lat"], 6), round(s["lng"], 6), li, ex])
json.dump(out, open(sys.argv[2], "w"), ensure_ascii=False, separators=(",", ":"))
print("stations", len(out["S"]), "exits", sum(len(x[4]) for x in out["S"]))
