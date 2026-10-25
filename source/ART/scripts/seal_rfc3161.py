"""RFC3161 digest-only requests. Verify signature, imprint and nonce with OpenSSL.

No catalogue, manuscript or credentials are transmitted. A failed receipt never
authorizes access or emission. There is no provider fallback.
"""
import argparse, datetime as dt, hashlib, json, pathlib, subprocess, urllib.request

OPENSSL = pathlib.Path(r'C:\Program Files\Git\usr\bin\openssl.exe')
CA = pathlib.Path(r'C:\Users\gjm31\AppData\Local\Programs\Python\Python313\Lib\site-packages\certifi\cacert.pem')
ENDPOINT = 'http://timestamp.digicert.com'
def now(): return dt.datetime.now(dt.timezone.utc).isoformat()
def sha(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def run(args):
    p=subprocess.run([str(OPENSSL),*map(str,args)],capture_output=True,text=True,timeout=30)
    return {'exit_code':p.returncode,'stdout':p.stdout,'stderr':p.stderr}

def seal(source,destination):
    source=pathlib.Path(source).resolve(); destination=pathlib.Path(destination).resolve()
    destination.mkdir(parents=True,exist_ok=False)
    receipt={'source':str(source),'sha256':sha(source),'endpoint':ENDPOINT,
             'started_utc':now(),'status':'FAILED','signature_verified':False,
             'independent_time_accuracy_seconds':None}
    try:
        req=destination/'request.tsq'; response=destination/'response.tsr'
        receipt['query']=run(['ts','-query','-data',source,'-sha256','-cert','-out',req])
        if receipt['query']['exit_code']: raise RuntimeError('OpenSSL query failed')
        body=req.read_bytes();receipt['request_bytes']=len(body)
        request=urllib.request.Request(ENDPOINT,data=body,headers={
            'Content-Type':'application/timestamp-query','Accept':'application/timestamp-reply'},method='POST')
        receipt['request_sent_utc']=now()
        with urllib.request.urlopen(request,timeout=40) as r:
            raw=r.read(1024*1024+1)
            receipt['http_status']=r.status
            receipt['content_type']=r.headers.get('Content-Type')
        receipt['response_received_utc']=now()
        response.write_bytes(raw)
        if len(raw)>1024*1024: raise RuntimeError('Oversized timestamp reply')
        receipt['response_sha256']=sha(response)
        receipt['reply_text']=run(['ts','-reply','-in',response,'-text'])
        receipt['verification']=run(['ts','-verify','-queryfile',req,'-in',response,'-CAfile',CA])
        receipt['ca_bundle_sha256']=sha(CA)
        if receipt['verification']['exit_code']: raise RuntimeError('Timestamp signature/chain/imprint/nonce not verified')
        if sha(source)!=receipt['sha256']: raise RuntimeError('Source changed during sealing')
        receipt['signature_verified']=True
        receipt['status']='VERIFIED_SIGNATURE_IMPRINT_NONCE_AND_CHAIN'
    except Exception as e:
        receipt['error']=repr(e)
    receipt['finished_utc']=now()
    (destination/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(receipt,indent=2))
    return receipt

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('source');a.add_argument('destination');args=a.parse_args()
    raise SystemExit(0 if seal(args.source,args.destination)['signature_verified'] else 2)
