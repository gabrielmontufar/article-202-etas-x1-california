"""Numba version of PolygonIntegrator.masses for the ETAS (non-Gaussian) kernel.

Same adaptive rule as the original: Gauss-2 for far edges; for near edges
(midpoint distance^2 < 64 * edge length^2) Gauss order
2**ceil(log2(max(order, 8*edge_length/scale))), error if > 4096.
No truncation of parents or edges; only summation order differs.
"""
import math
import numpy as np
import numba as nb
from numpy.polynomial.legendre import leggauss

_ORDERS = [2] + [2 ** k for k in range(3, 13)]  # 2, 8..4096
_NODES = []
_WEIGHTS = []
_OFFSETS = [0]
for o in _ORDERS:
    x, w = leggauss(o)
    _NODES.append(x / 2); _WEIGHTS.append(w / 2); _OFFSETS.append(_OFFSETS[-1] + o)
NODES = np.concatenate(_NODES); WEIGHTS = np.concatenate(_WEIGHTS)
OFFSETS = np.array(_OFFSETS, np.int64); ORDERS = np.array(_ORDERS, np.int64)


@nb.njit(cache=True)
def _slot(order):
    for k in range(ORDERS.shape[0]):
        if ORDERS[k] == order:
            return k
    return -1


@nb.njit(parallel=True, fastmath=False, cache=True)
def masses_q_grad(parents, scales, q, order, mid, v, normals, length2, nodes, weights, offsets, orders):
    n = parents.shape[0]; m = mid.shape[0]
    out = np.zeros((n, 3))
    bad = np.zeros(n, np.int64)
    twopi = 2.0 * math.pi
    for i in nb.prange(n):
        px = parents[i, 0]; py = parents[i, 1]
        d2 = scales[i] * scales[i]
        sqd = math.sqrt(d2)
        a0 = 0.0; a1 = 0.0; a2 = 0.0
        for j in range(m):
            dx = mid[j, 0] - px; dy = mid[j, 1] - py
            midr2 = dx * dx + dy * dy
            flux = (dx * normals[j, 0] + dy * normals[j, 1]) / twopi
            if midr2 < 64.0 * length2[j]:
                req = max(float(order), 8.0 * math.sqrt(length2[j]) / sqd)
                o = 2 ** int(math.ceil(math.log2(req)))
                if o > 4096:
                    bad[i] = 1
                    continue
                k = -1
                for kk in range(orders.shape[0]):
                    if orders[kk] == o:
                        k = kk
                        break
                if k < 0:
                    bad[i] = 2
                    continue
            else:
                k = 0
            s0 = offsets[k]; s1 = offsets[k + 1]
            e0 = 0.0; e1 = 0.0; e2 = 0.0
            for t in range(s0, s1):
                s = nodes[t]; w = weights[t]
                rx = dx + s * v[j, 0]; ry = dy + s * v[j, 1]
                r2 = rx * rx + ry * ry
                z = r2 / d2
                lg = math.log1p(z)
                u = math.exp((1.0 - q) * lg)
                cdf = -math.expm1((1.0 - q) * lg)
                if r2 > 0.0:
                    f = cdf / r2
                    fq = u * lg / r2
                else:
                    f = (q - 1.0) / d2
                    fq = 1.0 / d2
                fd = -2.0 * (q - 1.0) * u / (d2 + r2)
                e0 += w * f; e1 += w * fq; e2 += w * fd
            a0 += e0 * flux; a1 += e1 * flux; a2 += e2 * flux
        out[i, 0] = a0; out[i, 1] = a1; out[i, 2] = a2
    return out, bad


def masses_fast(self, parents, scales, q=None, order=16, gaussian=False, gradient=False):
    if gaussian or not gradient:
        return self._masses_original(parents, scales, q=q, order=order, gaussian=gaussian, gradient=gradient)
    parents = np.ascontiguousarray(np.asarray(parents, float).reshape(-1, 2))
    scales = np.ascontiguousarray(np.broadcast_to(np.asarray(scales, float), (len(parents),)))
    if np.any(scales <= 0) or not q > 1: raise ValueError('Invalid radial kernel')
    if order not in (8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096) and order != 2:
        raise ValueError('order must be a tabulated power of two')
    out, bad = masses_q_grad(parents, scales, float(q), int(order), np.ascontiguousarray(self.mid),
                             np.ascontiguousarray(self.v), np.ascontiguousarray(self.normals),
                             np.ascontiguousarray(self.length2), NODES, WEIGHTS, OFFSETS, ORDERS)
    if np.any(bad == 1): raise ArithmeticError('Edge integration resolution budget exceeded')
    if np.any(bad == 2): raise ArithmeticError('Untabulated Gauss order')
    if not np.all(np.isfinite(out)): raise ArithmeticError('Nonfinite boundary integral')
    return out
