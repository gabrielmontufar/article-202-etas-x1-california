"""P1-A1 design-stage epoch MAXC/MBS; no emission or scoring functions."""
import datetime as dt,hashlib,json,math,pathlib,sys
import numpy as np

ROOT=pathlib.Path(__file__).resolve().parents[1]
CACHE=pathlib.Path(r'C:\Users\gjm31\forge_cache\panama_probabilistic_20261020\amendment_20261021')
PLAN=pathlib.Path(__file__).with_name('PREPARATION_SCOPE_AND_ANALYSIS_RULES_ES.md')
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def write_new(p,obj):
    with pathlib.Path(p).open('x',encoding='utf-8') as f:json.dump(obj,f,indent=2,ensure_ascii=False,allow_nan=False)
def finite(x):return float(x) if x is not None and math.isfinite(x) else None

def b_value(centres,counts,cutoff,min_events=30):
    use=centres>=cutoff-1e-8;counts=counts[use];m=centres[use];n=int(counts.sum())
    if n<min_events:return None
    mean=float(counts@m/n);den=mean-(cutoff-.05)
    if den<=0:return None
    b=math.log10(math.e)/den
    sigma=math.log(10)*b*b*math.sqrt(float(counts@((m-mean)**2))/(n*(n-1)))
    return {'b':b,'sigma_Shi_Bolt':sigma,'tail_n':n}

def estimate_hist(centres,counts,acquisition_floor):
    counts=np.asarray(counts,int);n=int(counts.sum())
    if n==0:return {'n':0,'MAXC':None,'MAXC_plus_02':None,'MBS':None,'combined':None,'candidate_trace':[]}
    peak=int(np.flatnonzero(counts==counts.max())[-1]);mode=float(centres[peak]);maxc=round(mode+.2,8)
    trace=[];mbs=None
    nonzero=centres[counts>0];lo=max(acquisition_floor,float(nonzero.min()));hi=float(nonzero.max())-.4
    for j in range(round(lo*10),math.floor(hi*10+1e-7)+1):
        mc=j/10
        values=[b_value(centres,counts,mc+k/10) for k in range(5)]
        if any(v is None for v in values):continue
        base=values[0];avg=float(np.mean([v['b'] for v in values]));sigma=base['sigma_Shi_Bolt']
        ratio=abs(avg-base['b'])/sigma if sigma>0 else math.inf
        trace.append({'Mc':mc,**base,'mean_b_half_unit':avg,'normalized_difference':finite(ratio)})
        if ratio<=1:
            mbs=mc;break
    return {'n':n,'MAXC':mode,'MAXC_plus_02':maxc,'MBS':mbs,
        'combined':max(maxc,mbs) if mbs is not None else None,
        'MAXC_at_download_floor':abs(mode-acquisition_floor)<.051,'candidate_trace':trace}

def bootstrap_epochs(month_hist,epoch_specs,centres,acquisition_floor,label,B=500):
    rows=[];global_samples={'iid':[],'monthly':[]}
    per_epoch={}
    for e in epoch_specs:
        first,last=e['first_month'],e['last_month'];hist=month_hist[first:last].sum(axis=0)
        point=estimate_hist(centres,hist,acquisition_floor);draws={};n=int(hist.sum());month=month_hist[first:last]
        for kind in ['iid','monthly']:
            seed=int.from_bytes(hashlib.sha256(f'20261021|{label}|{e["label"]}|{kind}'.encode()).digest()[:8],'big')
            rng=np.random.default_rng(seed);values=[]
            for _ in range(B):
                if kind=='iid':sample=rng.multinomial(n,hist/n) if n else hist
                else:sample=month[rng.integers(0,len(month),len(month))].sum(axis=0) if len(month) else hist
                fit=estimate_hist(centres,sample,acquisition_floor)
                values.append(fit['combined'] if fit['combined'] is not None else math.inf)
            per_epoch[e['label']+'|'+kind]=np.array(values)
            draws[kind]={'replicates':B,'unresolved':sum(not math.isfinite(v) for v in values),
                'lower025':finite(sorted(values)[math.floor(.025*(B-1))]),
                'upper95':finite(sorted(values)[math.ceil(.95*B)-1]),
                'upper975':finite(sorted(values)[math.ceil(.975*B)-1])}
        rows.append({'epoch':e['label'],'point':point,'bootstrap':draws})
    result={}
    for kind in ['iid','monthly']:
        a=np.vstack([per_epoch[e['label']+'|'+kind] for e in epoch_specs]);values=a.max(axis=0)
        result[kind]={'replicates':B,'unresolved':int((~np.isfinite(values)).sum()),
            'upper95':finite(np.sort(values)[math.ceil(.95*B)-1]),
            'lower025':finite(np.sort(values)[math.floor(.025*(B-1))]),
            'upper975':finite(np.sort(values)[math.ceil(.975*B)-1])}
    points=[r['point']['combined'] for r in rows]
    point_global=max(points) if all(v is not None for v in points) else None
    bounds=[result[k]['upper95'] for k in ['iid','monthly']]
    upper=max(bounds) if all(v is not None for v in bounds) else None
    proposed=math.ceil(10*upper-1e-7)/10 if upper is not None else None
    floor_problem=any(r['point'].get('MAXC_at_download_floor',False) for r in rows)
    return {'epoch_results':rows,'global_point':point_global,'global_bootstrap':result,
        'proposed_Mstar_from_global_upper95':proposed,'floor_censoring_flag':floor_problem,
        'threshold_design_qualified':proposed is not None and not floor_problem,
        'note':'Empirical catalogue diagnostics, not proof of universal detection or forecasting skill'}

def magnitude_completeness(t,main_magnitude,mc_base,form='Page2016'):
    """Days since mainshock; two distinct literature forms, not locally fitted."""
    if np.any(np.asarray(t)<=0):raise ValueError('Mc(t) requires positive elapsed days')
    F,G,H=(.5,.25,1.) if form=='Page2016' else (1.,4.5,.75) if form=='HKJ2006' else (None,None,None)
    if F is None:raise ValueError('Unregistered completeness form')
    return np.maximum(mc_base,F*main_magnitude-G-H*np.log10(t))

def recovery_time(main_magnitude,mc_base,form='Page2016'):
    F,G,H=(.5,.25,1.) if form=='Page2016' else (1.,4.5,.75) if form=='HKJ2006' else (None,None,None)
    if F is None:raise ValueError('Unregistered completeness form')
    return 10**((F*main_magnitude-G-mc_base)/H)

def analyze_panama():
    sys.path.insert(0,str(ROOT/'scripts'));from public_catalogue import verify_access,target_indices
    verify_access()
    p=CACHE.parent/'training_capture_20261021_r1'
    cap=json.loads((p/'capture_manifest.json').read_text());grid=json.loads((p/'grid.json').read_text())
    if sha(p/'events.json')!=cap['events_sha256']:raise ValueError('Training bytes changed')
    records=json.loads((p/'events.json').read_text(encoding='utf-8'))
    records=[records[i] for i in target_indices(records,grid) if records[i]['origin_utc']>='1995-01-01']
    cutoff=dt.datetime.fromisoformat(cap['origin_end_exclusive']);last_month=(cutoff.year-1995)*12+cutoff.month
    centres=np.arange(30,math.ceil(max(r['mag'] for r in records)*10)+2)/10
    monthly=np.zeros((last_month,len(centres)),int)
    for row in records:
        t=dt.datetime.fromisoformat(row['origin_utc']);month=(t.year-1995)*12+t.month-1
        j=int(math.floor(row['mag']*10+.5))-30
        if 0<=month<len(monthly) and 0<=j<len(centres):monthly[month,j]+=1
    epochs=[]
    for year in range(1995,cutoff.year+1,5):
        epochs.append({'label':f'{year}-{min(year+5,cutoff.year)}','first_month':(year-1995)*12,
            'last_month':min(last_month,(year+5-1995)*12)})
    result=bootstrap_epochs(monthly,epochs,centres,3.,'Panama',500)
    result.update(status='DESIGN_ONLY_NOT_APPROVED_NOT_SEALED',region='Panama_P1',
        training_cutoff_utc=cap['origin_end_exclusive'],training_records=len(records),source_sha256=sha(p/'capture_manifest.json'),
        analysis_rules_sha256=sha(PLAN),analysis_code_sha256=sha(__file__),forecasts_issued=0,outcomes_scored=False)
    write_new(CACHE/'PANAMA_EPOCH_MC_DESIGN.json',result)
    print(json.dumps(result,indent=2));return result

if __name__=='__main__':analyze_panama()
