"""Bounded public support acquisition, preserving originals and failures."""
import datetime as dt,gzip,hashlib,json,pathlib,sys,urllib.request
CACHE=pathlib.Path(r'C:\Users\gjm31\forge_cache\panama_probabilistic_20261020\amendment_20261021\R4')

def fetch(url,name,limit=16*1024**2):
    p=CACHE/name;recpath=CACHE/(name+'.receipt.json')
    assert not p.exists() and not recpath.exists(),'Do not overwrite a capture'
    rec={'url':url,'started_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'maximum_bytes':limit}
    try:
        req=urllib.request.Request(url,headers={'User-Agent':'Article202-public-completeness-design/1.0','Accept-Encoding':'gzip'})
        with urllib.request.urlopen(req,timeout=45) as r:
            b=r.read(limit+1)
            if len(b)>limit:raise ValueError('Capture beyond byte budget')
            p.open('xb').write(b)
            rec.update(status='COMPLETE',http_status=r.status,final_url=r.url,headers=dict(r.headers),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
            decoded=gzip.decompress(b) if b[:2]==b'\x1f\x8b' else b
            (CACHE/(name+'.decoded')).open('xb').write(decoded)
            rec.update(decoded_bytes=len(decoded),decoded_sha256=hashlib.sha256(decoded).hexdigest())
    except Exception as e:
        rec.update(status='FAILED',error=repr(e));raise
    finally:
        rec['finished_utc']=dt.datetime.now(dt.timezone.utc).isoformat()
        recpath.open('x',encoding='utf-8').write(json.dumps(rec,indent=2))
    print(json.dumps({k:rec[k] for k in ['url','status','bytes','sha256']}),flush=True)
    return decoded

if __name__=='__main__':fetch(sys.argv[1],sys.argv[2])
