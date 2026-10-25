"""Authorized numerical backend plus one reference-initialized bootstrap fit.

Reference fitting remains the untouched eight-Sobol-start implementation.
"""
import datetime as dt,hashlib,json,math,os,pathlib,sys,time
from dataclasses import asdict
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):
    with path.open('x',encoding='utf8') as f:json.dump(value,f,indent=2,allow_nan=False)
def install_backend(folder,threads):
    sys.path.insert(0,str(folder))
    import importlib.metadata,numba
    from polygon_integration import PolygonIntegrator
    from r4_likelihood import MaskedLikelihood
    import fast_polygon,fast_trigger
    if importlib.metadata.version('numba')!='0.68.0':raise RuntimeError('Wrong Numba version')
    numba.set_num_threads(threads)
    if not hasattr(PolygonIntegrator,'_masses_original'):PolygonIntegrator._masses_original=PolygonIntegrator.masses
    PolygonIntegrator.masses=fast_polygon.masses_fast
    metadata={'profile':'R4_NUMBA_068_WARM_REFERENCE_START1','numba':'0.68.0',
        'llvmlite':importlib.metadata.version('llvmlite'),'threads':threads,'fastmath':False,
        'files':{name:sha(folder/name) for name in ('fast_trigger.py','fast_polygon.py')},'bootstrap_starts':1,'reference_starts':8}
    if getattr(MaskedLikelihood.value_gradient,'_r4_backend_manifest',None)==metadata:return metadata
    MaskedLikelihood.value_gradient=fast_trigger.value_gradient_fast
    MaskedLikelihood.value_gradient._r4_backend_manifest=metadata
    return metadata

def fit_single_reference_start(folder,history,flags,domain,radius,t0,t1,reference,resources,simulation_sha256,profile_sha256):
    import numpy as np
    from scipy.optimize import minimize
    from point_models import FIT_BOUNDS,unpack
    from r4_likelihood import MaskedLikelihood
    folder.mkdir(parents=True,exist_ok=True)
    context={'reference':reference,'simulation_sha256':simulation_sha256,'profile_sha256':profile_sha256,'starts':1}
    context_path=folder/'SINGLE_REFERENCE_START_CONTEXT.json'
    if context_path.exists():assert json.loads(context_path.read_text())==context,'Changed generator/input/profile; do not mix checkpoints'
    else:write(context_path,context)
    destination=folder/'ETAS_FIT_RESULT.json'
    if destination.exists():
        old=json.loads(destination.read_text());assert old.get('bootstrap_initializations')==1;return old
    h=history[history[:,0]<t1];selected=flags[history[:,0]<t1]
    L=MaskedLikelihood(h,selected,domain,radius,t0,t1,order=16)
    x0=np.array(reference['x'],float)
    if len(x0)!=9 or any(not a<=v<=b for v,(a,b) in zip(x0,FIT_BOUNDS)):raise RuntimeError('Reference vector outside unchanged bounds')
    started=time.monotonic();calls=0;checkpoint=folder/'start_00.json'
    log=folder/'progress.jsonl';memo={}
    if log.exists():
        for line in log.read_text().splitlines():
            row=json.loads(line)
            if 'gradient' in row:memo[tuple(row['x'])]=(row['nll'],np.array(row['gradient']))
    with log.open('a',encoding='utf8',buffering=1) as stream:
      def objective(x):
        nonlocal calls
        calls+=1;key=tuple(x)
        if key in memo:
            cached_value,cached_gradient=memo[key]
            return cached_value,cached_gradient.copy()
        value,g=L.value_gradient(unpack(x,m0=2.5))
        if not math.isfinite(value) or not np.all(np.isfinite(g)):return value,g
        row={'call':calls,'x':x.tolist(),'nll':value,'gradient':g.tolist(),'elapsed_seconds':time.monotonic()-started,'utc':dt.datetime.now(dt.timezone.utc).isoformat()}
        stream.write(json.dumps(row)+'\n');stream.flush();os.fsync(stream.fileno());memo[key]=(value,g.copy())
        return value,g
      if checkpoint.exists():row=json.loads(checkpoint.read_text())
      else:
        current=resources()
        if current['free_RAM_MiB']<512 or current['free_disk_GiB']<4:raise RuntimeError('RESOURCE_HOLD_BEFORE_SINGLE_REFERENCE_START')
        try:
            opt=minimize(objective,x0,jac=True,method='L-BFGS-B',bounds=FIT_BOUNDS,
                options={'maxiter':1000,'maxfun':20000,'ftol':1e-10,'gtol':1e-5})
            if not math.isfinite(float(opt.fun)) or not np.all(np.isfinite(opt.x)) or not np.all(np.isfinite(opt.jac)):
                raise ArithmeticError('Nonfinite optimizer result retained as failed replicate')
            row={'start':0,'initialization':'frozen_reference_vector','x_initial':x0.tolist(),
                'success':bool(opt.success),'message':str(opt.message),'nll':float(opt.fun),'x':opt.x.tolist(),
                'iterations':int(opt.nit),'calls':calls,'elapsed_seconds':time.monotonic()-started,
                'active_bounds':[k for k,(v,(a,b)) in enumerate(zip(opt.x,FIT_BOUNDS)) if min(v-a,b-v)<1e-5],
                'raw_gradient_max':float(np.max(np.abs(opt.jac)))}
        except Exception as error:
            if isinstance(error,MemoryError) or 'RESOURCE_HOLD' in str(error):raise
            row={'start':0,'initialization':'frozen_reference_vector','x_initial':x0.tolist(),'success':False,'error':repr(error),'calls':calls}
        write(checkpoint,row)
    if not row.get('success') or not math.isfinite(row.get('nll',math.inf)):
        result={'status':'SINGLE_REFERENCE_START_FAILED','starts':[row],'bootstrap_initializations':1,
                'full_uncertainty_closed':False,'forecasts_issued':0}
        write(destination,result);return result
    p=unpack(row['x'],m0=2.5);value=L.value_gradient(p)[0];refinements=[]
    for order in (32,64):
        L.order=order;v=L.value_gradient(p)[0]
        refinements.append({'order':order,'nll':v,'absolute_delta_per_target':abs(v-value)/len(L.ev)})
    refined=domain.from_geographic_cells([[ix/10-180,iy/10-90] for ix,iy in sorted(domain.cells)],subdivide=2)
    other=MaskedLikelihood(h,selected,refined,radius,t0,t1,order=64);v=other.value_gradient(p)[0]
    refinements.append({'order':64,'geographic_subdivision':2,'nll':v,'absolute_delta_per_target':abs(v-value)/len(L.ev)})
    passed=all(r['absolute_delta_per_target']<=1e-3 for r in refinements)
    result={'status':'CONDITIONAL_POINT_FIT_NUMERICAL_QA_PASS' if passed else 'MINIMUM_FAILED_REFINED_NUMERICAL_REPRODUCTION',
        'parameters':asdict(p),'starts':[row],'selected_start':0,'selected_nll':row['nll'],'active_bounds':row['active_bounds'],
        'target_events':len(L.ev),'parents_kept':len(L.h),'refinements':refinements,'bootstrap_initializations':1,
        'initialization':'frozen_reference_vector','full_uncertainty_closed':False,'candidate_gamma_uncertainty_established':False,
        'numerical_backend':getattr(MaskedLikelihood.value_gradient,'_r4_backend_manifest',{}),
        'forecasts_issued':0,'utc':dt.datetime.now(dt.timezone.utc).isoformat()}
    write(destination,result);return result

def patch_package_bootstrap(base,profile_path):
    def bootstrap_one(epoch,index,shared):
        import numpy as np
        p,ref_path=base.reference_capsule(epoch);reference=json.loads(ref_path.read_text())
        if shared:
            if index!=1:raise RuntimeError('Only the two prescribed shared replicates')
            path=base.WORK/'simulations'/epoch/f'replicate_{index:03d}.npz';record=json.loads(path.with_suffix('.json').read_text())
            assert record['reference_sha256']==base.sha(ref_path) and record['sha256']==base.sha(path)
        else:path,record=base.simulate_input(epoch,index)
        z=np.load(path,allow_pickle=False);_,_,domain,radius,bounds=base.inputs();t0,t1=bounds[epoch]
        folder=base.WORK/('shared_checks' if shared else 'bootstrap')/epoch/f'replicate_{index:03d}'
        result=fit_single_reference_start(folder,z['history'],z['target_flags'],domain,radius,t0,t1,reference,
            base.resources,base.sha(path),sha(profile_path))
        receipt=folder/'BOOTSTRAP_RECEIPT.json'
        if not receipt.exists():write(receipt,{'epoch':epoch,'replicate':index,'simulation_sha256':base.sha(path),
            'reference_sha256':base.sha(ref_path),'result_sha256':base.sha(folder/'ETAS_FIT_RESULT.json'),
            'bootstrap_initializations':1,'profile_sha256':sha(profile_path),'status':result['status'],
            'numerical_backend':result.get('numerical_backend',{}),
            'shared_equivalence_only':shared,'utc':dt.datetime.now(dt.timezone.utc).isoformat(),'forecasts_issued':0,'operational_HOLD':True})
    base.bootstrap_one=bootstrap_one
