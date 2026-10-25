"""Oriented-boundary integration of normalized radial kernels, including holes.

The integrand is CDF(r)/(2*pi*r^2) times outward flux. Its divergence is
the spatial density. No convex hull, parent removal, or post-hoc mass clip.
"""
import math
from functools import lru_cache
import numpy as np
from numpy.polynomial.legendre import leggauss

@lru_cache(maxsize=8)
def rule(order):
    x,w=leggauss(order)
    return x/2,w/2

class PolygonIntegrator:
    def __init__(self,starts,ends):
        self.starts=np.asarray(starts,float).reshape(-1,2)
        self.ends=np.asarray(ends,float).reshape(-1,2)
        if self.starts.shape!=self.ends.shape or not len(self.starts):raise ValueError('Invalid polygon edges')
        self.v=self.ends-self.starts;self.mid=(self.starts+self.ends)/2
        self.length2=np.sum(self.v*self.v,axis=1)
        if np.any(self.length2<=0):raise ValueError('Degenerate edge')
        self.normals=np.c_[self.v[:,1],-self.v[:,0]]
        self.area=float(np.sum(self.starts[:,0]*self.ends[:,1]-self.starts[:,1]*self.ends[:,0])/2)
        if self.area<=0:raise ValueError('Edges must orient interior on left, holes on right')

    @classmethod
    def from_geographic_cells(cls,cells,subdivide=1):
        from pyproj import Transformer
        keys={(round((lo+180)*10),round((la+90)*10)) for lo,la in cells}
        edges=[]
        for ix,iy in sorted(keys):
            # All exterior edges are counterclockwise; holes acquire the
            # opposite orientation automatically. Interior edges disappear.
            if (ix,iy-1) not in keys:edges.append(((ix,iy),(ix+1,iy)))
            if (ix+1,iy) not in keys:edges.append(((ix+1,iy),(ix+1,iy+1)))
            if (ix,iy+1) not in keys:edges.append(((ix+1,iy+1),(ix,iy+1)))
            if (ix-1,iy) not in keys:edges.append(((ix,iy+1),(ix,iy)))
        transformer=Transformer.from_crs('EPSG:4326','+proj=aeqd +lat_0=37 +lon_0=-120 +datum=WGS84 +units=m',always_xy=True)
        begins=[];ends=[]
        for a,b in edges:
            for part in range(subdivide):
                u=part/subdivide;v=(part+1)/subdivide
                points=np.array([[(1-s)*a[0]+s*b[0],(1-s)*a[1]+s*b[1]] for s in (u,v)])/10- [180,90]
                x,y=transformer.transform(points[:,0],points[:,1])
                begins.append([x[0]/1000,y[0]/1000]);ends.append([x[1]/1000,y[1]/1000])
        obj=cls(begins,ends);obj.transformer=transformer;obj.cells=keys
        return obj

    def masses(self,parents,scales,q=None,order=16,gaussian=False,gradient=False):
        """Far edges use Gauss-2, near edges Gauss-order; no kernel truncation.

        Near means distance to midpoint <8 edge lengths. Near-edge order also
        resolves the actual kernel scale (at least 8*edge_length/scale), which
        avoids underresolving a 0.5-km kernel on a ~10-km cell edge. The far
        approximation is independently checked using full higher-order rules
        in validation, not presumed correct merely by doubling near order.
        """
        parents=np.asarray(parents,float).reshape(-1,2)
        scales=np.broadcast_to(np.asarray(scales,float),(len(parents),))
        if np.any(scales<=0) or (not gaussian and not q>1):raise ValueError('Invalid radial kernel')
        result=np.zeros((len(parents),3 if gradient else 1))
        far_x,far_w=rule(2)
        def radial(r2,d2):
            z=r2/d2
            if gaussian:
                u=np.exp(-z/2);cdf=-np.expm1(-z/2)
                f=np.divide(cdf,r2,out=np.full_like(r2,.5)/d2,where=r2>0)
                return f,None,None
            log=np.log1p(z);u=np.exp((1-q)*log);cdf=-np.expm1((1-q)*log)
            f=np.divide(cdf,r2,out=(q-1)/d2+np.zeros_like(r2),where=r2>0)
            fq=np.divide(u*log,r2,out=1/d2+np.zeros_like(r2),where=r2>0)
            fd=-2*(q-1)*u/(d2+r2)
            return f,fq,fd
        for begin in range(0,len(parents),64):
            p=parents[begin:begin+64];d2=scales[begin:begin+len(p),None]**2
            delta=self.mid[None,:,:]-p[:,None,:]
            midr2=np.sum(delta*delta,axis=2)
            flux=np.sum(delta*self.normals[None,:,:],axis=2)/(2*math.pi)
            near=midr2<64*self.length2[None,:]
            acc=[np.zeros_like(flux) for _ in range(3 if gradient else 1)]
            for s,w in zip(far_x,far_w):
                r2=np.sum((delta+s*self.v[None,:,:])**2,axis=2)
                fs=radial(r2,d2)
                for k in range(len(acc)):acc[k]+=w*fs[k]
            rows,cols=np.nonzero(near)
            if len(rows):
                for k in range(len(acc)):acc[k][rows,cols]=0
                required=2**np.ceil(np.log2(np.maximum(order,8*np.sqrt(self.length2[cols])/np.sqrt(d2[rows,0])))).astype(int)
                if np.any(required>4096):raise ArithmeticError('Edge integration resolution budget exceeded')
                for actual_order in np.unique(required):
                    select=required==actual_order;rr=rows[select];cc=cols[select]
                    de=delta[rr,cc];ve=self.v[cc];ds=d2[rr,0]
                    near_x,near_w=rule(int(actual_order))
                    for s,w in zip(near_x,near_w):
                        r2=np.sum((de+s*ve)**2,axis=1);fs=radial(r2,ds)
                        for k in range(len(acc)):acc[k][rr,cc]+=w*fs[k]
            for k,a in enumerate(acc):result[begin:begin+len(p),k]=(a*flux).sum(axis=1)
        if not np.all(np.isfinite(result)):raise ArithmeticError('Nonfinite boundary integral')
        # Tolerances are checked by the caller; do not turn negatives to zero.
        return result if gradient else result[:,0]

    def full_edge_mass(self,parent,scale,q,order=64):
        """Independent nonadaptive high-order integration, validation only."""
        delta=self.mid-np.asarray(parent);flux=np.sum(delta*self.normals,axis=1)/(2*math.pi)
        nodes,weights=rule(order);answer=0.
        for s,w in zip(nodes,weights):
            r2=np.sum((delta+s*self.v)**2,axis=1)
            value=np.divide(-np.expm1((1-q)*np.log1p(r2/scale**2)),r2,
                            out=np.full_like(r2,(q-1)/scale**2),where=r2>0)
            answer+=float(w*(value*flux).sum())
        return answer
