"""Conditional ETAS likelihood in the approved R4 mask, external parents kept.

Analytic derivatives preserve the registered kernel and bounds. This module
does not emit or authorize a forecast. Numerical integration must pass QA.
"""
import collections,math
import numpy as np
from point_models import Background,temporal_cdf,covariate,ETASParameters

class MaskedLikelihood:
    def __init__(self,history,target_flags,domain,parent_radius,t0,t1,order=16):
        self.h=np.asarray(history,float).reshape(-1,4)
        self.ix=np.flatnonzero((self.h[:,0]>=t0)&(self.h[:,0]<t1)&np.asarray(target_flags,bool))
        if not len(self.ix):raise ValueError('Empty target fitting period')
        if np.any(self.h[:,0]>=t1) or np.any(np.diff(self.h[:,0])<0):raise ValueError('Noncausal or unsorted conditioning')
        self.ev=self.h[self.ix];self.domain=domain;self.t0=t0;self.t1=t1;self.order=order
        self.bg=Background(self.ev[:,1:3],parent_radius)
        self.density=self.bg.density(self.ev[:,1:3],leave_out=np.arange(len(self.ev)))
        gaussian=domain.masses(self.bg.xy,self.bg.h,gaussian=True,order=order)
        if np.any(gaussian<0) or np.any(gaussian>1+1e-5):raise ArithmeticError('Gaussian polygon mass outside [0,1]')
        self.background_mass=.95*float(gaussian.sum()/(len(gaussian)*self.bg.Z))+.05*domain.area/(math.pi*parent_radius**2)
        self.cache=collections.OrderedDict();self.evaluations=0

    def kernel_mass(self,p,order=None):
        order=self.order if order is None else order
        key=(p.q,p.d0,p.eta,order)
        if key not in self.cache:
            d=p.d0*np.exp(p.eta*(self.h[:,3]-p.m0))
            a=self.domain.masses(self.h[:,1:3],d,p.q,order=order,gradient=True)
            if np.any(a[:,0]<-1e-5) or np.any(a[:,0]>1+1e-5):raise ArithmeticError('ETAS polygon mass outside tolerance; no clipping')
            self.cache[key]=a
            if len(self.cache)>4:self.cache.popitem(last=False)
        return self.cache[key]

    def value_gradient(self,p):
        p.check();h=self.h;ev=self.ev
        if p.gamma!=0:raise ValueError('Use explicit X1 objective for nonzero gamma')
        if np.any(h[:,3]<p.m0):raise ValueError('Magnitude below explicit model support')
        dm=h[:,3]-p.m0;prod=p.kappa*np.exp(p.alpha*dm);scale2=(p.d0*np.exp(p.eta*dm))**2
        A=-1/(1-p.alpha_ratio)+p.beta*dm
        B=p.alpha_ratio*math.log(10)*dm
        value=0.;gradient=np.zeros(9)
        for first in range(0,len(ev),8):
            e=ev[first:first+8];base=p.mu*self.density[first:first+len(e)]
            # Sorted parents: future rows have exactly zero temporal support.
            stop=np.searchsorted(h[:,0],e[-1,0],side='left');hh=h[:stop]
            lag=e[:,None,0]-hh[None,:,0];positive=lag>0;lag=np.maximum(lag,0)
            r2=np.sum((e[:,None,1:3]-hh[None,:,1:3])**2,axis=2)
            logt=np.log1p(lag/p.c);logs=np.log1p(r2/scale2[None,:stop])
            weight=(p.p-1)/p.c*np.exp(-p.p*logt)*(p.q-1)/(math.pi*scale2[None,:stop])*np.exp(-p.q*logs)*prod[None,:stop]
            weight*=positive
            trigger=weight.sum(axis=1);intensity=base+trigger
            if np.any(intensity<=0) or not np.all(np.isfinite(intensity)):return math.inf,np.full(9,np.nan)
            value-=float(np.log(intensity).sum());inverse=1/intensity
            gradient[0]-=float((base*inverse).sum())
            gradient[1]-=float((trigger*inverse).sum())/p.n
            gradient[2]-=float(((weight@A[:stop])*inverse).sum())
            gradient[3]-=float(((weight@B[:stop])*inverse).sum())
            gradient[4]-=float(((weight*(p.p*lag/(p.c+lag)-1)).sum(axis=1)*inverse).sum())
            gradient[5]-=float(((weight*(1/(p.p-1)-logt)).sum(axis=1)*inverse).sum())
            gradient[6]-=float(((weight*(1/(p.q-1)-logs)).sum(axis=1)*inverse).sum())
            sd=-2+2*p.q*r2/(r2+scale2[None,:stop])
            gradient[7]-=float(((weight*sd).sum(axis=1)*inverse).sum())
            gradient[8]-=float(((weight*sd*dm[None,:stop]).sum(axis=1)*inverse).sum())
        mass=self.kernel_mass(p);lo=np.maximum(self.t0-h[:,0],0);hi=self.t1-h[:,0]
        ulo=np.exp((1-p.p)*np.log1p(lo/p.c));uhi=np.exp((1-p.p)*np.log1p(hi/p.c))
        integral=ulo-uhi
        dc=-(p.p-1)*uhi*hi/(p.c+hi)+(p.p-1)*ulo*lo/(p.c+lo)
        dp=uhi*np.log1p(hi/p.c)-ulo*np.log1p(lo/p.c)
        contribution=prod*mass[:,0]*integral
        value+=float(contribution.sum())+p.mu*self.background_mass*(self.t1-self.t0)
        gradient[0]+=p.mu*self.background_mass*(self.t1-self.t0)
        gradient[1]+=float(contribution.sum())/p.n
        gradient[2]+=float(contribution@A)
        gradient[3]+=float(contribution@B)
        gradient[4]+=float((prod*mass[:,0])@dc)
        gradient[5]+=float((prod*mass[:,0])@dp)
        gradient[6]+=float((prod*integral)@mass[:,1])
        gradient[7]+=float((prod*integral)@mass[:,2])
        gradient[8]+=float((prod*integral*dm)@mass[:,2])
        value-=len(ev)*math.log(p.beta)-p.beta*float((ev[:,3]-p.m0).sum())
        gradient[3]+=-len(ev)/p.b+math.log(10)*float((ev[:,3]-p.m0).sum())
        self.evaluations+=1
        return value,gradient

    def x1_inputs(self,base):
        h=self.h;p=base;prod=p.kappa*np.exp(p.alpha*(h[:,3]-p.m0));d=p.d0*np.exp(p.eta*(h[:,3]-p.m0))
        from point_models import temporal_pdf,spatial_pdf
        trigger=[];z=[]
        for event in self.ev:
            stop=np.searchsorted(h[:,0],event[0],side='left');past=h[:stop]
            r2=np.sum((past[:,1:3]-event[1:3])**2,axis=1)
            trigger.append(float((prod[:stop]*temporal_pdf(event[0]-past[:,0],p.c,p.p)*spatial_pdf(r2,d[:stop],p.q)).sum()))
            z.append(covariate(event[0],event[1:3],past))
        return np.asarray(trigger),np.asarray(z)

    def covariate_measure(self,cell_order=2):
        """Area quadrature over cells, causal exact time cuts; no unit renorm."""
        from numpy.polynomial.legendre import leggauss
        from scipy.spatial import cKDTree
        from pyproj import Geod
        nodes,weights=leggauss(cell_order);geod=Geod(ellps='WGS84')
        points=[];areas=[]
        for ix,iy in sorted(self.domain.cells):
            lon,lat=ix/10-180,iy/10-90
            # AEQD cell area: the same oriented projected quadrilateral as
            # the compensator. Geographic refinement is checked separately.
            x,y=self.domain.transformer.transform([lon,lon+.1,lon+.1,lon],[lat,lat,lat+.1,lat+.1])
            area=abs(sum(x[k]*y[(k+1)%4]-x[(k+1)%4]*y[k] for k in range(4)))/2e6
            for a,wa in zip(nodes,weights):
                for b,wb in zip(nodes,weights):
                    px,py=self.domain.transformer.transform(lon+.05*(1+a),lat+.05*(1+b))
                    points.append([px/1000,py/1000]);areas.append(area*wa*wb/4)
        points=np.array(points);mass_weights=self.bg.density(points)*np.asarray(areas)
        relevant=self.h[(self.h[:,0]>=self.t0-30)&(self.h[:,0]<self.t1)]
        tree=cKDTree(relevant[:,1:3]);aggregate=collections.defaultdict(float)
        for point,weight in zip(points,mass_weights):
            times=np.sort(relevant[tree.query_ball_point(point,50),0])
            cuts=np.unique(np.r_[self.t0,self.t1,times,times+7,times+30])
            cuts=cuts[(cuts>=self.t0)&(cuts<=self.t1)];mid=(cuts[1:]+cuts[:-1])/2
            n30=np.searchsorted(times,mid,'left')-np.searchsorted(times,mid-30,'left')
            n7=np.searchsorted(times,mid,'left')-np.searchsorted(times,mid-7,'left')
            pairs=np.c_[n7,n30];unique,inverse=np.unique(pairs,axis=0,return_inverse=True)
            totals=np.bincount(inverse,weights=weight*np.diff(cuts))
            for pair,total in zip(unique,totals):aggregate[tuple(pair)]+=float(total)
        pairs=np.array(list(aggregate));w=np.array(list(aggregate.values()))
        z=np.clip(np.log1p(pairs[:,0])-np.log1p(7*pairs[:,1]/30),-2,2)
        return z,w,float(mass_weights.sum())

    def fit_gamma(self,base,measure):
        from scipy.optimize import minimize
        from dataclasses import replace
        trigger,z=self.x1_inputs(base);zs,ws,mass=measure;runs=[]
        if abs(mass-self.background_mass)>1e-5+.005*self.background_mass:raise ArithmeticError('X1 background quadrature mass failed')
        def objective(v):
            g=float(v[0]);bg=base.mu*self.density*np.exp(g*z);intensity=trigger+bg
            value=base.mu*float(ws@np.exp(g*zs))-float(np.log(intensity).sum())+g*g/2
            derivative=base.mu*float(ws@(zs*np.exp(g*zs)))-float((z*bg/intensity).sum())+g
            return value,np.array([derivative])
        for k,g in enumerate(np.linspace(-.875,.875,8)):
            opt=minimize(objective,[g],jac=True,method='L-BFGS-B',bounds=[(-1,1)],options={'maxiter':1000,'maxfun':20000,'ftol':1e-10,'gtol':1e-5})
            runs.append({'start':k,'gamma':float(opt.x[0]),'success':bool(opt.success),'message':str(opt.message),'objective_gamma_terms':float(opt.fun),'gradient':float(opt.jac[0])})
        valid=[r for r in runs if r['success'] and math.isfinite(r['objective_gamma_terms'])]
        if not valid:raise RuntimeError('All eight X1 gamma starts failed')
        return replace(base,gamma=min(valid,key=lambda x:x['objective_gamma_terms'])['gamma']),runs
