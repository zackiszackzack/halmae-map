import json, urllib.request, urllib.parse, os, time, math, re
from concurrent.futures import ThreadPoolExecutor
KEY=os.environ['KAKAO_KEY']
def q(path, **p):
    u="https://dapi.kakao.com/v2/local/"+path+"?"+urllib.parse.urlencode(p)
    for t in range(5):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(u,headers={"Authorization":"KakaoAK "+KEY}),timeout=10))
        except Exception as e: time.sleep(1+t)
    return {"documents":[],"meta":{"is_end":True}}
raw=json.load(open('stations_raw.json'))
def dist(a,b,c,d): return math.hypot((a-c)*111000,(b-d)*88000)
groups=[]
for x in raw:
    name=x['place_name'].split(' ')[0]; line=x['category_name'].split(' > ')[-1]
    lat,lng=float(x['y']),float(x['x'])
    g=next((g for g in groups if g['name']==name and dist(g['lat'],g['lng'],lat,lng)<700),None)
    if not g: g={'name':name,'lat':lat,'lng':lng,'lines':[],'pts':[]}; groups.append(g)
    if line not in g['lines']: g['lines'].append(line)
    g['pts'].append((lat,lng))
for g in groups:
    g['lat']=sum(p[0] for p in g['pts'])/len(g['pts']); g['lng']=sum(p[1] for p in g['pts'])/len(g['pts']); del g['pts']
EXRE=re.compile(r'(\d+(?:-\d+)?)번\s?출구')
def exits(g):
    res=[];seen=[];miss=0;n=0
    while n<30:
        n+=1
        d=q("search/keyword.json",query=f"{g['name']} {n}번출구",x=g['lng'],y=g['lat'],radius=1200,sort="distance",size=15)
        hit=False
        for x in d['documents']:
            if not x['category_name'].endswith('지하철출구') or not x['place_name'].startswith(g['name']+' '): continue
            m=EXRE.search(x['place_name'])
            if not m: continue
            num=m.group(1)
            if num.split('-')[0]==str(n): hit=True
            lat,lng=float(x['y']),float(x['x'])
            if any(s[0]==num and dist(s[1],s[2],lat,lng)<120 for s in seen): continue
            seen.append((num,lat,lng))
            res.append({'n':num,'lat':round(lat,6),'lng':round(lng,6),'line':x['place_name'][len(g['name'])+1:m.start()].strip()})
        if hit: miss=0
        else:
            miss+=1
            if miss>=2 and n>=2: break
    return res
with ThreadPoolExecutor(8) as ex:
    for g,e in zip(groups,ex.map(exits,groups)): g['exits']=e
json.dump(groups,open('stations_grouped.json','w'),ensure_ascii=False)
print('groups',len(groups),'exits',sum(len(g['exits']) for g in groups),'no-exit groups',sum(1 for g in groups if not g['exits']))
