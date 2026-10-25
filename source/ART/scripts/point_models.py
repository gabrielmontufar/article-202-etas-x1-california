"""RJ and regional marked ETAS/ETAS-X1 kernels, fits and causal simulation.

Days, km and preferred catalogue M. Synthetic validation is not real skill.
All numerical budgets fail closed; simulation caps never truncate a forecast.
"""
from dataclasses import dataclass,asdict
from functools import lru_cache
import heapq,math,json,pathlib
import numpy as np
from scipy.optimize import minimize
from scipy.spatial import cKDTree
from scipy.stats import ncx2,qmc
from numpy.polynomial.legendre import leggauss

M0=4.0
class ModelFailure(RuntimeError):pass

@lru_cache(maxsize=8)
def angular_rule(order):return leggauss(order)

def temporal_pdf(t,c,p):
    t=np.asarray(t,float)
    return np.where(t>0,(p-1)/c*np.power(1+np.maximum(t,0)/c,-p),0.)
def temporal_cdf(t,c,p):
    t=np.maximum(np.asarray(t,float),0)
    return -np.expm1((1-p)*np.log1p(t/c))
def inverse_temporal(u,c,p):return c*np.expm1(-np.log1p(-np.asarray(u))/(p-1))
def spatial_pdf(r2,d,q):return (q-1)/(math.pi*np.asarray(d)**2)*np.power(1+np.asarray(r2)/np.asarray(d)**2,-q)
def radial_cdf(r,d,q):return -np.expm1((1-q)*np.log1p((np.asarray(r)/np.asarray(d))**2))
def disk_mass(offset,d,q,R,order=64):
    """Angular integration of radial CDF to displaced circular boundary."""
    a=np.asarray(offset,float).reshape(-1,1);d=np.broadcast_to(d,(a.size,)).reshape(-1,1)
    if np.any(a>R+1e-7):raise ValueError('Parent outside absorbing domain')
    nodes,w=angular_rule(order);theta=(nodes+1)*math.pi
    rm=-a*np.cos(theta)+np.sqrt(np.maximum(0,R*R-a*a*np.sin(theta)**2))
    return radial_cdf(np.maximum(rm,0),d,q)@w/2

@dataclass(frozen=True)
class ETASParameters:
    mu:float=0.1
    n:float=0.3
    alpha_ratio:float=0.5
    b:float=1.0
    c:float=0.03
    p:float=1.3
    q:float=1.8
    d0:float=5.
    eta:float=0.2
    gamma:float=0.
    m0:float=4.
    @property
    def beta(self):return self.b*math.log(10)
    @property
    def alpha(self):return self.alpha_ratio*self.beta
    @property
    def kappa(self):return self.n*(1-self.alpha_ratio)
    def check(self):
        vals=asdict(self)
        if not all(math.isfinite(v) for v in vals.values()):raise ValueError('Nonfinite parameters')
        if not (0<=self.m0<8 and 1e-6<=self.mu<=1e4 and .01<=self.n<=.95 and 0<=self.alpha_ratio<=.95 and .5<=self.b<=2
            and .001<=self.c<=1 and 1.01<=self.p<=2.5 and 1.01<=self.q<=3 and .5<=self.d0<=50
            and 0<=self.eta<=math.log(10)/2 and -1<=self.gamma<=1):raise ValueError('Parameter outside approved bounds')
        return self

class Background:
    """25-km Gaussian KDE in disk, 5% uniform; exact disk normalizer.

    Training-event density may subtract its own kernel (leave-one-out). The
    issue-time spatial law uses all past training points, never future ones.
    """
    def __init__(self,xy,R,bandwidth=25.):
        self.xy=np.asarray(xy,float).reshape(-1,2);self.R=float(R);self.h=float(bandwidth)
        if len(self.xy)==0:raise ValueError('KDE requires training locations')
        if np.any(np.linalg.norm(self.xy,axis=1)>R+1e-7):raise ValueError('Training source outside parent support')
        self.mass=ncx2.cdf((R/self.h)**2,2,np.sum(self.xy**2,axis=1)/self.h**2)
        self.Z=float(self.mass.mean())
        if not self.Z>0:raise ValueError('Invalid KDE normalizer')
    def density(self,xy,leave_out=None):
        xy=np.asarray(xy,float).reshape(-1,2);out=np.empty(len(xy));n=len(self.xy)
        for start in range(0,len(xy),128):
            points=xy[start:start+128];r2=np.sum((points[:,None,:]-self.xy[None,:,:])**2,axis=2)
            kernels=np.exp(-r2/(2*self.h**2))/(2*math.pi*self.h**2)
            total=kernels.sum(axis=1);normalizer=np.full(len(points),n*self.Z)
            if leave_out is not None:
                ix=np.asarray(leave_out)[start:start+len(points)];valid=ix>=0
                total[valid]-=kernels[np.arange(len(points))[valid],ix[valid]]
                normalizer[valid]-=self.mass[ix[valid]]
            kde=np.divide(total,normalizer,out=np.zeros_like(total),where=normalizer>0)
            out[start:start+len(points)]=.95*kde+.05/(math.pi*self.R**2)
        out[np.linalg.norm(xy,axis=1)>self.R]=0
        return out
    def sample(self,rng):
        if rng.random()<.05:
            ang=rng.uniform(0,2*math.pi);rad=self.R*math.sqrt(rng.random())
            return np.array([rad*math.cos(ang),rad*math.sin(ang)])
        component=rng.choice(len(self.xy),p=self.mass/self.mass.sum())
        for _ in range(100000):
            v=self.xy[component]+rng.normal(size=2)*self.h
            if np.linalg.norm(v)<=self.R:return v
        raise ModelFailure('KDE rejection budget exceeded; no truncated law')

def covariate(t,xy,history):
    """Strictly causal: time-30 <= t_j < t, distance <= 50 km."""
    h=np.asarray(history,float).reshape(-1,4)
    valid=(h[:,0]<t)&(h[:,0]>=t-30)&(np.sum((h[:,1:3]-xy)**2,axis=1)<=50**2)
    n30=int(valid.sum());n7=int((valid&(h[:,0]>=t-7)).sum())
    return float(np.clip(math.log1p(n7)-math.log1p(7*n30/30),-2,2))

def covariate_measure(history,bg,t0,t1,order=4096):
    """Exact time intervals at a fixed deterministic spatial quadrature.

    Never called with target observations. Spatial quadrature must be checked
    at double resolution before real emission, independently of this utility.
    """
    h=np.asarray(history,float).reshape(-1,4);power=int(math.log2(order))
    if 2**power!=order:raise ValueError('Sobol order must be power of 2')
    u=qmc.Sobol(2,scramble=True,seed=20261020).random_base2(power)
    r=bg.R*np.sqrt(u[:,0]);ang=2*math.pi*u[:,1];xy=np.c_[r*np.cos(ang),r*np.sin(ang)]
    w=bg.density(xy)*math.pi*bg.R**2/order;mass=float(w.sum());w/=mass
    tree=cKDTree(h[:,1:3]);zs=[];ws=[]
    for point,weight in zip(xy,w):
        times=np.sort(h[tree.query_ball_point(point,50),0])
        cuts=np.unique(np.r_[t0,t1,times,times+7,times+30]);cuts=cuts[(cuts>=t0)&(cuts<=t1)]
        mid=(cuts[:-1]+cuts[1:])/2
        n30=np.searchsorted(times,mid,side='left')-np.searchsorted(times,mid-30,side='left')
        n7=np.searchsorted(times,mid,side='left')-np.searchsorted(times,mid-7,side='left')
        zs.extend(np.clip(np.log1p(n7)-np.log1p(7*n30/30),-2,2))
        ws.extend(weight*np.diff(cuts))
    return np.asarray(zs),np.asarray(ws),mass

def etas_nll(parameters,history,bg,t0,t1,measure=None,leave_out=None):
    p=parameters.check();h=np.asarray(history,float).reshape(-1,4)
    if np.any(h[:,0]>=t1):raise ValueError('Training contains origins at/after cutoff')
    if not np.all(np.isfinite(h)) or np.any(h[:,3]<p.m0):raise ValueError('Nonfinite history or magnitude below model support')
    ix=np.flatnonzero((h[:,0]>=t0)&(h[:,0]<t1));events=h[ix]
    if not len(events):raise ValueError('No training events')
    density=bg.density(events[:,1:3],leave_out)
    z=np.array([covariate(e[0],e[1:3],h) for e in events]) if p.gamma else np.zeros(len(events))
    intensity=p.mu*density*np.exp(p.gamma*z)
    prod=p.kappa*np.exp(p.alpha*(h[:,3]-p.m0));d=p.d0*np.exp(p.eta*(h[:,3]-p.m0))
    for first in range(0,len(events),64):
        ev=events[first:first+64];lag=ev[:,None,0]-h[None,:,0]
        r2=np.sum((ev[:,None,1:3]-h[None,:,1:3])**2,axis=2)
        intensity[first:first+len(ev)]+=(temporal_pdf(lag,p.c,p.p)*spatial_pdf(r2,d,p.q)*prod).sum(axis=1)
    if np.any(intensity<=0) or not np.all(np.isfinite(intensity)):return math.inf
    boundary=disk_mass(np.linalg.norm(h[:,1:3],axis=1),d,p.q,bg.R)
    trigger_integral=float(np.sum(prod*boundary*(temporal_cdf(t1-h[:,0],p.c,p.p)-temporal_cdf(t0-h[:,0],p.c,p.p))))
    if p.gamma:
        if measure is None:raise ValueError('X1 requires frozen spacetime integration measure')
        zs,ws,_=measure;background_integral=p.mu*float(ws@np.exp(p.gamma*zs))
    else:background_integral=p.mu*(t1-t0)
    logmarks=len(events)*math.log(p.beta)-p.beta*float((events[:,3]-p.m0).sum())
    return background_integral+trigger_integral-float(np.log(intensity).sum())-logmarks+p.gamma**2/2

FIT_BOUNDS=[(math.log(1e-6),math.log(1e4)),(.01,.95),(0,.95),(.5,2),(math.log(.001),0),
            (1.01,2.5),(1.01,3),(math.log(.5),math.log(50)),(0,math.log(10)/2)]
def unpack(x,gamma=0,m0=4.):
    # exp(log(bound)) may exceed its bound by one ulp. Canonicalize only these
    # three transformed coordinates; never widen a scientific parameter bound.
    mu=min(1e4,max(1e-6,math.exp(x[0])));c=min(1.,max(.001,math.exp(x[4])))
    d0=min(50.,max(.5,math.exp(x[7])))
    return ETASParameters(mu,x[1],x[2],x[3],c,x[5],x[6],d0,x[8],gamma,m0)
def save_fit_progress(path,model,runs):
    if path:
        p=pathlib.Path(path)
        # A checkpoint is replaceable progress; all starts accumulate in order.
        p.write_text(json.dumps({'model':model,'synthetic_or_training_only':True,'starts':runs},indent=2),encoding='utf-8')

def fit_etas(history,bg,t0,t1,leave_out=None,fitlog_path=None,m0=4.):
    """8 fixed deterministic starts, all retained; finite converged minimum only."""
    design=qmc.Sobol(9,scramble=True,seed=20261020).random_base2(3);results=[]
    for j,u in enumerate(design):
        x=np.array([a+(b-a)*z for (a,b),z in zip(FIT_BOUNDS,u)])
        # Same declared budget at every start; no outcome-driven retries.
        opt=minimize(lambda v:etas_nll(unpack(v,m0=m0),history,bg,t0,t1,leave_out=leave_out),x,
            method='L-BFGS-B',bounds=FIT_BOUNDS,options={'maxiter':1000,'maxfun':20000,'ftol':1e-10,'gtol':1e-5})
        results.append({'start':j,'success':bool(opt.success),'message':str(opt.message),
            'nll':float(opt.fun),'x':opt.x.tolist(),'iterations':int(opt.nit),
            'active_bounds':[i for i,(v,(a,b)) in enumerate(zip(opt.x,FIT_BOUNDS)) if min(v-a,b-v)<1e-5],
            'raw_gradient_max':float(np.max(np.abs(opt.jac))),
            'identifiability_established':False})
        save_fit_progress(fitlog_path,'ETAS',results)
    valid=[r for r in results if r['success'] and math.isfinite(r['nll'])]
    if not valid:raise ModelFailure('All 8 ETAS starts failed; retain run log')
    best=min(valid,key=lambda x:x['nll']);p=unpack(best['x'],m0=m0)
    return p,results

def fit_x1(base,history,bg,t0,t1,measure,leave_out=None,fitlog_path=None):
    from dataclasses import replace
    runs=[]
    for j,g in enumerate(np.linspace(-.875,.875,8)):
        opt=minimize(lambda v:etas_nll(replace(base,gamma=float(v[0])),history,bg,t0,t1,measure,leave_out),
            [g],method='L-BFGS-B',bounds=[(-1,1)],options={'maxiter':1000,'maxfun':20000,'ftol':1e-10,'gtol':1e-5})
        runs.append({'start':j,'gamma':float(opt.x[0]),'nll':float(opt.fun),'success':bool(opt.success),'message':str(opt.message)})
        save_fit_progress(fitlog_path,'ETAS-X1',runs)
    valid=[r for r in runs if r['success'] and math.isfinite(r['nll'])]
    if not valid:raise ModelFailure('All 8 X1 starts failed')
    return replace(base,gamma=min(valid,key=lambda x:x['nll'])['gamma']),runs

def omori_integral(a,b,c,p):
    if b<a or a<0:raise ValueError('Invalid RJ time interval')
    if abs(p-1)<1e-8:return math.log((b+c)/(a+c))
    return ((b+c)**(1-p)-(a+c)**(1-p))/(1-p)

@dataclass(frozen=True)
class RJParameters:
    a:float=-2.;b:float=1.;c:float=.03;p:float=1.1;main_magnitude:float=7.7;background_per_day:float=.1
    m0:float=4.
    def check(self):
        if not (-6<=self.a<=2 and .5<=self.b<=2 and .001<=self.c<=1 and .5<=self.p<=2.5
                and self.background_per_day>=0 and 0<=self.m0<8):raise ValueError('RJ bounds invalid')
        return self
    def rate(self,t):
        self.check();t=np.asarray(t,float)
        if np.any(t<0):raise ValueError('RJ before mainshock')
        return self.background_per_day+10**(self.a+self.b*(self.main_magnitude-self.m0))*np.power(t+self.c,-self.p)
    def expected(self,start,end,threshold=None):
        threshold=self.m0 if threshold is None else threshold
        if threshold<self.m0:raise ValueError('Threshold below RJ model support')
        self.check();integral=self.background_per_day*(end-start)+10**(self.a+self.b*(self.main_magnitude-self.m0))*omori_integral(start,end,self.c,self.p)
        return integral*10**(-self.b*(threshold-self.m0))

def fit_rj(times,magnitudes,end,background_per_day,main_magnitude=7.7,fitlog_path=None,m0=4.):
    t=np.asarray(times,float);m=np.asarray(magnitudes,float)
    if len(t)==0 or np.any(t<0) or np.any(t>=end) or np.any(m<m0):raise ValueError('Invalid RJ training')
    bounds=[(-6,2),(.5,2),(math.log(.001),0),(.5,2.5)]
    def to_p(v):return RJParameters(v[0],v[1],math.exp(v[2]),v[3],main_magnitude,background_per_day,m0)
    def obj(v):
        p=to_p(v);beta=p.b*math.log(10)
        return p.expected(0,end)-float(np.log(p.rate(t)).sum())-len(t)*math.log(beta)+beta*float((m-m0).sum())
    runs=[]
    for j,u in enumerate(qmc.Sobol(4,scramble=True,seed=20261020).random_base2(3)):
        x=np.array([a+(b-a)*v for (a,b),v in zip(bounds,u)])
        opt=minimize(obj,x,method='L-BFGS-B',bounds=bounds,options={'maxiter':1000,'maxfun':20000,'ftol':1e-10,'gtol':1e-5})
        runs.append({'start':j,'success':bool(opt.success),'nll':float(opt.fun),'x':opt.x.tolist(),'message':str(opt.message)})
        save_fit_progress(fitlog_path,'RJ',runs)
    valid=[r for r in runs if r['success'] and math.isfinite(r['nll'])]
    if not valid:raise ModelFailure('All 8 RJ starts failed')
    return to_p(min(valid,key=lambda r:r['nll'])['x']),runs

def simulate_etas(p,history,bg,cutoff,end,seed,max_events=200000):
    """Chronological superposition/thinning and branching with absorbing boundary.

    Returns [t,x,y,M,exact_floor_immigrant]. Full cascades in the lead gap are
    simulated. Accepted future events alone update X1; real future input fails.
    """
    p.check();h=np.asarray(history,float).reshape(-1,4)
    if np.any(h[:,0]>=cutoff) or end<=cutoff:raise ValueError('Noncausal history/interval')
    if not np.all(np.isfinite(h)) or np.any(h[:,3]<p.m0):raise ValueError('Invalid ETAS simulation history support')
    rng=np.random.default_rng(seed);heap=[];serial=0;processed=h.tolist();accepted=[];generated=0
    def push(t,xy,mag,kind):
        nonlocal serial,generated
        generated+=1
        if generated>max_events:raise ModelFailure('Trajectory budget exceeded; discard whole trajectory')
        heapq.heappush(heap,(float(t),serial,float(xy[0]),float(xy[1]),float(mag),kind));serial+=1
    def children(event):
        tj,xj,yj,mj=event[:4];lower=max(cutoff,tj)
        lo=float(temporal_cdf(lower-tj,p.c,p.p));hi=float(temporal_cdf(end-tj,p.c,p.p))
        mean=p.kappa*math.exp(p.alpha*(mj-p.m0))*(hi-lo)
        if not math.isfinite(mean):raise ModelFailure('Nonfinite offspring mean')
        count=int(rng.poisson(mean))
        if generated+count>max_events:raise ModelFailure('Offspring budget exceeded; no tail clipping')
        for _ in range(count):
            time=tj+float(inverse_temporal(lo+rng.random()*(hi-lo),p.c,p.p))
            r=p.d0*math.exp(p.eta*(mj-p.m0))*math.sqrt(math.expm1(-math.log1p(-rng.random())/(p.q-1)))
            ang=rng.uniform(0,2*math.pi);xy=np.array([xj+r*math.cos(ang),yj+r*math.sin(ang)])
            if np.linalg.norm(xy)<=bg.R:push(time,xy,p.m0+rng.exponential(1/p.beta),'child')
    for event in h:children(event)
    low=p.mu*math.exp(-2*abs(p.gamma));high=p.mu*math.exp(2*abs(p.gamma))
    for rate,kind in [(low,'floor'),(high-low,'residual')]:
        count=int(rng.poisson(rate*(end-cutoff)))
        if generated+count>max_events:raise ModelFailure('Immigrant proposal budget exceeded')
        for _ in range(count):push(rng.uniform(cutoff,end),bg.sample(rng),p.m0+rng.exponential(1/p.beta),kind)
    while heap:
        t,_,x,y,m,kind=heapq.heappop(heap)
        if kind=='residual':
            z=covariate(t,np.array([x,y]),processed)
            accept=(p.mu*math.exp(p.gamma*z)-low)/(high-low)
            if not -1e-12<=accept<=1+1e-12:raise ModelFailure('Invalid X1 thinning probability')
            if rng.random()>accept:continue
        event=[t,x,y,m];processed.append(event);accepted.append(event+[kind=='floor']);children(event)
    return np.asarray(accepted,float).reshape(-1,5)

def simulate_rj(p,bg,start,end,seed,max_events=200000):
    p.check();rng=np.random.default_rng(seed);n=int(rng.poisson(p.expected(start,end)))
    if n>max_events:raise ModelFailure('RJ event cap; discard, do not truncate')
    bgmean=p.background_per_day*(end-start);total=p.expected(start,end)
    rows=[]
    for _ in range(n):
        u=rng.random()
        if u<bgmean/total:t=rng.uniform(start,end)
        else:
            v=rng.random()
            if abs(p.p-1)<1e-8:t=(start+p.c)*math.exp(v*math.log((end+p.c)/(start+p.c)))-p.c
            else:t=((start+p.c)**(1-p.p)+v*((end+p.c)**(1-p.p)-(start+p.c)**(1-p.p)))**(1/(1-p.p))-p.c
        xy=bg.sample(rng);rows.append([t,*xy,p.m0+rng.exponential(1/(p.b*math.log(10)))])
    return np.array(sorted(rows,key=lambda r:r[0])).reshape(-1,4)
