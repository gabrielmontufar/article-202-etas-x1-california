"""Training-only native-catalogue transfer audit; aliases bounded, no scores."""
import collections,csv,datetime as dt,json,math,pathlib,sqlite3,sys,urllib.parse
ROOT=pathlib.Path(__file__).resolve().parents[1];HERE=pathlib.Path(__file__).resolve().parent
CACHE=pathlib.Path(r'C:\Users\gjm31\forge_cache\panama_probabilistic_20261020\amendment_20261021');OUT=CACHE/'R4'
sys.path.insert(0,str(ROOT/'amendment_P1A1_R3'));from r3_design import guard,sha,write
sys.path.insert(0,str(HERE));from fetch_support import fetch
UTC=dt.timezone.utc

def wilson(k,n):
    if not n:return [None,None]
    z=1.959963984540054;p=k/n;d=1+z*z/n
    c=(p+z*z/(2*n))/d;h=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return [c-h,c+h]

def scedc_rows():
    for year in [2024,2025,2026]:
        p=OUT/f'SCEDC_{year}.catalog.decoded'
        for ln,line in enumerate(p.read_text().splitlines(),1):
            if not line.strip() or line.startswith('#'):continue
            c=line.split()
            if len(c)!=13:raise ValueError(f'Unrecognized SCEDC format {p.name}:{ln}')
            if c[2]!='eq':continue
            yield {'id':'ci'+str(int(c[10])),'origin':dt.datetime.fromisoformat(c[0].replace('/','-')+'T'+c[1]).replace(tzinfo=UTC),
                   'mag':float(c[4]),'mag_type':c[5],'lat':float(c[6]),'lon':float(c[7]),'depth':float(c[8]),
                   'source_file':p.name,'line':ln}

def ncedc_rows():
    p=OUT/'NCEDC_M25_2024_CUTOFF.txt.decoded'
    for ln,line in enumerate(p.read_text().splitlines(),1):
        if not line.strip() or line.startswith('#'):continue
        c=line.split('|')
        if len(c)<14:raise ValueError('Unrecognized FDSN text record')
        if c[13].strip().lower()!='earthquake':continue
        yield {'id':'nc'+str(int(c[0])),'origin':dt.datetime.fromisoformat(c[1]).replace(tzinfo=UTC),
               'mag':float(c[10]),'mag_type':c[9],'lat':float(c[2]),'lon':float(c[3]),'depth':float(c[4]),
               'source_file':p.name,'line':ln}

def main():
    resources=guard();assert not (OUT/'R4_SOURCE_TRANSFER_AUDIT.json').exists()
    rules=HERE/'R4_SOURCE_TRANSFER_RULES_BEFORE_MATCHING_ES.md'
    m=json.loads((CACHE/'california_training/CAPTURE_MANIFEST.json').read_text());path=CACHE/'california_training/ANSS_RELM_TRAINING.sqlite'
    assert sha(path)==m['database_sha256']
    end=dt.datetime.fromisoformat(m['origin_cutoff_exclusive']);start=dt.datetime(2024,1,1,tzinfo=UTC);recent=end-dt.timedelta(days=365)
    geo=json.loads((CACHE/'R3/R3_GEOGRAPHIC_MASKS_WITH_NCSN.json').read_text())
    mask={name:{(round((lo+180)*10),round((la+90)*10)) for lo,la in geo['masks'][name]['cells']} for name in ['R3_SCSN_LAND','R3_NCSN_LAND']}
    db=sqlite3.connect(f'file:{path.as_posix()}?mode=ro&immutable=1',uri=True);db.execute('PRAGMA cache_size=-8192')
    reports=[];discrepancies=[]
    for network,generator,region in [('SCSN',scedc_rows,'R3_SCSN_LAND'),('NCSN',ncedc_rows,'R3_NCSN_LAND')]:
        selected=[];negative=[];seen=set();alias_requests=0
        for record in generator():
            if not start<=record['origin']<end or record['mag']<2.5:continue
            key=(math.floor((record['lon']+180)*10+1e-8),math.floor((record['lat']+90)*10+1e-8))
            if key not in mask[region]:continue
            if -5<=record['depth']<0:negative.append(record);continue
            if not 0<=record['depth']<=70:continue
            if record['id'] in seen:raise ValueError('Duplicate source ID')
            seen.add(record['id'])
            old=db.execute('SELECT id,time_ms,mag,depth,lon,lat,mag_type FROM events WHERE id=?',(record['id'],)).fetchone()
            aliases=[];alias_error=None
            if old is None and alias_requests<30:
                alias_requests+=1
                name='ALIAS_'+record['id']+'.json'
                url='https://earthquake.usgs.gov/fdsnws/event/1/query?'+urllib.parse.urlencode({'eventid':record['id'],'format':'geojson'})
                try:
                    data=json.loads(fetch(url,name,1024**2))
                    aliases=[data['id']]+[x for x in data['properties'].get('ids','').split(',') if x]
                    for eventid in aliases:
                        old=db.execute('SELECT id,time_ms,mag,depth,lon,lat,mag_type FROM events WHERE id=?',(eventid,)).fetchone()
                        if old is not None:break
                except Exception as e:alias_error=repr(e)
            matched=old is not None
            detail={'network':network,'source_id':record['id'],'source_origin':record['origin'].isoformat(),
                    'source_mag':record['mag'],'source_mag_type':record['mag_type'],'source_depth':record['depth'],
                    'source_file':record['source_file'],'source_line':record['line'],'matched_to_admitted_capture':matched,
                    'aliases_resolved_now_not_historical_vintage':aliases,'alias_error':alias_error}
            if matched:
                oldkey=(math.floor((old[4]+180)*10+1e-8),math.floor((old[5]+90)*10+1e-8))
                detail.update(admitted_id=old[0],admitted_mag=old[2],admitted_depth=old[3],admitted_mag_type=old[6],
                              admitted_in_reference_mask=oldkey in mask[region],
                              magnitude_below25=old[2]<2.5,origin_difference_seconds=old[1]/1000-record['origin'].timestamp())
            selected.append(detail)
            if not matched or detail.get('magnitude_below25') or not detail.get('admitted_in_reference_mask',True):
                discrepancies.append(detail)
        windows=[]
        for label,first in [('post2024',start),('last365',recent)]:
            rows=[x for x in selected if dt.datetime.fromisoformat(x['source_origin'])>=first]
            n=len(rows);k=sum(x['matched_to_admitted_capture'] for x in rows);ci=wilson(k,n)
            windows.append({'window':label,'source_target_records':n,'present_in_admitted_capture':k,
                            'presence_fraction':k/n if n else None,'presence_Wilson95':ci,
                            'unresolved_count':n-k,'present_but_mag_below25':sum(x.get('magnitude_below25',False) for x in rows),
                            'present_but_coordinates_outside_mask':sum(x['matched_to_admitted_capture'] and not x.get('admitted_in_reference_mask',True) for x in rows),
                            'negative_source_depth_excluded_from_original_target':sum(r['origin']>=first for r in negative),
                            'proposed_transfer_integrity_gate':bool(n and k/n>=.99 and ci[0]>=.95)})
        reports.append({'network':network,'windows':windows,'alias_requests':alias_requests,
                        'negative_source_depths':[dict(r,origin=r['origin'].isoformat()) for r in negative],
                        'negative_depth_unobserved_due_to_source_query':network=='NCSN'})
        print('TRANSFER',network,json.dumps(windows),flush=True)
    db.close()
    obj={'status':'SOURCE_TRANSFER_DIAGNOSTIC_NOT_PHYSICAL_DETECTION_PROOF','completed_utc':dt.datetime.now(UTC).isoformat(),
         'rules_sha256':sha(rules),'code_sha256':sha(__file__),'source_database_sha256':m['database_sha256'],
         'networks':reports,'discrepancies':discrepancies,'all_proposed_transfer_integrity_gates_met':all(w['proposed_transfer_integrity_gate'] for n in reports for w in n['windows']),
         'independent_detection_assumption':False,'source_catalogues_derived_from_same_networks':True,
         'magnitude_threshold_definition_closed':False,'forecasts_issued':0,'scores_computed':0,'resources_after':resources()}
    write(OUT/'R4_SOURCE_TRANSFER_AUDIT.json',obj)
    print('END_RESOURCES',obj['resources_after'],flush=True)

if __name__=='__main__':main()
