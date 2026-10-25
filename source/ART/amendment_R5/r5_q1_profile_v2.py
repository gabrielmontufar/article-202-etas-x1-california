"""R5 Q1 - one-dimensional profile likelihood for n and d0 (diagnostic only).

Implements section 2 of the R5 amendment (SHA-256 4c169541...a76a8, commit
83ab54f) with the Q1 implementation addendum (SHA-256 f1964e84...f7f).
The R4 numerical core is imported unchanged; only parameter validation for the
profiled coordinate is relaxed through a subclass, as the addendum fixes.
No forecasts, no Q2 scores.
"""
import argparse, dataclasses, datetime as dt, hashlib, json, math, os, pathlib, sys, time
for _k in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'): os.environ[_k] = '1'
os.environ.setdefault('NUMBA_NUM_THREADS', '2')
PKG = pathlib.Path(__file__).resolve().parents[1]
ACC = PKG / 'aceleracion_adoptada_R4_v1'
sys.path.insert(0, str(PKG)); sys.path.insert(0, str(ACC))
import numpy as np

AMENDMENT_SHA = '4c169541bd2ab654f838da12c45b341f2bd194f66237777470c0ff31dd2a76a8'
ADDENDUM_SHA = 'f1964e8419c14e5cae15ddd51fceeed94ff0d25b801299f50b646ae3c7522f7f'
GRIDS = {'n': [0.70, 0.80, 0.85, 0.90, 0.93, 0.95, 0.97, 0.99],
         'd0': [0.10, 0.20, 0.30, 0.50, 0.75, 1.0, 2.0]}
REF_VALUE = {'n': 0.95, 'd0': 0.5}
COORD = {'n': 1, 'd0': 7}
ORIG = {'n': (0.01, 0.95), 'd0': (0.5, 50.0)}
SOBOL_STARTS = (1, 4, 7)
THRESH = 1.921


def sha(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def now(): return dt.datetime.now(dt.timezone.utc).isoformat()
def write(path, obj):
    tmp = path.with_suffix(path.suffix + '.tmp'); tmp.write_text(json.dumps(obj, indent=1, allow_nan=False, default=lambda o: o.item() if hasattr(o, 'item') else str(o))); os.replace(tmp, path)


def visit_order(param):
    g = GRIDS[param]; r = g.index(REF_VALUE[param])
    order = [(0, r, None)]
    for k in range(1, len(g)):
        if r - k >= 0: order.append((k, r - k, r - k + 1))
        if r + k < len(g): order.append((k, r + k, r + k - 1))
    return [(g[i], (g[nb] if nb is not None else None)) for _, i, nb in order]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--epoch', required=True, choices=['principal_2024', 'sensitivity_2016_2023'])
    ap.add_argument('--param', required=True, choices=['n', 'd0'])
    ap.add_argument('--amendment', required=True); ap.add_argument('--addendum', required=True)
    ap.add_argument('--out', required=True); ap.add_argument('--identity-only', action='store_true')
    a = ap.parse_args()
    assert sha(a.amendment) == AMENDMENT_SHA and sha(a.addendum) == ADDENDUM_SHA, 'registered text mismatch'

    import run_accelerated_r4 as acc
    acc.check_package(); acc.base.guard(); backend = acc.configure_backend(); base = acc.base
    from portable_resources import resources
    with base.mutex():
        run(a, acc, base, backend, resources)


def run(a, acc, base, backend, resources):
    from point_models import ETASParameters, FIT_BOUNDS
    from r4_likelihood import MaskedLikelihood
    from scipy.optimize import minimize
    from scipy.stats import qmc

    relaxed = {'n': (0.01, 0.99), 'd0': (0.10, 50.0)}[a.param]

    @dataclasses.dataclass(frozen=True)
    class ProfileParams(ETASParameters):
        def check(self):
            v = dataclasses.asdict(self)
            if not all(math.isfinite(x) for x in v.values()): raise ValueError('Nonfinite parameters')
            n_lo, n_hi = relaxed if a.param == 'n' else ORIG['n']
            d_lo, d_hi = relaxed if a.param == 'd0' else ORIG['d0']
            ok = (0 <= self.m0 < 8 and 1e-6 <= self.mu <= 1e4 and n_lo <= self.n <= n_hi + 1e-15
                  and 0 <= self.alpha_ratio <= .95 and .5 <= self.b <= 2 and .001 <= self.c <= 1
                  and 1.01 <= self.p <= 2.5 and 1.01 <= self.q <= 3 and d_lo - 1e-15 <= self.d0 <= d_hi
                  and 0 <= self.eta <= math.log(10) / 2 and self.gamma == 0)
            if not ok: raise ValueError('Parameter outside profile bounds')
            return self

    def make(x):
        mu = min(1e4, max(1e-6, math.exp(x[0]))); c = min(1., max(.001, math.exp(x[4])))
        d0 = min(50., math.exp(x[7]))
        if a.param != 'd0': d0 = max(.5, d0)
        return ProfileParams(mu, x[1], x[2], x[3], c, x[5], x[6], d0, x[8], 0., 2.5)

    h, flags, domain, radius, bounds = base.inputs(); t0, t1 = bounds[a.epoch]
    sel = h[:, 0] < t1; hh = h[sel]; ff = flags[sel]
    L = MaskedLikelihood(hh, ff, domain, radius, t0, t1, order=16)
    ref_path = PKG / 'work' / 'references' / f'{a.epoch}.json'; ref = json.loads(ref_path.read_text())
    x_ref = np.array(ref['x'], float)
    out = pathlib.Path(a.out) / a.epoch / a.param; out.mkdir(parents=True, exist_ok=True)
    context = {'script_sha256': sha(__file__), 'amendment_sha256': AMENDMENT_SHA, 'addendum_sha256': ADDENDUM_SHA,
               'reference_capsule_sha256': sha(ref_path), 'epoch': a.epoch, 'param': a.param}
    ctx_path = out / 'RUN_CONTEXT.json'
    if ctx_path.exists():
        assert json.loads(ctx_path.read_text()) == context, 'CONTEXT_MISMATCH: do not mix checkpoints from another script/reference'
    else:
        if any(out.iterdir()): raise RuntimeError('CONTEXT_MISSING_IN_NONEMPTY_FOLDER: use a new output folder')
        write(ctx_path, context)

    ident_path = out / 'IDENTITY_CONTROL.json'
    if not ident_path.exists():
        v = float(L.value_gradient(make(x_ref))[0])
        rel = float(abs(v - ref['nll']) / abs(ref['nll']))
        write(ident_path, {'epoch': a.epoch, 'reference_capsule_sha256': sha(ref_path), 'capsule_nll': ref['nll'],
                           'r5_nll': v, 'relative_difference': rel, 'tolerance': 1e-9, 'pass': bool(rel <= 1e-9),
                           'backend': backend, 'utc': now()})
    ident = json.loads(ident_path.read_text()); print('IDENTITY', ident['pass'], ident['relative_difference'], flush=True)
    if not ident['pass']:
        write(out / 'Q1_HOLD.json', {'status': 'HOLD_IDENTITY_CONTROL_FAILED', 'utc': now()}); return
    if a.identity_only: return

    k = COORD[a.param]
    design = qmc.Sobol(9, scramble=True, seed=20261020).random_base2(3)
    solved = {}
    for value, neighbour in visit_order(a.param):
        xv = value if a.param == 'n' else math.log(value)
        pdir = out / f'point_{value:g}'; pdir.mkdir(exist_ok=True)
        res_path = pdir / 'POINT_RESULT.json'
        if res_path.exists():
            solved[value] = json.loads(res_path.read_text()); continue
        bnds = list(FIT_BOUNDS); bnds[k] = (xv, xv)
        inits = [('warm_reference', x_ref.copy())]
        neighbour_note = None
        if neighbour is not None and 'best_x' in solved[neighbour]:
            inits.append(('warm_neighbour_' + format(neighbour, 'g'), np.array(solved[neighbour]['best_x'], float)))
        elif neighbour is not None:
            neighbour_note = 'NEIGHBOUR_ALL_STARTS_FAILED_NO_WARM_NEIGHBOUR_START'
        for j in SOBOL_STARTS:
            inits.append((f'sobol_{j}', np.array([lo + (hi - lo) * u for (lo, hi), u in zip(FIT_BOUNDS, design[j])])))
        rows = []
        for name, x0 in inits:
            x0 = x0.copy(); x0[k] = xv
            x0 = np.array([min(max(v_, lo), hi) for v_, (lo, hi) in zip(x0, bnds)])
            ck = pdir / f'start_{name}.json'
            if ck.exists(): rows.append(json.loads(ck.read_text())); continue
            current = resources()
            if current['free_RAM_MiB'] < 512 or current['free_disk_GiB'] < 4:
                raise RuntimeError('RESOURCE_HOLD_BEFORE_Q1_START: ' + json.dumps(current))
            started = time.monotonic(); calls = 0
            def objective(x):
                nonlocal calls
                calls += 1; val, g = L.value_gradient(make(x))
                if calls == 1 or calls % 10 == 0:
                    print('Q1', a.epoch, a.param, value, name, 'call', calls, 'nll', val, 'elapsed', round(time.monotonic() - started), flush=True)
                g = np.array(g, float); g[k] = 0.0
                return val, g
            try:
                opt = minimize(objective, x0, jac=True, method='L-BFGS-B', bounds=bnds,
                               options={'maxiter': 1000, 'maxfun': 20000, 'ftol': 1e-10, 'gtol': 1e-5})
                row = {'start': name, 'x_initial': x0.tolist(), 'success': bool(opt.success), 'message': str(opt.message),
                       'nll': float(opt.fun), 'x': opt.x.tolist(), 'iterations': int(opt.nit), 'calls': calls,
                       'elapsed_seconds': time.monotonic() - started,
                       'other_active_bounds': [i for i, (v_, (lo, hi)) in enumerate(zip(opt.x, FIT_BOUNDS))
                                               if i != k and min(v_ - lo, hi - v_) < 1e-5]}
            except Exception as e:
                row = {'start': name, 'success': False, 'error': repr(e), 'calls': calls}
            write(ck, row); rows.append(row)
            print('Q1_START_DONE', a.epoch, a.param, value, name, row.get('success'), row.get('nll'), flush=True)
        valid = [r for r in rows if r.get('success') and math.isfinite(r.get('nll', math.inf))]
        if not valid:
            res = {'value': value, 'status': 'ALL_STARTS_FAILED', 'starts': rows, 'neighbour_note': neighbour_note}
        else:
            best = min(valid, key=lambda r: r['nll']); p = make(np.array(best['x']))
            v16 = L.value_gradient(p)[0]; refs = []
            for order in (32, 64):
                L.order = order; refs.append({'order': order, 'nll': L.value_gradient(p)[0]})
            L.order = 16
            refined = domain.from_geographic_cells([[ix / 10 - 180, iy / 10 - 90] for ix, iy in sorted(domain.cells)], subdivide=2)
            refs.append({'order': 64, 'geographic_subdivision': 2,
                         'nll': MaskedLikelihood(hh, ff, refined, radius, t0, t1, order=64).value_gradient(p)[0]})
            for r in refs: r['absolute_delta_per_target'] = abs(r['nll'] - v16) / len(L.ev)
            qa = all(r['absolute_delta_per_target'] <= 1e-3 for r in refs)
            res = {'value': value, 'status': 'QA_PASS' if qa else 'NUMERICAMENTE_NO_FIABLE', 'best_start': best['start'],
                   'best_nll': best['nll'], 'best_x': best['x'], 'parameters': dataclasses.asdict(p),
                   'refinements': refs, 'starts': rows, 'neighbour': neighbour, 'neighbour_note': neighbour_note, 'n_starts': len(inits)}
        res['utc'] = now(); write(res_path, res); solved[value] = res

    pts = [solved[v] for v in GRIDS[a.param] if 'best_nll' in solved[v]]
    failed = [v for v in GRIDS[a.param] if 'best_nll' not in solved[v]]
    unreliable = [p['value'] for p in pts if p['status'] != 'QA_PASS']
    m = min(p['best_nll'] for p in pts) if pts else None
    for p in pts: p['delta_nll'] = p['best_nll'] - m
    inset = [p['value'] for p in pts if p['delta_nll'] <= THRESH]
    lo, hi = ORIG[a.param]; vmin = min(pts, key=lambda p: p['best_nll'])['value'] if pts else None
    grid = GRIDS[a.param]
    # Registered rule (amendment s.2), applied only to a complete, QA-passing profile.
    if failed or unreliable:
        cls = 'SIN_CLASIFICAR_PERFIL_INCOMPLETO_O_NO_FIABLE'
    elif len(inset) == len(grid):
        cls = 'NO_IDENTIFICADO'
    elif any(v >= hi or v <= lo for v in inset):
        cls = 'LIMITADO_POR_COTA'
    elif vmin not in (grid[0], grid[-1]):
        cls = 'IDENTIFICADO_DENTRO_DE_COTA'
    else:
        # Minimum at an examined-grid end that is not an original bound: neither
        # registered class applies; reported as such, no new inferential rule.
        cls = 'SIN_CLASE_REGISTRADA_MINIMO_EN_EXTREMO_DE_REJILLA'
    summary = {'epoch': a.epoch, 'param': a.param, 'classification': cls, 'threshold_delta_nll': THRESH,
               'profile': [{'value': p['value'], 'best_nll': p['best_nll'], 'delta_nll': p['delta_nll'], 'status': p['status'],
                            'best_start': p['best_start']} for p in pts],
               'failed_points': failed, 'numerically_unreliable_points': unreliable,
               'profile_set_95': inset, 'argmin': vmin, 'original_bounds': [lo, hi],
               'amendment_sha256': AMENDMENT_SHA, 'addendum_sha256': ADDENDUM_SHA, 'script_sha256': sha(__file__),
               'reference_capsule_sha256': sha(ref_path), 'forecasts_issued': 0, 'Q2_scored': False, 'utc': now()}
    write(out / 'Q1_PROFILE_SUMMARY.json', summary); print('Q1_DONE', a.epoch, a.param, cls, flush=True)


if __name__ == '__main__':
    main()
