import os, urllib.request, concurrent.futures
Z=6; X0,X1=43,49; Y0,Y1=24,31
jobs=[(x,y) for x in range(X0,X1+1) for y in range(Y0,Y1+1)]
def get(j):
    x,y=j; p=f"tiles/{Z}_{x}_{y}.png"
    if os.path.exists(p) and os.path.getsize(p)>0: return p
    url=f"https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{Z}/{x}/{y}.png"
    for _ in range(4):
        try:
            with urllib.request.urlopen(url, timeout=45) as r: d=r.read()
            open(p,'wb').write(d); return p
        except Exception as e: err=e
    return f"FAIL {x},{y} {err}"
with concurrent.futures.ThreadPoolExecutor(12) as ex: res=list(ex.map(get,jobs))
bad=[r for r in res if str(r).startswith('FAIL')]
print(f"{len(jobs)} tiles, {len(bad)} failed"); [print(b) for b in bad]
