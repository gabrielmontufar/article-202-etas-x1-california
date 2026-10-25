"""Frozen R4 distributed diagnostic bootstrap; no forecasts or external actions."""
import argparse,contextlib,datetime as dt,hashlib,importlib.metadata,json,math,os,pathlib,shutil,sys,time,traceback
for _key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):os.environ[_key]='1'
BASE=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(BASE));from portable_resources import guard,resources,sha,write
sys.path.insert(0,str(BASE/'project/scripts'))
sys.path.insert(0,str(BASE/'project/amendment_P1A1_R4'))
EPOCH=dt.datetime(1990,1,1,tzinfo=dt.timezone.utc)
EPOCHS=('principal_2024','sensitivity_2016_2023')
WORK=BASE/'work'

def stamp():return dt.datetime.now(dt.timezone.utc).isoformat()
def check_package():
    manifest=json.loads((BASE/'SHA256_MANIFEST.json').read_text())
    for rel,expected in manifest['files'].items():
        path=BASE/rel
        if not path.is_file() or sha(path)!=expected:raise RuntimeError('PACKAGE_HASH_MISMATCH: '+rel)
    for line in (BASE/'requirements.txt').read_text().splitlines():
        if not line or line.startswith('#'):continue
        name,version=line.split('==')
        if importlib.metadata.version(name)!=version:raise RuntimeError('ENVIRONMENT_VERSION_HOLD: '+name)
    return manifest

@contextlib.contextmanager
def mutex():
    WORK.mkdir(exist_ok=True)
    handle=open(WORK/'one_numerical_worker.mutex','a+b');handle.seek(0,2)
    if handle.tell()==0:handle.write(b'0');handle.flush()
    handle.seek(0)
    if sys.platform=='win32':
        import msvcrt
        msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
    else:
        import fcntl
        fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
    try:yield
    finally:
        if sys.platform=='win32':handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
        else:fcntl.flock(handle,fcntl.LOCK_UN)
        handle.close()

def inputs():
    import numpy as np
    from polygon_integration import PolygonIntegrator
    z=np.load(BASE/'inputs/keep_unknown_history.npz',allow_pickle=False)
    h=z['history'];flags=z['target_flags'];support=json.loads((BASE/'inputs/R4_PROPOSED_SUPPORT.json').read_text())
    domain=PolygonIntegrator.from_geographic_cells(support['cells'])
    receipt=json.loads((BASE/'inputs/keep_unknown_receipt.json').read_text())
    assert len(h)==76222 and receipt['target_recent365']==844 and len(domain.cells)==4296
    bounds={
        'principal_2024':((dt.datetime(2024,1,1,tzinfo=dt.timezone.utc)-EPOCH).days,(dt.datetime.fromisoformat(receipt['data_cutoff_exclusive'])-EPOCH).total_seconds()/86400),
        'sensitivity_2016_2023':((dt.datetime(2016,1,1,tzinfo=dt.timezone.utc)-EPOCH).days,(dt.datetime(2024,1,1,tzinfo=dt.timezone.utc)-EPOCH).days)}
    return h,flags,domain,receipt['parent_radius_km'],bounds

def fit_core():
    # The exact Windows numerical function is copied byte-for-byte. Only its
    # resource/write adapter and output root are portable, not its equations.
    import fit_r4_masked_models as fit
    return fit

def validate_fit(result):
    from point_models import ETASParameters,unpack
    if result['status']!='CONDITIONAL_POINT_FIT_NUMERICAL_QA_PASS':raise RuntimeError('REFERENCE_MINIMUM_QA_HOLD')
    rows=result['starts']
    if len(rows)!=8 or sorted(x['start'] for x in rows)!=list(range(8)):raise RuntimeError('REFERENCE_EIGHT_STARTS_HOLD')
    valid=[r for r in rows if r.get('success') and math.isfinite(r.get('nll',math.inf))]
    if not valid:raise RuntimeError('No converged start')
    best=min(valid,key=lambda r:r['nll'])
    if best['start']!=result['selected_start']:raise RuntimeError('Selected start mismatch')
    p=ETASParameters(**result['parameters']).check()
    if p.gamma!=0 or p.m0!=2.5:raise RuntimeError('Bootstrap baseline is explicit gamma=0, m0=2.5')
    reconstructed=unpack(best['x'],m0=2.5)
    from dataclasses import asdict
    if any(not math.isclose(asdict(reconstructed)[key],value,rel_tol=1e-12,abs_tol=1e-14) for key,value in asdict(p).items()):raise RuntimeError('Reference vector mismatch')
    return p,best

def export_reference(epoch,path):
    result=json.loads(path.read_text());p,best=validate_fit(result)
    receipt={'status':'CONDITIONAL_DIAGNOSTIC_GENERATOR_FROZEN_NOT_FORECAST','epoch':epoch,
        'parameters':result['parameters'],'x':best['x'],'nll':result['selected_nll'],
        'reference_result_sha256':sha(path),'input_sha256':sha(BASE/'inputs/keep_unknown_history.npz'),
        'numerical_core_sha256':sha(BASE/'project/amendment_P1A1_R4/fit_r4_masked_models.py'),
        'active_bounds':result['active_bounds'],'utc':stamp(),'operational_HOLD':True,'forecasts_issued':0}
    folder=WORK/'references';folder.mkdir(exist_ok=True);destination=folder/(epoch+'.json')
    if destination.exists():
        old=json.loads(destination.read_text())
        for key in ('parameters','x','reference_result_sha256','input_sha256','numerical_core_sha256'):assert old[key]==receipt[key]
    else:write(destination,receipt)
    print('REFERENCE_CAPSULE',destination,sha(destination),flush=True)

def reference(epoch):
    if epoch!='sensitivity_2016_2023':raise RuntimeError('Cloud reference authorization covers only 2016-2023; import principal from Windows')
    h,flags,domain,radius,bounds=inputs();fit=fit_core();fit.OUT=WORK/'reference_fits';fit.OUT.mkdir(exist_ok=True)
    t0,t1=bounds[epoch]
    fit.fit_one(epoch,h,flags,domain,radius,t0,t1,resources)
    export_reference(epoch,fit.OUT/epoch/'ETAS_FIT_RESULT.json')

def reference_capsule(epoch):
    from point_models import ETASParameters
    path=WORK/'references'/(epoch+'.json')
    if not path.exists():raise RuntimeError('REFERENCE_NOT_READY_HOLD: '+epoch+'; do not invent parameters')
    ref=json.loads(path.read_text())
    assert ref['epoch']==epoch and ref['input_sha256']==sha(BASE/'inputs/keep_unknown_history.npz')
    assert ref['numerical_core_sha256']==sha(BASE/'project/amendment_P1A1_R4/fit_r4_masked_models.py')
    return ETASParameters(**ref['parameters']).check(),path

def simulate_input(epoch,index):
    import numpy as np
    from point_models import Background,simulate_etas
    p,ref=reference_capsule(epoch);h,flags,domain,radius,bounds=inputs();t0,t1=bounds[epoch]
    folder=WORK/'simulations'/epoch;folder.mkdir(parents=True,exist_ok=True)
    path=folder/f'replicate_{index:03d}.npz';receipt_path=folder/f'replicate_{index:03d}.json'
    if path.exists():
        record=json.loads(receipt_path.read_text());assert record['reference_sha256']==sha(ref) and record['sha256']==sha(path)
        return path,record
    if receipt_path.exists():raise RuntimeError('Existing failed simulation retained; no seed substitution')
    label=f'R4_JOINT_PARAMETRIC_20261021|{epoch}|{index-1:03d}'
    seed=int.from_bytes(hashlib.sha256(label.encode()).digest()[:8],'big')
    assert json.loads((BASE/'seeds.json').read_text())[epoch][str(index)]['seed']==seed
    initial=h[h[:,0]<t0];original_targets=h[(h[:,0]>=t0)&(h[:,0]<t1)&flags]
    bg=Background(original_targets[:,1:3],radius)
    generated=simulate_etas(p,initial,bg,t0,t1,seed,max_events=200000)
    future=generated[:,:4];lon,lat=domain.transformer.transform(future[:,1]*1000,future[:,2]*1000,direction='INVERSE')
    keys=list(zip(np.floor((lon+180)*10+1e-8).astype(int),np.floor((lat+90)*10+1e-8).astype(int)))
    future_flags=np.array([key in domain.cells for key in keys],bool)
    initial_flags=flags[h[:,0]<t0]
    with path.open('xb') as f:np.savez_compressed(f,history=np.r_[initial,future],target_flags=np.r_[initial_flags,future_flags])
    record={'status':'SIMULATED_DIAGNOSTIC_INPUT','epoch':epoch,'replicate':index,'seed':seed,'seed_label':label,
        'sha256':sha(path),'reference_sha256':sha(ref),'conditioned_events':len(initial),'simulated_events':len(future),
        'simulated_target_events':int(future_flags.sum()),'utc':stamp(),'not_a_real_forecast':True}
    write(receipt_path,record);return path,record

def bootstrap_one(epoch,index,shared):
    import numpy as np
    p,ref=reference_capsule(epoch)
    if shared:
        if index!=1:raise RuntimeError('Only replicate 1 of each epoch is the fixed shared equivalence check')
        path=WORK/'simulations'/epoch/f'replicate_{index:03d}.npz'
        record=json.loads(path.with_suffix('.json').read_text())
        assert record['reference_sha256']==sha(ref) and sha(path)==record['sha256'],'Shared input must be transferred unchanged'
    else:path,record=simulate_input(epoch,index)
    z=np.load(path,allow_pickle=False);h,flags=z['history'],z['target_flags'];_,_,domain,radius,bounds=inputs();t0,t1=bounds[epoch]
    fit=fit_core();fit.OUT=WORK/('shared_checks' if shared else 'bootstrap')/epoch;fit.OUT.mkdir(parents=True,exist_ok=True)
    result=fit.fit_one(f'replicate_{index:03d}',h,flags,domain,radius,t0,t1,resources)
    folder=fit.OUT/f'replicate_{index:03d}'
    if not (folder/'BOOTSTRAP_RECEIPT.json').exists():
        write(folder/'BOOTSTRAP_RECEIPT.json',{'epoch':epoch,'replicate':index,'simulation_sha256':sha(path),
            'reference_sha256':sha(ref),'result_sha256':sha(folder/'ETAS_FIT_RESULT.json'),
            'status':result['status'],'shared_equivalence_only':shared,'utc':stamp(),'forecasts_issued':0,'operational_HOLD':True})

def run_range(args):
    if not 1<=args.start<=args.stop<=200:raise ValueError('Indices are 1..200 inclusive')
    if not args.shared_check:
        if args.role=='local' and args.stop>100:raise RuntimeError('Local assignment is 1..100')
        if args.role=='cloud' and args.start<101:raise RuntimeError('Cloud assignment is 101..200; shared check 1 must be explicit')
    elif args.start!=1 or args.stop!=1:raise RuntimeError('Exactly one shared index per epoch')
    epochs=EPOCHS if args.epoch=='both' else (args.epoch,)
    # Fail before executing either epoch if any required reference is absent.
    for epoch in epochs:reference_capsule(epoch)
    for epoch in epochs:
        for index in range(args.start,args.stop+1):
            current=resources()
            if current['free_RAM_MiB']<512 or current['free_disk_GiB']<4:raise RuntimeError('RESOURCE_HOLD_BEFORE_REPLICATE')
            parent=WORK/('shared_checks' if args.shared_check else 'bootstrap')/epoch;parent.mkdir(parents=True,exist_ok=True)
            failure=parent/f'replicate_{index:03d}_FAILURE.json'
            if failure.exists():print('RETAINED_FAILURE',epoch,index,flush=True);continue
            try:bootstrap_one(epoch,index,args.shared_check)
            except Exception as error:
                if isinstance(error,MemoryError) or 'RESOURCE_HOLD' in str(error):
                    write(parent/f'replicate_{index:03d}_RESOURCE_HOLD_{time.time_ns()}.json',{'epoch':epoch,'replicate':index,'error':repr(error),'utc':stamp(),'same_seed_checkpoint_resume_only':True})
                    raise
                write(failure,{'epoch':epoch,'replicate':index,'error':repr(error),'traceback':traceback.format_exc(),
                    'utc':stamp(),'failed_replicate_not_replaced':True,'forecasts_issued':0})
                print('FAILED_REPLICATE_RETAINED',epoch,index,repr(error),flush=True)
    print('ASSIGNED_RANGE_FINISHED_NOT_GLOBAL_UNCERTAINTY',flush=True)

def main():
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('verify')
    p=sub.add_parser('reference');p.add_argument('--epoch',choices=EPOCHS,required=True)
    p=sub.add_parser('export-reference');p.add_argument('--epoch',choices=EPOCHS,required=True);p.add_argument('--result',type=pathlib.Path,required=True)
    p=sub.add_parser('generate-shared');p.add_argument('--epoch',choices=EPOCHS,required=True)
    p=sub.add_parser('bootstrap');p.add_argument('--epoch',choices=(*EPOCHS,'both'),required=True);p.add_argument('--role',choices=['local','cloud'],required=True)
    p.add_argument('--start',type=int,required=True);p.add_argument('--stop',type=int,required=True);p.add_argument('--shared-check',action='store_true')
    args=parser.parse_args();check_package()
    if args.command=='verify':print('STATIC_PACKAGE_AND_PINNED_ENVIRONMENT_PASS');return
    guard()
    with mutex():
        write(WORK/('INVOCATION_'+str(time.time_ns())+'.json'),{'arguments':sys.argv[1:],'utc':stamp(),'pid':os.getpid(),'environment':{name:importlib.metadata.version(name) for name in ('numpy','scipy','pyproj')},'forecasts_issued':0,'operational_HOLD':True})
        if args.command=='reference':reference(args.epoch)
        elif args.command=='export-reference':export_reference(args.epoch,args.result)
        elif args.command=='generate-shared':path,record=simulate_input(args.epoch,1);print('TRANSFER_SHARED_INPUT_AND_RECEIPT',path,record['sha256'])
        else:run_range(args)
if __name__=='__main__':main()
