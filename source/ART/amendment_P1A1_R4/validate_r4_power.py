"""Registered R4 score-design diagnostics; synthetic only, never forecasts."""
import datetime as dt, hashlib, json, math, pathlib, sys

ROOT=pathlib.Path(__file__).resolve().parents[1]
HERE=pathlib.Path(__file__).resolve().parent
OUT=pathlib.Path(r'C:\Users\gjm31\forge_cache\panama_probabilistic_20261020\amendment_20261021\R4')
sys.path.insert(0,str(ROOT/'amendment_P1A1_R3'))
from r3_design import guard,sha,write

def weights(length, draws=9999, seed=20261020):
    """Exactly the same index draws as evaluation.block_interval, vectorized."""
    import numpy as np
    rng=np.random.default_rng(seed);blocks=math.ceil(90/length)
    starts=rng.integers(0,90-length+1,size=(draws,blocks))
    w=np.zeros((draws,90),float)
    for b in range(blocks):
        for k in range(min(length,90-b*length)):
            w[np.arange(draws),starts[:,b]+k]+=1
    assert np.all(w.sum(axis=1)==90)
    return w

def wilson(k,n):
    from statistics import NormalDist
    z=NormalDist().inv_cdf(.975);p=k/n;den=1+z*z/n
    center=(p+z*z/(2*n))/den
    half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return [center-half,center+half]

def diagnostic(rate_only,clustered,ig,trials,seed):
    import numpy as np
    from scipy.optimize import brentq
    rng=np.random.default_rng(seed);mean=844*90/365
    exposure=np.ones((trials,90))
    if clustered:
        blocks=rng.lognormal(-.6**2/2,.6,size=(trials,math.ceil(90/7)))
        exposure=np.repeat(blocks,7,axis=1)[:,:90]
    lam=mean/90*exposure
    if rate_only:
        r=brentq(lambda v:math.log(v)-1+1/v-ig,1+1e-10,10)
        counts=rng.poisson(lam);d=counts*math.log(r)-lam*(1-1/r)
        truth={'rate_ratio':r,'candidate_mean_true':True}
        a=counts;b=np.zeros_like(counts)
    else:
        p=brentq(lambda v:v*math.log(2*v)+(1-v)*math.log(2*(1-v))-ig,.50000001,.999999)
        a=rng.poisson(lam*p);b=rng.poisson(lam*(1-p));counts=a+b
        d=a*math.log(2*p)+b*math.log(2*(1-p))
        truth={'candidate_spatial_probability':p,'base_spatial_probability':.5,'candidate_mean_true':True}
    return d,counts,lam,a,b,truth

def main():
    resources=guard()
    import numpy as np
    from scipy.stats import norm
    sys.path.insert(0,str(ROOT/'scripts'))
    from evaluation import block_interval
    target=OUT/'R4_POWER_DESIGN_DIAGNOSTIC.json'
    assert not target.exists(),'Immutable results already exist'
    W={k:weights(k) for k in (7,14)}
    # Verify actual native rule, not a different faster confidence interval.
    n=np.arange(90)%4;d=.13*n+np.sin(np.arange(90))*.2
    parity={}
    for k,w in W.items():
        fast=np.quantile((w@d)/(w@n),[.025,.975])
        slow=block_interval(d,n,k)['interval95']
        assert np.max(np.abs(fast-slow))<1e-12
        parity[str(k)]={'maximum_absolute_CI_difference':float(np.max(np.abs(fast-slow)))}
    scenarios=[]
    for mech in ('rate_only','two_cell_space'):
      for dep in ('independent','seven_day_cox'):
        for ig in (.05,.10):
            label=f'{mech}|{dep}|{ig:.2f}'
            seed=int.from_bytes(hashlib.sha256(('R4_POWER_20261021|'+label).encode()).digest()[:8],'big')
            d,n,lam,a,b,truth=diagnostic(mech=='rate_only',dep=='seven_day_cox',ig,1000,seed)
            total=n.sum(axis=1);point=np.divide(d.sum(axis=1),total,out=np.full(1000,np.nan),where=total>0)
            success=(total>=100)&(point>.05);coverage={};ci_all={}
            for k,w in W.items():
                ci=np.empty((1000,2));undefined=np.zeros(1000,bool)
                for start in range(0,1000,25):
                    den=n[start:start+25]@w.T
                    vals=np.divide(d[start:start+25]@w.T,den,out=np.full(den.shape,np.nan),where=den>0)
                    undefined[start:start+25]=np.any(~np.isfinite(vals),axis=1)
                    ci[start:start+25]=np.quantile(vals,[.025,.975],axis=1).T
                valid=~undefined;covers=valid&(ci[:,0]<=ig)&(ci[:,1]>=ig)
                coverage[str(k)]={'coverage':float(covers.mean()),'wilson95':wilson(int(covers.sum()),1000),'undefined_trials':int(undefined.sum())}
                success&=valid&(ci[:,0]>.05);ci_all['ci'+str(k)]=ci
            k=int(success.sum());interval=wilson(k,1000)
            result={'label':label,'seed':seed,'trials':1000,'true_expected_IG':ig,'truth':truth,
                'expected_events':844*90/365,'events_mean':float(total.mean()),
                'events_quantiles':np.quantile(total,[.025,.5,.975]).tolist(),
                'below_100':int((total<100).sum()),'joint_successes':k,
                'joint_success_fraction':k/1000,'wilson95':interval,'coverage':coverage,
                'power_at_least80':bool(k/1000>=.8) if ig==.1 else None,
                'boundary_upper_false_success_at_most07':bool(interval[1]<=.07) if ig==.05 else None}
            raw=OUT/('R4_POWER_'+label.replace('|','_')+'.npz')
            with raw.open('xb') as f:np.savez_compressed(f,score_delta=d,daily_count=n,true_daily_mean=lam,cell_A=a,cell_B=b,success=success,**ci_all)
            result['raw']={'path':str(raw),'sha256':sha(raw)};scenarios.append(result)
            print('SCENARIO',label,'joint=',k/1000,'CI=',interval,flush=True)
            write(OUT/('R4_POWER_'+label.replace('|','_')+'.json'),result)
    precision=[];mean=844*90/365
    for sigma in (.1,.2,.3,.5,1.):
        power=float(norm.cdf((.10-.05)*math.sqrt(mean)/sigma-norm.ppf(.975)))
        precision.append({'assumed_iid_per_event_SD_nats':sigma,'approximate_one_CI_power':power,
            'N_required80_approx':math.ceil(((norm.ppf(.975)+norm.ppf(.8))*sigma/.05)**2)})
    out={'status':'SYNTHETIC_SCORE_DESIGN_DIAGNOSTIC_NOT_ETAS_PREFLIGHT',
        'utc':dt.datetime.now(dt.timezone.utc).isoformat(),'rules_sha256':sha(HERE/'R4_VALIDATION_RULES_BEFORE_COMPUTATION_ES.md'),
        'script_sha256':sha(__file__),'native_bootstrap_parity':parity,'scenarios':scenarios,
        'normal_precision_sensitivity_only':precision,
        'actual_ETAS_X1_power_established':False,'historical_forecast_skill_calculated':False,
        'outcomes_opened':False,'forecasts_issued':0,'external_seals':0,
        'scope':'Oracle score fixtures; not new challenger models, not a universal upper power bound',
        'resources_after':resources()}
    write(target,out)
    print('COMPLETE',str(target),flush=True)

if __name__=='__main__':main()
