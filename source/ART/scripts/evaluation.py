"""Registered mean-score and temporal block intervals; no real outcomes read.

The mean score remains proper for conditional means of dependent counts. It
is not the exact clustered-process log likelihood. Zero-event days contribute.
"""
import math
import numpy as np

def daily_gain(observed,etas_mean,x1_mean):
    n=np.asarray(observed,float);e=np.asarray(etas_mean,float);x=np.asarray(x1_mean,float)
    if n.shape!=e.shape or n.shape!=x.shape:raise ValueError('Different scoring support')
    if not all(np.all(np.isfinite(a)) for a in [n,e,x]):raise ValueError('Nonfinite score input')
    if np.any(n<0) or np.any(n!=np.floor(n)):raise ValueError('Observed counts invalid')
    if np.any(e<=0) or np.any(x<=0):raise ValueError('No post-outcome epsilon; positive immigrant means required')
    return float(np.sum(n*np.log(x/e)-(x-e))),int(n.sum())

def information_gain(deltas,counts):
    d=np.asarray(deltas,float);n=np.asarray(counts,float)
    if d.shape!=n.shape or not np.all(np.isfinite(d)) or np.any(n<0):raise ValueError('Invalid daily sequence')
    total=float(n.sum())
    return None if total==0 else float(d.sum()/total)

def block_interval(deltas,counts,length,replicates=9999,seed=20261020):
    """Non-circular overlapping moving blocks; last sampled block cropped.

    All days are retained, including zeros. A draw with no events is undefined;
    if it occupies a CI tail, the interval is not evaluable, never discarded.
    """
    d=np.asarray(deltas,float);n=np.asarray(counts,float);size=len(d)
    if d.shape!=n.shape or size<length or length not in (7,14):raise ValueError('Invalid registered block support')
    rng=np.random.default_rng(seed);values=[];undefined=0
    for _ in range(replicates):
        starts=rng.integers(0,size-length+1,size=math.ceil(size/length))
        indices=np.concatenate([np.arange(s,s+length) for s in starts])[:size]
        # Resample the calendar, retaining missing-day positions. Do not close
        # gaps and turn nonadjacent days into falsely adjacent observations.
        valid=np.isfinite(d[indices])&np.isfinite(n[indices])
        ig=information_gain(d[indices][valid],n[indices][valid])
        if ig is None:undefined+=1
        else:values.append(ig)
    # No reselection of all-positive draws to manufacture narrower intervals.
    if undefined>0:return {'status':'UNDEFINED_DRAWS_NO_CONFIRMATORY_CI','undefined':undefined,'replicates':replicates,'interval95':None}
    return {'status':'COMPUTED_APPROXIMATE_BLOCK_CI','undefined':0,'replicates':replicates,
        'block_length':length,'interval95':np.quantile(values,[.025,.975]).tolist()}

def final_decision(deltas,counts,expected_windows=90):
    d=np.asarray(deltas,float);n=np.asarray(counts,float)
    if len(d)!=len(n):raise ValueError('Daily lists differ')
    finite=np.isfinite(d)&np.isfinite(n);coverage=float(finite.sum()/expected_windows)
    ig=information_gain(d[finite],n[finite]);total=int(n[finite].sum())
    out={'common_coverage':coverage,'events':total,'IG':ig,'status':'NOT_EVALUABLE','intervals':{}}
    if len(d)>expected_windows:raise ValueError('More than registered final windows')
    if len(d)!=expected_windows or coverage<.9 or total<100 or ig is None:return out
    for length in [7,14]:out['intervals'][str(length)]=block_interval(d,n,length)
    if any(r['interval95'] is None for r in out['intervals'].values()):return out
    out['status']='SUCCESS_LOCAL_ONLY' if ig>.05 and all(r['interval95'][0]>.05 for r in out['intervals'].values()) else 'NO_DEMONSTRATED_IMPROVEMENT'
    return out
