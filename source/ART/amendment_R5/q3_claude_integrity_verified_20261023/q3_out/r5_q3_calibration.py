"""R5 Q3 - calibration of the R4 block bootstrap-t CI at realized N, fixed window.

Implements section 4 of R5_ENMIENDA_PREREGISTRADA_ANTES_DE_CALCULO_ES.md
(SHA-256 4c169541bd2ab654f838da12c45b341f2bd194f66237777470c0ff31dd2a76a8).
Fixtures and interval code are copied from R4 dimension_event_rule.py (same
worlds, same interval estimator, same bootstrap seed 20261020); the only
changes the amendment prescribes are: fixed window of T days with no stopping
or 12-month censoring, mean daily rate N_realized/T, and new seed labels.
Synthetic fixtures only: no real outcomes, no forecasts.
"""
import argparse, datetime as dt, hashlib, json, math, pathlib, sys
import numpy as np
from scipy.optimize import brentq

AMENDMENT_SHA = '4c169541bd2ab654f838da12c45b341f2bd194f66237777470c0ff31dd2a76a8'
BOOT_SEED = 20261020


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def wilson(k, n):
    from statistics import NormalDist
    z = NormalDist().inv_cdf(.975); p = k / n; den = 1 + z * z / n
    center = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [center - half, center + half]


def worlds(mechanism, dependency, ig, phase, n_real, T, trials):
    label = f'{mechanism}|{dependency}|{ig:.2f}|{phase}'
    seed = int.from_bytes(hashlib.sha256(('R5_Q3|' + label).encode()).digest()[:8], 'big')
    rng = np.random.default_rng(seed)
    lam = np.full((trials, T), n_real / T)
    if dependency == 'seven_day_cox':
        nb = math.ceil(T / 7)
        lam *= np.repeat(rng.lognormal(-.6 ** 2 / 2, .6, size=(trials, nb)), 7, axis=1)[:, :T]
    if mechanism == 'rate_only':
        r = brentq(lambda r: math.log(r) - 1 + 1 / r - ig, 1 + 1e-10, 10)
        n = rng.poisson(lam); d = n * math.log(r) - lam * (1 - 1 / r); truth = {'r': r}
    else:
        p = brentq(lambda p: p * math.log(2 * p) + (1 - p) * math.log(2 * (1 - p)) - ig, .50000001, .999999)
        a = rng.poisson(lam * p); b = rng.poisson(lam * (1 - p)); n = a + b
        d = a * math.log(2 * p) + b * math.log(2 * (1 - p)); truth = {'p': p}
    return label, seed, d, n, truth


def intervals(d, n, length, draws):
    """Verbatim logic of R4 dimension_event_rule.intervals."""
    size = d.shape[1]; groups = d.shape[0]; k = math.ceil(size / length)
    if k < 2: raise ValueError('Too few calendar blocks')
    starts = np.random.default_rng(BOOT_SEED).integers(0, size - length + 1, size=(draws, k))
    lengths = np.full(k, length); lengths[-1] = size - (k - 1) * length
    D = np.c_[np.zeros(groups), np.cumsum(d, axis=1)]; N = np.c_[np.zeros(groups), np.cumsum(n, axis=1)]
    point = d.sum(axis=1) / n.sum(axis=1)
    od = D[:, length:] - D[:, :-length]; on = N[:, length:] - N[:, :-length]
    original_se = np.sqrt((size / length) * np.var(od - point[:, None] * on, axis=1, ddof=1) * size / (size - length + 1)) / n.sum(axis=1)
    per = []; stud = []
    for first in range(groups):
        bd = D[first, starts + lengths] - D[first, starts]
        bn = N[first, starts + lengths] - N[first, starts]
        totaln = bn.sum(axis=1); g = np.divide(bd.sum(axis=1), totaln, out=np.full(draws, np.nan), where=totaln > 0)
        star_se = np.sqrt(size * np.sum((bd - g[:, None] * bn) ** 2 / lengths, axis=1) / (k - 1)) / totaln
        statistic = np.divide(g - point[first], star_se, out=np.full(draws, np.nan), where=star_se > 0)
        badp = not np.all(np.isfinite(g)); badt = not np.all(np.isfinite(statistic)) or not original_se[first] > 0
        per.append(np.quantile(g, [.025, .975]) if not badp else [np.nan, np.nan])
        if badt: stud.append([np.nan, np.nan])
        else:
            qt = np.quantile(statistic, [.025, .975])
            stud.append([point[first] - qt[1] * original_se[first], point[first] - qt[0] * original_se[first]])
    return np.asarray(per), np.asarray(stud), point


def evaluate(d, n, ig, draws, trials):
    cis = {}; point = None
    for L in (7, 14):
        per, stud, point = intervals(d, n, L, draws)
        cis[('percentile', L)] = per; cis[('bootstrap_t', L)] = stud
    methods = {}
    for method in ('percentile', 'bootstrap_t'):
        success = point > .05; coverage = {}
        for L in (7, 14):
            ci = cis[(method, L)]
            valid = np.all(np.isfinite(ci), axis=1); covers = valid & (ci[:, 0] <= ig) & (ci[:, 1] >= ig)
            success &= valid & (ci[:, 0] > .05)
            coverage[str(L)] = {'coverage': float(covers.mean()), 'wilson95': wilson(int(covers.sum()), trials),
                                'undefined': int((~valid).sum())}
        s = int(success.sum())
        methods[method] = {'successes': s, 'success_fraction': s / trials, 'wilson95': wilson(s, trials), 'coverage': coverage}
    return {'trials': trials, 'true_IG': ig, 'bootstrap_replicates': draws,
            'realized_total_N_quantiles': np.quantile(n.sum(axis=1), [.025, .5, .975]).tolist(),
            'IG_point_quantiles': np.quantile(point, [.025, .5, .975]).tolist(), 'methods': methods}


def scenario_ok(r):
    m = r['methods']['bootstrap_t']
    if any(v['coverage'] < .93 for v in m['coverage'].values()): return False
    if r['true_IG'] == .10 and m['wilson95'][0] < .80: return False
    if r['true_IG'] == .05 and m['wilson95'][1] > .07: return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n-real', type=int, required=True)
    ap.add_argument('--days', type=int, default=1024)
    ap.add_argument('--n-source', required=True, help='path to R5_Q3_N_REALIZADO.json')
    ap.add_argument('--amendment', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--trials', type=int, default=1000)
    ap.add_argument('--smoke', action='store_true', help='timing only; output is not a result')
    a = ap.parse_args()
    assert sha(a.amendment) == AMENDMENT_SHA, 'amendment hash mismatch'
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    phases = [('r5_smoke_NOT_A_RESULT', 199)] if a.smoke else [('r5_screen', 1999), ('r5_independent_validation', 9999)]
    result = {'amendment_sha256': AMENDMENT_SHA, 'script_sha256': sha(__file__), 'n_source_sha256': sha(a.n_source),
              'N_realized': a.n_real, 'window_days': a.days, 'daily_mean': a.n_real / a.days,
              'started_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'phases': {},
              'numpy': np.__version__, 'python': sys.version.split()[0]}
    for phase, draws in phases:
        rows = []
        for mechanism in ('rate_only', 'two_cell_space'):
            for dependency in ('independent', 'seven_day_cox'):
                for ig in (.05, .10):
                    label, seed, d, n, truth = worlds(mechanism, dependency, ig, phase, a.n_real, a.days, a.trials)
                    r = evaluate(d, n, ig, draws, a.trials)
                    r.update(label=label, seed=seed, truth=truth, passes=scenario_ok(r))
                    rows.append(r)
                    m = r['methods']['bootstrap_t']
                    print(phase, label, 'succ', m['success_fraction'], 'cov7', m['coverage']['7']['coverage'],
                          'cov14', m['coverage']['14']['coverage'], 'ok', r['passes'], flush=True)
        result['phases'][phase] = {'scenarios': rows, 'all_pass': all(r['passes'] for r in rows)}
        (out / f'R5_Q3_{phase}.json').write_text(json.dumps(result['phases'][phase], indent=1))
    if not a.smoke:
        result['Q3'] = 'PASS' if result['phases']['r5_independent_validation']['all_pass'] else 'FAIL'
    result.update(finished_utc=dt.datetime.now(dt.timezone.utc).isoformat(), forecasts_issued=0, seals=0,
                  real_scores_opened=False)
    (out / ('R5_Q3_SMOKE_NOT_RESULT.json' if a.smoke else 'R5_Q3_RESULT.json')).write_text(json.dumps(result, indent=1))
    print('DONE', result.get('Q3', 'SMOKE'), flush=True)


if __name__ == '__main__':
    main()
