"""New public training captures only; no protected local catalogues are read."""
import datetime as dt, hashlib, json, math, pathlib, subprocess, urllib.parse, urllib.request
from seal_rfc3161 import OPENSSL,CA

ROOT=pathlib.Path(__file__).resolve().parents[1]
CACHE=pathlib.Path(r'C:\Users\gjm31\forge_cache\panama_probabilistic_20261020')
UTC=dt.timezone.utc
def now():return dt.datetime.now(UTC)
def digest(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def write_new(p,obj):
    with pathlib.Path(p).open('x',encoding='utf-8') as f:json.dump(obj,f,indent=2,ensure_ascii=False,allow_nan=False)

def verify_access(contract=None,seal_dir=None):
    contract=pathlib.Path(contract or ROOT/'config/PUBLIC_TRAINING_ACCESS_V2.json')
    seal_dir=pathlib.Path(seal_dir or CACHE/'access_v2_rfc3161_20261021')
    a=json.loads(contract.read_text(encoding='utf-8'))
    receipt=json.loads((seal_dir/'receipt.json').read_text(encoding='utf-8'))
    if a['schema_version']!=2 or a['protected_results_access'] or a['retrospective_scoring']:
        raise ValueError('Access scope differs')
    if digest(contract)!=receipt['sha256']:raise ValueError('Access contract hash changed')
    if digest(ROOT/'docs/PROTOCOLO_PANAMA_P1_PROPUESTO_ES.md')!=a['approved_protocol_sha256']:
        raise ValueError('Approved protocol changed')
    if digest(ROOT/'config/protocol_lock_v2.PROPOSED.json')!=a['approved_config_sha256']:
        raise ValueError('Approved specification changed')
    for f in a['source_documents']:
        if digest(ROOT/f['path'])!=f['sha256']:raise ValueError('Access dependency changed')
    v=json.loads((ROOT/'config/protocol_lock_v2.PROPOSED.json').read_text())
    if digest(v['legacy_lock_path'])!=a['legacy_lock_sha256']:raise ValueError('Legacy lock changed')
    # OpenSSL accepts either -queryfile or -data, not both. Verify each binding.
    for binding in [('-queryfile',seal_dir/'request.tsq'),('-data',contract)]:
        p=subprocess.run([str(OPENSSL),'ts','-verify',binding[0],str(binding[1]),
            '-in',str(seal_dir/'response.tsr'),'-CAfile',str(CA)],capture_output=True,text=True)
        if p.returncode:raise ValueError('External signature/imprint/nonce verification failed: '+p.stderr)
    return a

def build_grid():
    import numpy as np
    from pyproj import Geod,Transformer
    c=json.loads((ROOT/'config/protocol_lock_v2.PROPOSED.json').read_text())['region']
    step=c['grid_step_degrees']; lat0=c['center_latitude'];lon0=c['center_longitude']
    geod=Geod(ellps='WGS84');cells=[];maxr=0
    for iy in range(math.floor((lat0-5+90)/step),math.ceil((lat0+5+90)/step)):
        for ix in range(math.floor((lon0-5+180)/step),math.ceil((lon0+5+180)/step)):
            lo=-180+ix*step;la=-90+iy*step
            if geod.inv(lon0,lat0,lo+step/2,la+step/2)[2]>1000*c['reference_radius_km']:continue
            corners=[(lo,la),(lo+step,la),(lo+step,la+step),(lo,la+step)]
            area=abs(geod.polygon_area_perimeter(*zip(*corners))[0])/1e6
            maxr=max(maxr,*[geod.inv(lon0,lat0,x,y)[2]/1000 for x,y in corners])
            cells.append({'ix':ix,'iy':iy,'lon':lo,'lat':la,'area_km2':area})
    proj=f'+proj=aeqd +lat_0={lat0} +lon_0={lon0} +datum=WGS84 +units=m'
    return {'cells':cells,'step':step,'origin':[-180,-90],
        'parent_radius_km':maxr+c['parent_buffer_km'],'projection':proj,
        'center':[lon0,lat0],'model_distance':'local WGS84 AEQD Euclidean km; not a physical stress operator'}

def target_indices(records,grid):
    keys={(r['ix'],r['iy']) for r in grid['cells']};s=grid['step']
    return [i for i,r in enumerate(records) if (math.floor((r['lon']+180)/s),math.floor((r['lat']+90)/s)) in keys]

def capture(output,origin_end):
    """Historical development snapshot, explicitly not a scheduled emission."""
    a=verify_access();end=dt.datetime.fromisoformat(origin_end.replace('Z','+00:00'))
    if end.tzinfo is None or end>now():raise ValueError('Future/naive origin cutoff')
    output=pathlib.Path(output);output.mkdir(parents=True,exist_ok=False)
    grid=build_grid();write_new(output/'grid.json',grid)
    manifest={'status':'CAPTURING_PUBLIC_TRAINING','access_contract_sha256':digest(ROOT/'config/PUBLIC_TRAINING_ACCESS_V2.json'),
        'started_utc':now().isoformat(),'origin_end_exclusive':end.isoformat(),'scheduled_issue_capture':False,
        'provider':'USGS ComCat','licence_url':'https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits',
        'analysis_permission':'public USGS data','redistribution':'source attribution; third-party product exceptions retained',
        'supersession':'never replace raw capture','parser_sha256':digest(__file__),'requests':[],'outcomes_scored':False}
    all_events=[]
    def chunk(start,stop):
        params={'format':'geojson','starttime':start.isoformat(),'endtime':stop.isoformat(),
            'latitude':grid['center'][1],'longitude':grid['center'][0],'maxradiuskm':grid['parent_radius_km'],
            'minmagnitude':3,'mindepth':0,'maxdepth':70,'eventtype':'earthquake','orderby':'time-asc','limit':20000}
        url=a['allowed_provider_prefix']+'query?'+urllib.parse.urlencode(params)
        sent=now();n=len(manifest['requests']);rawpath=output/f'raw_{n:03d}.geojson'
        req=urllib.request.Request(url,headers={'User-Agent':'Article202-private-probabilistic-research/2'})
        with urllib.request.urlopen(req,timeout=60) as r:
            raw=r.read(32*1024*1024+1);headers=dict(r.headers);status=r.status
        received=now();rawpath.write_bytes(raw)
        if len(raw)>32*1024*1024:raise ValueError('Oversized response, no truncation allowed')
        d=json.loads(raw);features=d['features']
        record={'url':url,'sent_utc':sent.isoformat(),'received_utc':received.isoformat(),
            'http_status':status,'headers':headers,'bytes':len(raw),'sha256':digest(rawpath),'path':rawpath.name,
            'returned':len(features),'start_inclusive':start.isoformat(),'end_exclusive':stop.isoformat()}
        manifest['requests'].append(record)
        write_new(output/f'request_{n:03d}.json',record)
        if len(features)>=20000:
            if (stop-start).total_seconds()<1:raise ValueError('Unsplittable service limit')
            mid=start+(stop-start)/2;chunk(start,mid);chunk(mid,stop);return
        # ComCat versions do not all return metadata.count. Cross-check the
        # documented count service, preserving its bytes and retrieval interval.
        cp={k:v for k,v in params.items() if k not in ('format','orderby','limit')}
        count_url=a['allowed_provider_prefix']+'count?'+urllib.parse.urlencode(cp)
        count_sent=now()
        with urllib.request.urlopen(count_url,timeout=60) as cr: count_raw=cr.read(1025)
        count_received=now();count_path=output/f'count_{n:03d}.txt';count_path.write_bytes(count_raw)
        count=int(count_raw.decode('ascii').strip())
        write_new(output/f'count_request_{n:03d}.json',{'url':count_url,'sent_utc':count_sent.isoformat(),
            'received_utc':count_received.isoformat(),'bytes':len(count_raw),'sha256':digest(count_path),'count':count})
        if len(features)!=count:raise ValueError('Independent ComCat count mismatch; preserve and retry a new capture')
        for f in features:
            p=f['properties'];lon,lat,depth=f['geometry']['coordinates'][:3]
            t=dt.datetime.fromtimestamp(p['time']/1000,UTC)
            if not start<=t<stop:continue
            if t>=end or t>received or not 0<=depth<=70:raise ValueError('Origin/depth outside contract')
            if p.get('type')!='earthquake' or p.get('mag') is None or p['mag']<3:raise ValueError('Unexpected event type/magnitude')
            all_events.append({'id':f['id'],'origin_utc':t.isoformat(),'time_ms':p['time'],'mag':p['mag'],
                'magType':p.get('magType'),'lon':lon,'lat':lat,'depth_km':depth,'updated_ms':p.get('updated'),
                'net':p.get('net'),'status':p.get('status'),'received_utc':received.isoformat(),'raw_file':rawpath.name})
    try:
        start=dt.datetime(1990,1,1,tzinfo=UTC)
        while start<end:
            stop=min(end,dt.datetime(min(start.year+5,9999),1,1,tzinfo=UTC));chunk(start,stop);start=stop
        unique={}
        for e in all_events:
            if e['id'] in unique and e!=unique[e['id']]:raise ValueError('Duplicate conflicting ID')
            unique[e['id']]=e
        records=sorted(unique.values(),key=lambda x:(x['time_ms'],x['id']))
        write_new(output/'events.json',records)
        manifest.update(status='COMPLETE_PUBLIC_TRAINING_CAPTURE',events=len(records),events_sha256=digest(output/'events.json'),
            target_events=len(target_indices(records,grid)),grid_sha256=digest(output/'grid.json'))
    except Exception as e:
        manifest.update(status='FAILED_CAPTURE_NO_EMISSION',error=repr(e))
        raise
    finally:
        manifest['finished_utc']=now().isoformat();write_new(output/'capture_manifest.json',manifest)
    return manifest

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('output');p.add_argument('--origin-end',required=True);a=p.parse_args()
    print(json.dumps(capture(a.output,a.origin_end),indent=2))
