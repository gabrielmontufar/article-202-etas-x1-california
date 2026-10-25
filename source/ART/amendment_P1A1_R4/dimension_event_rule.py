"""R4 event-driven design, immutable simulation fixtures; no real outcomes."""
import datetime as dt,hashlib,json,math,pathlib,sys
ROOT=pathlib.Path(__file__).resolve().parents[1];HERE=pathlib.Path(__file__).resolve().parent
OUT=pathlib.Path(r'C:\Users\gjm31\forge_cache\panama_probabilistic_20261020\amendment_20261021\R4\event_rule_20261021')
sys.path.insert(0,str(ROOT/'amendment_P1A1_R3'));from r3_design import guard,sha,write
sys.path.insert(0,str(HERE));from validate_r4_power import wilson
GRID=(400,450,500,550,600,650,700,750,800)

def worlds(mechanism,dependency,ig,phase):
    import numpy as np
    from scipy.optimize import brentq
    label=f'{mechanism}|{dependency}|{ig:.2f}|{phase}'
    seed=int.from_bytes(hashlib.sha256(('R4_EVENT_RULE_20261021|'+label).encode()).digest()[:8],'big')
    rng=np.random.default_rng(seed);lam=np.full((1000,365),844/365)
    if dependency=='seven_day_cox':lam*=np.repeat(rng.lognormal(-.6**2/2,.6,size=(1000,53)),7,axis=1)[:,:365]
    if mechanism=='rate_only':
        r=brentq(lambda r:math.log(r)-1+1/r-ig,1+1e-10,10)
        n=rng.poisson(lam);d=n*math.log(r)-lam*(1-1/r);truth={'r':r}
    else:
        p=brentq(lambda p:p*math.log(2*p)+(1-p)*math.log(2*(1-p))-ig,.50000001,.999999)
        a=rng.poisson(lam*p);b=rng.poisson(lam*(1-p));n=a+b
        d=a*math.log(2*p)+b*math.log(2*(1-p));truth={'p':p}
    return label,seed,d,n,lam,truth

def intervals(d,n,length,draws):
    """Same resampling indices for percentile and the single proposed repair."""
    import numpy as np
    size=d.shape[1];groups=d.shape[0];k=math.ceil(size/length)
    if k<2:raise ValueError('Too few calendar blocks')
    starts=np.random.default_rng(20261020).integers(0,size-length+1,size=(draws,k))
    lengths=np.full(k,length);lengths[-1]=size-(k-1)*length
    D=np.c_[np.zeros(groups),np.cumsum(d,axis=1)];N=np.c_[np.zeros(groups),np.cumsum(n,axis=1)]
    point=d.sum(axis=1)/n.sum(axis=1)
    # Overlapping residual block sums define the registered original SE.
    od=D[:,length:]-D[:,:-length];on=N[:,length:]-N[:,:-length]
    original_se=np.sqrt((size/length)*np.var(od-point[:,None]*on,axis=1,ddof=1)*size/(size-length+1))/n.sum(axis=1)
    per=[];stud=[];undefined_p=[];undefined_t=[]
    # Keep the temporary cube below ~10 MiB even for short 7-day blocks.
    for first in range(groups):
        bd=D[first,starts+lengths]-D[first,starts]
        bn=N[first,starts+lengths]-N[first,starts]
        totaln=bn.sum(axis=1);g=np.divide(bd.sum(axis=1),totaln,out=np.full(draws,np.nan),where=totaln>0)
        star_se=np.sqrt(size*np.sum((bd-g[:,None]*bn)**2/lengths,axis=1)/(k-1))/totaln
        statistic=np.divide(g-point[first],star_se,out=np.full(draws,np.nan),where=star_se>0)
        badp=not np.all(np.isfinite(g));badt=not np.all(np.isfinite(statistic)) or not original_se[first]>0
        per.append(np.quantile(g,[.025,.975]) if not badp else [np.nan,np.nan])
        if badt:stud.append([np.nan,np.nan])
        else:
            qt=np.quantile(statistic,[.025,.975]);stud.append([point[first]-qt[1]*original_se[first],point[first]-qt[0]*original_se[first]])
        undefined_p.append(badp);undefined_t.append(badt)
    return np.asarray(per),np.asarray(stud)

def evaluate(d,n,target,ig,draws):
    import numpy as np
    cumulative=n.cumsum(axis=1);reached=cumulative[:,-1]>=target
    stop=np.where(reached,(cumulative>=target).argmax(axis=1)+1,365)
    point=np.full(1000,np.nan);success={a:reached.copy() for a in ('percentile','bootstrap_t_proposed')}
    cis={a:{str(k):np.full((1000,2),np.nan) for k in (7,14)} for a in success}
    for T in np.unique(stop[reached]):
        ix=np.flatnonzero(reached&(stop==T));data=d[ix,:T];counts=n[ix,:T]
        point[ix]=data.sum(axis=1)/counts.sum(axis=1)
        for L in (7,14):
            per,stud=intervals(data,counts,L,draws)
            cis['percentile'][str(L)][ix]=per;cis['bootstrap_t_proposed'][str(L)][ix]=stud
    methods={}
    for method in success:
        coverage={}
        success[method]&=point>.05
        for k,ci in cis[method].items():
            valid=np.all(np.isfinite(ci),axis=1);covers=valid&(ci[:,0]<=ig)&(ci[:,1]>=ig)
            success[method]&=valid&(ci[:,0]>.05)
            coverage[k]={'fraction_all_1000':float(covers.mean()),'wilson95':wilson(int(covers.sum()),1000),
                         'undefined_or_censored':int((~valid).sum()),'coverage_given_reached':float(covers.sum()/reached.sum()) if reached.any() else None}
        s=int(success[method].sum())
        methods[method]={'joint_successes':s,'joint_success_fraction':s/1000,'wilson95':wilson(s,1000),'coverage':coverage}
    return {'N':target,'trials':1000,'true_IG':ig,'bootstrap_replicates':draws,
            'reached_by_365':int(reached.sum()),'censored':int((~reached).sum()),
            'stop_day_quantiles_reached':np.quantile(stop[reached],[.025,.5,.975]).tolist() if reached.any() else None,
            'expected_days_from_recent_rate':target*365/844,'methods':methods},stop,point,cis,success

def phase_run(phase,grid,draws):
    import numpy as np
    records=[]
    for mechanism in ('rate_only','two_cell_space'):
      for dependency in ('independent','seven_day_cox'):
       for ig in (.05,.1):
        label,seed,d,n,lam,truth=worlds(mechanism,dependency,ig,phase)
        tag=label.replace('|','_');raw=OUT/(tag+'.npz')
        if raw.exists():
            with np.load(raw) as existing:
                assert np.array_equal(existing['d'],d) and np.array_equal(existing['n'],n)
        else:
            with raw.open('xb') as f:np.savez_compressed(f,d=d,n=n,true_daily_mean=lam)
        for N in grid:
            result_path=OUT/(tag+f'_N{N}.json')
            if result_path.exists():
                r=json.loads(result_path.read_text());assert r['script_sha256']==sha(__file__);records.append(r);continue
            r,stop,point,cis,success=evaluate(d,n,N,ig,draws)
            r.update(label=label,seed=seed,phase=phase,truth=truth,script_sha256=sha(__file__),source_sha256=sha(raw))
            detail=OUT/(tag+f'_N{N}_decisions.npz')
            with detail.open('xb') as f:np.savez_compressed(f,stop_day=stop,IG=point,
                percentile7=cis['percentile']['7'],percentile14=cis['percentile']['14'],
                proposed7=cis['bootstrap_t_proposed']['7'],proposed14=cis['bootstrap_t_proposed']['14'],
                success_percentile=success['percentile'],success_proposed=success['bootstrap_t_proposed'])
            r['decisions_sha256']=sha(detail);write(result_path,r);records.append(r)
            a=r['methods']['bootstrap_t_proposed']
            print('EVENT_RULE',phase,label,'N',N,'success',a['joint_success_fraction'],'coverage',a['coverage']['7']['fraction_all_1000'],a['coverage']['14']['fraction_all_1000'],'censored',r['censored'],flush=True)
    return records

def qualifies(records,N,method='bootstrap_t_proposed'):
    rows=[r for r in records if r['N']==N]
    if len(rows)!=8:return False
    for r in rows:
        a=r['methods'][method]
        if any(v['fraction_all_1000']<.93 for v in a['coverage'].values()):return False
        if r['true_IG']==.1 and a['wilson95'][0]<.8:return False
        if r['true_IG']==.05 and a['wilson95'][1]>.07:return False
    return True

def main():
    resources=guard();OUT.mkdir(exist_ok=True)
    final=OUT/'R4_EVENT_COUNT_DESIGN_RESULT.json';assert not final.exists(),'Already complete; do not duplicate'
    screen=phase_run('screening',GRID,1999)
    candidates=[N for N in GRID if qualifies(screen,N)]
    chosen=min(candidates) if candidates else None;validation=[]
    if chosen is not None:validation=phase_run('independent_validation',(chosen,),9999)
    passed=chosen is not None and qualifies(validation,chosen)
    write(final,{'status':'PROPOSED_N_AND_CI_PASSED_SYNTHETIC_SCENARIOS' if passed else 'HOLD_EVENT_RULE_POWER_OR_COVERAGE',
        'utc':dt.datetime.now(dt.timezone.utc).isoformat(),'rule_sha256':sha(HERE/'R4_EVENT_RULE_AND_COMPLETION_BEFORE_ANALYSIS_ES.md'),
        'CI_proposal_sha256':sha(HERE/'R4_CI_REPAIR_PROPOSAL_BEFORE_SCREEN_ES.md'),'script_sha256':sha(__file__),
        'screening_N_candidates':candidates,'selected_for_independent_validation':chosen,
        'proposed_N_star':chosen if passed else None,'independent_validation_passed':passed,
        'actual_fitted_ETAS_X1_power_established':False,'screening':screen,'validation':validation,
        'operational_CI_activated':False,'forecasts_issued':0,'external_seals':0,'resources_after':resources()})
    print('COMPLETE_EVENT_RULE',chosen,'VALIDATED',passed,flush=True)

if __name__=='__main__':main()
