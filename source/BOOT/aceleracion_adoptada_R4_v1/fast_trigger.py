"""Numba prototype of the triggering sum in MaskedLikelihood.value_gradient.

Same formulas, exact (no truncation): every parent with time < event time.
Only the evaluation order of floating-point sums differs from the NumPy version.
"""
import math
import numpy as np
import numba as nb


@nb.njit(parallel=True, fastmath=False, cache=True)
def trigger_terms(ev, h, base, prod, scale2, A, B, dm, c, p, q):
    n = ev.shape[0]
    pos2 = prod / scale2
    cpq = (p - 1.0) / c * (q - 1.0) / math.pi
    out = np.zeros((n, 9))  # trigger, SA, SB, S4, S5, S6, S7, S8, ok
    cp = (p - 1.0) / c
    cq = (q - 1.0) / math.pi
    ip = 1.0 / (p - 1.0)
    iq = 1.0 / (q - 1.0)
    for i in nb.prange(n):
        t = ev[i, 0]
        x = ev[i, 1]
        y = ev[i, 2]
        # parents strictly earlier (sorted history)
        lo = 0
        hi = h.shape[0]
        while lo < hi:
            mid = (lo + hi) // 2
            if h[mid, 0] < t:
                lo = mid + 1
            else:
                hi = mid
        stop = lo
        tr = 0.0; sa = 0.0; sb = 0.0; s4 = 0.0; s5 = 0.0; s6 = 0.0; s7 = 0.0; s8 = 0.0
        for k in range(stop):
            lag = t - h[k, 0]
            if lag <= 0.0:
                continue
            dx = x - h[k, 1]
            dy = y - h[k, 2]
            r2 = dx * dx + dy * dy
            s2 = scale2[k]
            logt = math.log1p(lag / c)
            logs = math.log1p(r2 / s2)
            w = cpq * pos2[k] * math.exp(-p * logt - q * logs)
            tr += w
            sa += w * A[k]
            sb += w * B[k]
            s4 += w * (p * lag / (c + lag) - 1.0)
            s5 += w * (ip - logt)
            s6 += w * (iq - logs)
            sd = -2.0 + 2.0 * q * r2 / (r2 + s2)
            s7 += w * sd
            s8 += w * sd * dm[k]
        out[i, 0] = tr
        out[i, 1] = sa
        out[i, 2] = sb
        out[i, 3] = s4
        out[i, 4] = s5
        out[i, 5] = s6
        out[i, 6] = s7
        out[i, 7] = s8
    return out


def value_gradient_fast(self, p):
    """Drop-in replacement for MaskedLikelihood.value_gradient (gamma=0)."""
    p.check(); h = self.h; ev = self.ev
    if p.gamma != 0: raise ValueError('Use explicit X1 objective for nonzero gamma')
    if np.any(h[:, 3] < p.m0): raise ValueError('Magnitude below explicit model support')
    dm = h[:, 3] - p.m0; prod = p.kappa * np.exp(p.alpha * dm); scale2 = (p.d0 * np.exp(p.eta * dm)) ** 2
    A = -1 / (1 - p.alpha_ratio) + p.beta * dm
    B = p.alpha_ratio * math.log(10) * dm
    base = p.mu * self.density[:len(ev)]
    T = trigger_terms(np.ascontiguousarray(ev), np.ascontiguousarray(h), base, prod, scale2,
                      np.ascontiguousarray(A), np.ascontiguousarray(B), np.ascontiguousarray(dm), p.c, p.p, p.q)
    trigger = T[:, 0]; intensity = base + trigger
    if np.any(intensity <= 0) or not np.all(np.isfinite(intensity)): return math.inf, np.full(9, np.nan)
    inverse = 1 / intensity
    value = -float(np.log(intensity).sum())
    gradient = np.zeros(9)
    gradient[0] -= float((base * inverse).sum())
    gradient[1] -= float((trigger * inverse).sum()) / p.n
    for g, col in ((2, 1), (3, 2), (4, 3), (5, 4), (6, 5), (7, 6), (8, 7)):
        gradient[g] -= float((T[:, col] * inverse).sum())
    mass = self.kernel_mass(p); lo = np.maximum(self.t0 - h[:, 0], 0); hi = self.t1 - h[:, 0]
    ulo = np.exp((1 - p.p) * np.log1p(lo / p.c)); uhi = np.exp((1 - p.p) * np.log1p(hi / p.c))
    integral = ulo - uhi
    dc = -(p.p - 1) * uhi * hi / (p.c + hi) + (p.p - 1) * ulo * lo / (p.c + lo)
    dp = uhi * np.log1p(hi / p.c) - ulo * np.log1p(lo / p.c)
    contribution = prod * mass[:, 0] * integral
    value += float(contribution.sum()) + p.mu * self.background_mass * (self.t1 - self.t0)
    gradient[0] += p.mu * self.background_mass * (self.t1 - self.t0)
    gradient[1] += float(contribution.sum()) / p.n
    gradient[2] += float(contribution @ A)
    gradient[3] += float(contribution @ B)
    gradient[4] += float((prod * mass[:, 0]) @ dc)
    gradient[5] += float((prod * mass[:, 0]) @ dp)
    gradient[6] += float((prod * integral) @ mass[:, 1])
    gradient[7] += float((prod * integral) @ mass[:, 2])
    gradient[8] += float((prod * integral * dm) @ mass[:, 2])
    value -= len(ev) * math.log(p.beta) - p.beta * float((ev[:, 3] - p.m0).sum())
    gradient[3] += -len(ev) / p.b + math.log(10) * float((ev[:, 3] - p.m0).sum())
    self.evaluations += 1
    return value, gradient
