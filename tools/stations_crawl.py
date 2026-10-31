import json, urllib.request, urllib.parse, os, time
KEY=os.environ['KAKAO_KEY']
def q(path, **p):
    u="https://dapi.kakao.com/v2/local/"+path+"?"+urllib.parse.urlencode(p)
    for t in range(4):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(u,headers={"Authorization":"KakaoAK "+KEY}),timeout=10))
        except Exception as e: time.sleep(1+t)
    raise SystemExit("fail "+u)
out={}; calls=0
def rect(x0,y0,x1,y1,depth=0):
    global calls
    docs=[]; 
    for page in (1,2,3):
        d=q("search/category.json",category_group_code="SW8",rect=f"{x0},{y0},{x1},{y1}",page=page,size=15); calls+=1
        docs+=d['documents']
        if d['meta']['is_end']: break
    total=d['meta']['total_count']
    if total>45 and depth<12:
        mx,my=(x0+x1)/2,(y0+y1)/2
        for r in ((x0,y0,mx,my),(mx,y0,x1,my),(x0,my,mx,y1),(mx,my,x1,y1)): rect(*r,depth=depth+1)
    else:
        for x in docs: out[x['id']]=x
rect(124.5,33.0,131.0,38.7)
json.dump(list(out.values()),open('stations_raw.json','w'),ensure_ascii=False)
print('stations',len(out),'calls',calls)
