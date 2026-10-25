"""One guarded worker for original-lineage masked ETAS fits and QA checkpoints."""
import collections,ctypes,datetime as dt,json,math,os,pathlib,sqlite3,sys,time
ROOT=pathlib.Path(__file__).resolve().parents[1];HERE=pathlib.Path(__file__).resolve().parent
CACHE=pathlib.Path(r'C:\Users\gjm31\forge_cache\panama_probabilistic_20261020\amendment_20261021')
OUT=CACHE/'R4/masked_fits_20261021';PARENT=CACHE/'R4/parent_band_20261021_geodesic'
AUTHORIZED_ID='nc71112204'
TREATMENT=None
sys.path.insert(0,str(ROOT/'amendment_P1A1_R3'));from r3_design import guard,sha,write
EPOCH=dt.datetime(1990,1,1,tzinfo=dt.timezone.utc)

def read_events(path):
    db=sqlite3.connect(f'file:{path.as_posix()}?mode=ro&immutable=1',uri=True);db.execute('PRAGMA cache_size=-8192')
    for row in db.execute('SELECT id,time_ms,mag,lon,lat,depth,mag_type FROM events WHERE mag>=2.5 ORDER BY time_ms,id'):yield row
    db.close()

def prepare():
    import numpy as np
    from polygon_integration import PolygonIntegrator
    from check_standard_target import STANDARD,NONSTANDARD
    manifest=json.loads((PARENT/'CAPTURE_MANIFEST.json').read_text());assert manifest['status']=='COMPLETE_PUBLIC_PARENT_BAND'
    assert sha(PARENT/'R4_PARENT_TRAINING.sqlite')==manifest['database_sha256']
    original=CACHE/'california_training/ANSS_RELM_TRAINING.sqlite'
    original_manifest=json.loads((original.parent/'CAPTURE_MANIFEST.json').read_text())
    assert sha(original)==original_manifest['database_sha256']
    relm=json.loads((CACHE/'CALIFORNIA_RELM_MASK.json').read_text())
    relm_keys={(round((lo+180)*10),round((la+90)*10)) for lo,la in relm['cells']}
    support=json.loads((HERE/'R4_PROPOSED_SUPPORT.json').read_text())
    domain=PolygonIntegrator.from_geographic_cells(support['cells'])
    events={};excluded=collections.Counter();unknown=collections.Counter();legacy=collections.Counter();authorized=[]
    def key(row):return (math.floor((row[3]+180)*10+1e-8),math.floor((row[4]+90)*10+1e-8))
    def add(row,label):
        typ=str(row[6]).lower()
        if typ in NONSTANDARD:excluded[label+'|'+typ]+=1;return
        if typ not in STANDARD:
            if TREATMENT in ('keep_unknown','drop_unknown') and typ in {'mc','ma'}:
                # Literal diagnostic marks, NOT additions to STANDARD.
                legacy[label+'|'+typ]+=1
            elif TREATMENT in ('keep_unknown','drop_unknown') and row[0]==AUTHORIZED_ID and typ=='':
                if row[2]!=3.2 or row[1]!=1586628140750:raise RuntimeError('Authorized original record identity changed')
                authorized.append({'source':label,'id':row[0],'mag':row[2],'mag_type':row[6],'time_ms':row[1]})
                if TREATMENT=='drop_unknown':excluded[label+'|authorized_id_drop']+=1;return
            else:unknown[label+'|'+typ]+=1;return
        if row[0] in events and events[row[0]]!=row:raise RuntimeError('Cross-source conflicting duplicate outside deterministic priority')
        events[row[0]]=row
    # This priority is fixed before fits, not selected by performance.
    for r in read_events(original):add(r,'original_RELM')
    for r in read_events(PARENT/'R4_PARENT_TRAINING.sqlite'):
        year=dt.datetime.fromtimestamp(r[1]/1000,dt.timezone.utc).year
        if year<1995 or key(r) not in relm_keys:add(r,'new_parent_band')
    if unknown:raise RuntimeError('Unknown magnitude types: '+json.dumps(unknown))
    if TREATMENT is not None and len(authorized)!=1:raise RuntimeError('Expected exactly one original authorized unknown record')
    rows=sorted(events.values(),key=lambda r:(r[1],r[0]));del events
    lon=np.array([r[3] for r in rows]);lat=np.array([r[4] for r in rows])
    x,y=domain.transformer.transform(lon,lat)
    h=np.c_[(np.array([r[1] for r in rows])-EPOCH.timestamp()*1000)/86400000,x/1000,y/1000,[r[2] for r in rows]]
    flags=np.array([key(r) in domain.cells for r in rows])
    within=np.linalg.norm(h[:,1:3],axis=1)<=manifest['parent_radius_km']
    if not np.all(within):raise RuntimeError('An original RELM event falls outside declared parent domain')
    cutoff=dt.datetime.fromisoformat(manifest['origin_cutoff_exclusive']);end=(cutoff-EPOCH).total_seconds()/86400
    last365=(h[:,0]>=end-365)&flags
    if int(last365.sum())!=844:raise RuntimeError('Original target rate changed; do not silently revise R4')
    provenance={'status':'ORIGINAL_TARGET_LINEAGE_PRESERVED_PARENT_BAND_COMPLETE','utc':dt.datetime.now(dt.timezone.utc).isoformat(),
        'original_database_sha256':original_manifest['database_sha256'],'parent_database_sha256':manifest['database_sha256'],
        'parent_radius_km':manifest['parent_radius_km'],'history_events':len(h),'target_recent365':int(last365.sum()),
        'target_cells':len(domain.cells),'boundary_edges':len(domain.starts),'area_km2':domain.area,
        'excluded_nonstandard':dict(excluded),'unknown_types':dict(unknown),'literal_legacy_diagnostic_marks':dict(legacy),
        'authorized_original_unknown':authorized,'event_treatment':TREATMENT,'operational_magnitude_admission':False,
        'magnitude_types_reclassified':False,'target_version_replaced':False,
        'data_cutoff_exclusive':cutoff.isoformat(),'public_known_training_only':True,'forecasts':0}
    if not (OUT/'PREPARED_DATA_RECEIPT.json').exists():
        with (OUT/'prepared_history.npz').open('xb') as f:np.savez_compressed(f,history=h,target_flags=flags,ids=np.array([r[0] for r in rows]),mag_types=np.array([r[6] for r in rows]))
        provenance['prepared_npz_sha256']=sha(OUT/'prepared_history.npz');write(OUT/'PREPARED_DATA_RECEIPT.json',provenance)
    else:
        old=json.loads((OUT/'PREPARED_DATA_RECEIPT.json').read_text());assert old['original_database_sha256']==provenance['original_database_sha256'] and old['parent_database_sha256']==provenance['parent_database_sha256'] and old.get('event_treatment')==TREATMENT
        assert sha(OUT/'prepared_history.npz')==old['prepared_npz_sha256']
    return h,flags,domain,manifest['parent_radius_km'],end

def spatial_qa(domain,h):
    import numpy as np
    # Fixed quantile indices before looking at mass error; include both sides
    # of boundaries and multiple scales/q across the original parameter range.
    ix=np.unique(np.linspace(0,len(h)-1,32,dtype=int));parents=h[ix,1:3]
    checks=[]
    for d,q in ((.5,1.01),(.5,3.),(5.,1.8),(50.,1.01),(50.,3.)):
        value=domain.masses(parents,d,q,order=32)
        reference=np.array([domain.full_edge_mass(p,d,q,order=256) for p in parents])
        error=np.abs(value-reference);tolerance=1e-5+1e-3*np.abs(reference)
        check={'d0':d,'q':q,'maximum_absolute_mass_error':float(error.max()),'maximum_error_tolerance_ratio':float((error/tolerance).max()),'pass':bool(np.all(error<=tolerance))}
        checks.append(check);print('REAL_MASK_QA',check,flush=True)
    receipt={'status':'PASS' if all(r['pass'] for r in checks) else 'FAIL','checks':checks,'selection':'32 fixed time-quantile parents','utc':dt.datetime.now(dt.timezone.utc).isoformat()}
    write(OUT/'REAL_MASK_QA.json',receipt)
    if receipt['status']!='PASS':raise RuntimeError('Real-mask integration QA failed; no real fit')

def fit_one(name,h,flags,domain,radius,t0,t1,resources):
    import numpy as np
    from scipy.optimize import minimize
    from scipy.stats import qmc
    from point_models import FIT_BOUNDS,unpack
    from r4_likelihood import MaskedLikelihood
    from dataclasses import asdict
    folder=OUT/name;folder.mkdir(exist_ok=True)
    path=folder/'ETAS_FIT_RESULT.json'
    if path.exists():return json.loads(path.read_text())
    selected=h[:,0]<t1;likelihood=MaskedLikelihood(h[selected],flags[selected],domain,radius,t0,t1,order=16)
    results=[];log=folder/'progress.jsonl';design=qmc.Sobol(9,scramble=True,seed=20261020).random_base2(3)
    with log.open('a',encoding='utf8',buffering=1) as stream:
      for j,u in enumerate(design):
        checkpoint=folder/f'start_{j:02d}.json'
        if checkpoint.exists():results.append(json.loads(checkpoint.read_text()));continue
        current_resources=resources()
        if current_resources['free_RAM_MiB']<512 or current_resources['free_disk_GiB']<4:
            raise RuntimeError('RESOURCE_HOLD_BEFORE_NEXT_START: '+json.dumps(current_resources))
        first=time.monotonic();calls=0
        def objective(x):
            nonlocal calls
            calls+=1;p=unpack(x,m0=2.5);value,g=likelihood.value_gradient(p)
            stream.write(json.dumps({'start':j,'call':calls,'elapsed_seconds':time.monotonic()-first,'nll':value,'x':x.tolist(),'raw_gradient_max':float(np.max(np.abs(g))),'utc':dt.datetime.now(dt.timezone.utc).isoformat()})+'\n')
            if calls==1 or calls%10==0:print('FIT',name,'start',j,'call',calls,'nll',value,'elapsed',round(time.monotonic()-first),flush=True)
            return value,g
        x=np.array([a+(b-a)*v for (a,b),v in zip(FIT_BOUNDS,u)])
        try:
            opt=minimize(objective,x,jac=True,method='L-BFGS-B',bounds=FIT_BOUNDS,options={'maxiter':1000,'maxfun':20000,'ftol':1e-10,'gtol':1e-5})
            row={'start':j,'success':bool(opt.success),'message':str(opt.message),'nll':float(opt.fun),'x':opt.x.tolist(),
                 'iterations':int(opt.nit),'calls':calls,'elapsed_seconds':time.monotonic()-first,
                 'active_bounds':[k for k,(v,(a,b)) in enumerate(zip(opt.x,FIT_BOUNDS)) if min(v-a,b-v)<1e-5],
                 'raw_gradient_max':float(np.max(np.abs(opt.jac)))}
        except Exception as e:
            row={'start':j,'success':False,'error':repr(e),'calls':calls,'elapsed_seconds':time.monotonic()-first}
        write(checkpoint,row);results.append(row);print('FIT_START_DONE',name,j,row['success'],flush=True)
    valid=[r for r in results if r['success'] and math.isfinite(r['nll'])]
    if not valid:
        result={'status':'ALL_EIGHT_STARTS_FAILED','starts':results,'epoch':name,'full_uncertainty_closed':False};write(path,result);return result
    best=min(valid,key=lambda r:r['nll']);p=unpack(best['x'],m0=2.5)
    # Keep order-16 minimum and compare higher-order evaluators, never replace
    # it with a numerically incompatible apparently better solution.
    original_value=likelihood.value_gradient(p)[0];refinements=[]
    for order in (32,64):
        likelihood.order=order;v=likelihood.value_gradient(p)[0]
        refinements.append({'order':order,'nll':v,'absolute_delta_per_target':abs(v-original_value)/len(likelihood.ev)})
    refined=domain.from_geographic_cells([[ix/10-180,iy/10-90] for ix,iy in sorted(domain.cells)],subdivide=2)
    refined_likelihood=MaskedLikelihood(h[selected],flags[selected],refined,radius,t0,t1,order=64)
    vg=refined_likelihood.value_gradient(p)[0]
    refinements.append({'order':64,'geographic_subdivision':2,'nll':vg,'absolute_delta_per_target':abs(vg-original_value)/len(likelihood.ev)})
    passed=all(r['absolute_delta_per_target']<=1e-3 for r in refinements)
    result={'status':'CONDITIONAL_POINT_FIT_NUMERICAL_QA_PASS' if passed else 'MINIMUM_FAILED_REFINED_NUMERICAL_REPRODUCTION',
        'epoch':name,'training_t0_days':t0,'training_t1_days':t1,'target_events':len(likelihood.ev),'parents_kept':len(likelihood.h),
        'parameters':asdict(p),'starts':results,'selected_start':best['start'],'selected_nll':best['nll'],
        'active_bounds':best['active_bounds'],'refinements':refinements,'full_uncertainty_closed':False,
        'joint_parameter_bootstrap_replicates_completed':0,'historical_incompleteness_confound_acknowledged':name=='sensitivity_2016_2023',
        'ETAS_X1_power_established':False,'forecasts_issued':0,'utc':dt.datetime.now(dt.timezone.utc).isoformat()}
    write(path,result)
    if passed:
        m2=likelihood.covariate_measure(2);m4=likelihood.covariate_measure(4)
        comparisons=[{'gamma':g,'order2':float(m2[1]@np.exp(g*m2[0])),'order4':float(m4[1]@np.exp(g*m4[0]))} for g in (-1,-.5,0,.5,1)]
        ok=all(abs(r['order2']-r['order4'])<=1e-5+.005*abs(r['order4']) for r in comparisons)
        write(folder/'X1_INTEGRATION_QA.json',{'status':'PASS' if ok else 'FAIL','comparisons':comparisons,'renormalized_to_unit_target_mass':False})
        if ok:
            x1,runs=likelihood.fit_gamma(p,m4)
            write(folder/'X1_FIT_RESULT.json',{'parameters':asdict(x1),'starts':runs,'status':'CONDITIONAL_GAMMA_FIT_NOT_SKILL','full_uncertainty_closed':False})
    return result

def main():
    global OUT,TREATMENT
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--diagnostic-authorized',action='store_true',required=True)
    parser.add_argument('--event-treatment',choices=['keep_unknown','drop_unknown'],required=True)
    parser.add_argument('--stage',choices=['prepare','point'],default='point')
    args=parser.parse_args();TREATMENT=args.event_treatment
    resources=guard();OUT=CACHE/'R4/masked_diagnostic_authorized_20261021'/TREATMENT
    OUT.mkdir(parents=True,exist_ok=True);sys.path.insert(0,str(ROOT/'scripts'));sys.path.insert(0,str(HERE))
    import msvcrt
    # Common lock across the two diagnostic treatments: never two fits at once.
    lock=open(OUT.parent/'worker.mutex','a+b');lock.seek(0,2)
    if lock.tell()==0:lock.write(b'0');lock.flush()
    lock.seek(0)
    try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:raise RuntimeError('Own masked worker already active; never duplicate')
    try:
        (OUT/'ACTIVE_WORKER.json').write_text(json.dumps({'pid':os.getpid(),'started_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'status':'RUNNING','priority':'BelowNormal','threads':1,'event_treatment':TREATMENT,'diagnostic_only':True,'operational_HOLD':True},indent=2))
        files=[pathlib.Path(__file__),ROOT/'scripts/r4_likelihood.py',ROOT/'scripts/polygon_integration.py',ROOT/'scripts/point_models.py',HERE/'R4_DIAGNOSTIC_AUTHORIZATION_AND_EVENT_SENSITIVITY_ES.md']
        source_hashes={str(p):sha(p) for p in files}
        if not (OUT/'CODE_AND_AUTHORIZATION_RECEIPT.json').exists():
            write(OUT/'CODE_AND_AUTHORIZATION_RECEIPT.json',{'utc':dt.datetime.now(dt.timezone.utc).isoformat(),'files':{str(p):sha(p) for p in files},'event_treatment':TREATMENT,'diagnostic_only':True,'forecasts_issued':0})
        else:
            assert json.loads((OUT/'CODE_AND_AUTHORIZATION_RECEIPT.json').read_text())['files']==source_hashes,'Do not resume checkpoints under changed source'
        h,flags,domain,radius,end=prepare()
        if args.stage=='prepare':
            (OUT/'ACTIVE_WORKER.json').write_text(json.dumps({'pid':os.getpid(),'status':'PREPARATION_ONLY_DIAGNOSTIC_HOLD','event_treatment':TREATMENT,'forecasts_issued':0,'utc':dt.datetime.now(dt.timezone.utc).isoformat()}))
            print('DIAGNOSTIC_PREPARATION_COMPLETED',TREATMENT,'history',len(h),flush=True);return
        if not (OUT/'REAL_MASK_QA.json').exists():spatial_qa(domain,h)
        else:assert json.loads((OUT/'REAL_MASK_QA.json').read_text())['status']=='PASS'
        epochs=[('principal_2024',(dt.datetime(2024,1,1,tzinfo=dt.timezone.utc)-EPOCH).days,end),
                ('sensitivity_2016_2023',(dt.datetime(2016,1,1,tzinfo=dt.timezone.utc)-EPOCH).days,(dt.datetime(2024,1,1,tzinfo=dt.timezone.utc)-EPOCH).days)]
        summary=[]
        for name,t0,t1 in epochs:summary.append(fit_one(name,h,flags,domain,radius,t0,t1,resources))
        write(OUT/'R4_ETAS_CONDITIONAL_FIT_SUMMARY.json',{'epochs':summary,'full_parameter_stability_identified':False,
            'reason':'Point fits do not substitute the prescribed joint parameter uncertainty or remove historical observation confounding',
            'bootstrap_200_per_epoch_completed':False,'event_treatment':TREATMENT,'diagnostic_only':True,'operational_HOLD':True,'forecasts_issued':0,'resources_after':resources()})
        (OUT/'ACTIVE_WORKER.json').write_text(json.dumps({'pid':os.getpid(),'status':'FINITE_POINT_FIT_QUEUE_FINISHED','utc':dt.datetime.now(dt.timezone.utc).isoformat()}))
    except Exception as e:
        write(OUT/f'FAILURE_{os.getpid()}.json',{'error':repr(e),'utc':dt.datetime.now(dt.timezone.utc).isoformat(),'forecasts_issued':0})
        (OUT/'ACTIVE_WORKER.json').write_text(json.dumps({'pid':os.getpid(),'status':'FAILED_RETAINED','error':repr(e)}));raise
    finally:
        lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1);lock.close()

if __name__=='__main__':main()
