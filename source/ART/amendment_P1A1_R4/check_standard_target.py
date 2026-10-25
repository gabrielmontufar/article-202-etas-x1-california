"""Check one explicit R4 standard-magnitude proposal; original audits retained."""
import collections,datetime as dt,json,math,pathlib,sqlite3,sys
ROOT=pathlib.Path(__file__).resolve().parents[1];HERE=pathlib.Path(__file__).resolve().parent
CACHE=pathlib.Path(r'C:\Users\gjm31\forge_cache\panama_probabilistic_20261020\amendment_20261021');OUT=CACHE/'R4'
sys.path.insert(0,str(ROOT/'amendment_P1A1_R3'));from r3_design import guard,sha,write
sys.path.insert(0,str(HERE));from compare_source_catalogues import scedc_rows,ncedc_rows,wilson
STANDARD={'ml','md','mw','mwr','mww','mwc','mwb','mb','mb_lg','mblg','ms','ms_20','ms20','mwp','mi','me','mlr','lr','l','d','dl','w'}
NONSTANDARD={'mh','h'}

def main():
    resources=guard()
    import numpy as np
    sys.path.insert(0,str(ROOT/'amendment_P1A1'));from completeness_epoch import bootstrap_epochs
    assert not (OUT/'R4_STANDARD_TARGET_CHECK.json').exists()
    manifest=json.loads((CACHE/'california_training/CAPTURE_MANIFEST.json').read_text());path=CACHE/'california_training/ANSS_RELM_TRAINING.sqlite'
    assert sha(path)==manifest['database_sha256']
    end=dt.datetime.fromisoformat(manifest['origin_cutoff_exclusive']);endms=round(end.timestamp()*1000)
    starts={'last365':end-dt.timedelta(days=365),'post2024':dt.datetime(2024,1,1,tzinfo=dt.timezone.utc)}
    geo=json.loads((CACHE/'R3/R3_GEOGRAPHIC_MASKS_WITH_NCSN.json').read_text());names=['R3_SCSN_LAND','R3_NCSN_LAND']
    keys={n:{(round((lo+180)*10),round((la+90)*10)) for lo,la in geo['masks'][n]['cells']} for n in names}
    assert not keys[names[0]]&keys[names[1]]
    db=sqlite3.connect(f'file:{path.as_posix()}?mode=ro&immutable=1',uri=True);db.execute('PRAGMA cache_size=-8192')
    maxmag=float(db.execute('SELECT MAX(mag) FROM events').fetchone()[0]);centres=np.arange(10,math.ceil(maxmag*10)+2)/10
    hist={n:{w:np.zeros(((end.year-s.year)*12+end.month-s.month+1,len(centres)),int) for w,s in starts.items()} for n in names}
    unknown=collections.Counter();excluded=collections.Counter();excluded_target=collections.Counter();recent_counts=collections.Counter()
    first=round(starts['post2024'].timestamp()*1000)
    for time_ms,mag,lon,lat,mt in db.execute('SELECT time_ms,mag,lon,lat,mag_type FROM events WHERE time_ms>=? AND time_ms<?',(first,endms)):
        key=(math.floor((lon+180)*10+1e-8),math.floor((lat+90)*10+1e-8))
        region=next((n for n in names if key in keys[n]),None)
        if region is None:continue
        typ=str(mt).lower()
        t=dt.datetime.fromtimestamp(time_ms/1000,dt.timezone.utc)
        if typ in NONSTANDARD:
            excluded[region]+=1
            if t>=starts['last365'] and mag>=2.5:excluded_target[region]+=1
            continue
        if typ not in STANDARD:unknown[typ]+=1;continue
        for w,s in starts.items():
            if t>=s:
                mo=(t.year-s.year)*12+t.month-s.month;mi=int(math.floor(mag*10+.5))-10;hist[region][w][mo,mi]+=1
        if t>=starts['last365'] and mag>=2.5:recent_counts[region]+=1
    results=[]
    for region in names:
        row={'region':region,'recent365_standard_target_count':recent_counts[region],
             'expected90_standard_target':recent_counts[region]*90/365,
             'excluded_nonstandard_training_since2024':excluded[region],
             'excluded_nonstandard_target_last365':excluded_target[region],'recent':{}}
        for w,s in starts.items():
            h=hist[region][w]
            # Same original R4 labels/seeds for paired sensitivity, not a search.
            out=bootstrap_epochs(h,[{'label':w,'first_month':0,'last_month':len(h)}],centres,1.,region+'|R4|'+w,500)
            row['recent'][w]=out
            print('STANDARD_RECENT',region,w,'point',out['global_point'],'upper95',out['proposed_Mstar_from_global_upper95'],flush=True)
        results.append(row)
    oldaudit=json.loads((OUT/'R4_SOURCE_TRANSFER_AUDIT.json').read_text());old_missing={x['source_id']:x for x in oldaudit['discrepancies'] if not x['matched_to_admitted_capture']}
    transfer=[]
    for network,generator,region in [('SCSN',scedc_rows,'R3_SCSN_LAND'),('NCSN',ncedc_rows,'R3_NCSN_LAND')]:
        selected=[];excluded_ref=collections.Counter()
        for r in generator():
            if not starts['post2024']<=r['origin']<end or not 0<=r['depth']<=70 or r['mag']<2.5:continue
            key=(math.floor((r['lon']+180)*10+1e-8),math.floor((r['lat']+90)*10+1e-8))
            if key not in keys[region]:continue
            typ=r['mag_type'].lower()
            if typ in NONSTANDARD:
                excluded_ref['post2024']+=1
                if r['origin']>=starts['last365']:excluded_ref['last365']+=1
                continue
            if typ not in STANDARD:unknown[network+':'+typ]+=1;continue
            # Exact original decision retained; no new proximity association.
            old=db.execute('SELECT mag,mag_type FROM events WHERE id=?',(r['id'],)).fetchone()
            present=old is not None
            if not present and r['id'] not in old_missing:
                # An original alias resolution was positive; reuse it as recorded.
                p=OUT/('ALIAS_'+r['id']+'.json.decoded')
                if p.exists():
                    alias=json.loads(p.read_text());ids=[alias['id']]+[v for v in alias['properties'].get('ids','').split(',') if v]
                    for eid in ids:
                        old=db.execute('SELECT mag,mag_type FROM events WHERE id=?',(eid,)).fetchone()
                        if old is not None:present=True;break
            selected.append({'id':r['id'],'origin':r['origin'].isoformat(),'present':present,'source_mag':r['mag'],
                             'source_type':r['mag_type'],'admitted_mag':old[0] if old else None,'admitted_type':old[1] if old else None,
                             'present_below25':bool(old and old[0]<2.5)})
        windows=[]
        for w,s in starts.items():
            rows=[x for x in selected if dt.datetime.fromisoformat(x['origin'])>=s];n=len(rows);k=sum(x['present'] for x in rows);ci=wilson(k,n)
            windows.append({'window':w,'source_standard_targets':n,'present_in_admitted_capture':k,'presence_fraction':k/n if n else None,
                            'presence_Wilson95':ci,'excluded_nonstandard_reference_targets':excluded_ref[w],
                            'present_below25':sum(x['present_below25'] for x in rows),
                            'gate_same_thresholds':bool(n and k/n>=.99 and ci[0]>=.95),
                            'unresolved_standard_ids':[x['id'] for x in rows if not x['present']]})
        transfer.append({'network':network,'windows':windows,'all_matched_records':selected})
        print('STANDARD_TRANSFER',network,json.dumps(windows),flush=True)
    db.close()
    complete=all(c['threshold_design_qualified'] and c['proposed_Mstar_from_global_upper95']<=2.5 for r in results for c in r['recent'].values()) and not unknown
    transferred=all(w['gate_same_thresholds'] for t in transfer for w in t['windows']) and not unknown
    total=sum(recent_counts.values())
    final={'status':'PROPOSED_STANDARD_TARGET_REVIEW_ONLY','completed_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
           'proposal_rule_sha256':sha(HERE/'R4_STANDARD_MAGNITUDE_PROPOSAL_BEFORE_CHECK_ES.md'),'code_sha256':sha(__file__),
           'source_database_sha256':manifest['database_sha256'],'unknown_types':dict(unknown),'regional_Mc':results,
           'compatible_reference_transfer':transfer,'recent_network_completeness_diagnostics_met':bool(complete),
           'compatible_transfer_gate_met':bool(transferred),'union_recent365_target_count':total,'union_expected90':total*90/365,
           'union_expected90_at_least100':total*90/365>=100,'nonstandard_targets_removed_from_original_count':sum(excluded_target.values()),
           'proposed_design_gates_met':bool(complete and transferred and total*90/365>=100),
           'original_all_type_transfer_failure_preserved':True,'independent_physical_detection_proved':False,
           'joint_uncertainty_and_power_closed':False,'operational_configuration_changed':False,'forecasts_issued':0,'external_seals':0,
           'resources_after':resources()}
    write(OUT/'R4_STANDARD_TARGET_CHECK.json',final)
    print('STANDARD_DESIGN_PROPOSED',final['proposed_design_gates_met'],'N90',final['union_expected90'],'EXCLUDED_TARGETS',final['nonstandard_targets_removed_from_original_count'],'END_RESOURCES',final['resources_after'],flush=True)

if __name__=='__main__':main()
