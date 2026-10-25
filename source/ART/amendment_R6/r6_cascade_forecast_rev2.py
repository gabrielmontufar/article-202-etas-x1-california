"""R6 preregistered robustness: six ETAS starts, gamma, analytic + cascade means.

DRAFT FOR EXACT-BYTE REVIEW. No numerical stage runs without a matching Claude receipt.
R4/R5 sources and final results remain read-only. No operational issuance.
"""
from pathlib import Path
import argparse
import contextlib
import csv
import ctypes
import datetime as dt
import hashlib
import importlib.metadata
import json
import math
import os
import shutil
import sqlite3
import subprocess
import sys
import traceback
import types
import uuid

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / 'amendment_R6'
R5_HERE = ROOT / 'amendment_R5'
CACHE = Path('C:/Users/gjm31/forge_cache/panama_probabilistic_20261020/amendment_20261021')
LOCK_PATH = R5_HERE / 'R5_Q2_SOURCE_LOCK_20261023.json'
LOCK_SHA = 'ab48b2bde320223d9f298c7fcf9934b1d189c990760b91756f562feaf25b81e1'
REGISTRATION = HERE / 'R6_REGISTRO_SCRIPT.json'
START = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc)
END = dt.datetime(2026, 10, 21, 3, 21, 46, 320144, tzinfo=dt.timezone.utc)
EPOCH = dt.datetime(1990, 1, 1, tzinfo=dt.timezone.utc)
GAMMA = 0.09335882678597657
MODELS = ('ETAS', 'ETAS_X1')
N_EXPECTED, NCELLS, NDAYS = 2122, 4296, 1025


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def write_json(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def artifact(path, base):
    path = Path(path)
    return {'path': path.relative_to(base).as_posix(), 'sha256': sha(path),
            'bytes': path.stat().st_size}


def checked_artifact(base, record):
    path = (base / record['path']).resolve()
    require(path.is_relative_to(base.resolve()), 'Unsafe artifact path')
    require(path.stat().st_size == record['bytes'] and sha(path) == record['sha256'],
            'Artifact bytes changed: ' + str(path))
    return path


def resources():
    class Memory(ctypes.Structure):
        _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [
            (name, ctypes.c_ulonglong) for name in
            ('total', 'available', 'page_total', 'page_available', 'virtual_total',
             'virtual_available', 'extended_available')]
    require(sys.platform == 'win32', 'This registered runner is for Windows')
    memory = Memory()
    memory.length = ctypes.sizeof(memory)
    require(ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)),
            'Cannot measure free RAM')
    return {'free_RAM_MiB': memory.available / 2**20,
            'free_disk_GiB': shutil.disk_usage('C:/').free / 2**30}


def guard(reserve_bytes=0):
    values = resources()
    require(values['free_RAM_MiB'] >= 512 and
            values['free_disk_GiB'] >= 4 + reserve_bytes / 2**30,
            'RESOURCE_HOLD ' + json.dumps(values))
    return values


@contextlib.contextmanager
def single_worker():
    """Same R4 process locks, plus an external Python-worker inventory; no kills."""
    import msvcrt
    guard()
    folder = CACHE / 'R4/masked_diagnostic_authorized_20261021'
    handles = []
    try:
        for filename in ('controller.mutex', 'worker.mutex'):
            handle = (folder / filename).open('a+b')
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            handles.append(handle)
        command = ('Get-CimInstance Win32_Process -Filter '
                   '"Name = \'python.exe\' OR Name = \'pythonw.exe\'" | '
                   'Select-Object ProcessId,ParentProcessId,CreationDate,CommandLine | '
                   'ConvertTo-Json -Compress')
        raw = subprocess.check_output(['powershell.exe', '-NoProfile', '-NonInteractive',
                                       '-Command', command], text=True, timeout=30)
        rows = json.loads(raw) if raw.strip() else []
        rows = rows if isinstance(rows, list) else [rows]
        own = [r for r in rows if r['ProcessId'] == os.getpid()]
        require(len(own) == 1, 'Own process identity not established')
        allowed = {os.getpid()}
        # A Windows venv shim is allowed only as our actual parent, running this file.
        for row in rows:
            if row['ProcessId'] == own[0]['ParentProcessId']:
                require(str(Path(__file__)).lower() in str(row['CommandLine']).lower(),
                        'Unidentified Python parent')
                allowed.add(row['ProcessId'])
        require(all(r['ProcessId'] in allowed for r in rows),
                'Another Python worker is present; preserve it and stop R6')
        kernel = ctypes.windll.kernel32
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        kernel.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        require(kernel.SetPriorityClass(kernel.GetCurrentProcess(), 0x4000),
                'Cannot set BelowNormal priority')
        yield rows
    finally:
        for handle in reversed(handles):
            handle.close()


def runtime(run, stage):
    global np
    for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
        os.environ[name] = '1'
    os.environ['NUMBA_NUM_THREADS'] = '3'
    os.environ['NUMBA_CACHE_DIR'] = str(run / 'numba_cache')
    sys.path.insert(0, str(ROOT / 'scripts'))
    sys.path.insert(0, str(ROOT.parent / 'bootstrap_nube_R4/aceleracion_adoptada_R4_v1'))
    import numpy as np
    if stage == 'score':
        return types.SimpleNamespace(np=np)
    import numba
    from point_models import Background, ETASParameters, temporal_cdf
    from polygon_integration import PolygonIntegrator
    from r4_likelihood import MaskedLikelihood
    from fast_polygon import masses_fast
    numba.set_num_threads(3)
    require(numba.get_num_threads() == 3, 'Thread setting failed')
    integral = numba.njit(cache=True, fastmath=False)(frozen_z_integral)
    return types.SimpleNamespace(np=np, Background=Background, Parameters=ETASParameters,
                                 cdf=temporal_cdf, Polygon=PolygonIntegrator,
                                 Masked=MaskedLikelihood, masses_fast=masses_fast,
                                 z_integral=integral)


def calendar():
    starts = [START + dt.timedelta(days=i) for i in range(NDAYS)]
    ends = [min(s + dt.timedelta(days=1), END) for s in starts]
    require(starts[-1] < END < starts[-1] + dt.timedelta(days=1), 'Partial-day definition')
    return starts, ends


def frozen_z_integral(times, starts, ends, gamma):
    """R4 covariate_measure time cuts, with a different frozen past each day.

    Numba compiles this only after review. No simulated or within-day parents.
    The original R4 routine is independently compared at fixed calendar positions.
    """
    result = starts.copy()
    for day in range(len(starts)):
        a, b = starts[day], ends[day]
        lo = np.searchsorted(times, a - 30.0, side='left')
        hi = np.searchsorted(times, a, side='left')
        past = times[lo:hi]
        # The prefix is materialized before temporal cut construction: future
        # neighbour times cannot enter z, including events within [a,b).
        cuts = [a, b]
        for value in past:
            if a < value + 7.0 < b:
                cuts.append(value + 7.0)
            if a < value + 30.0 < b:
                cuts.append(value + 30.0)
        cuts.sort()
        total = 0.0
        for j in range(len(cuts) - 1):
            middle = (cuts[j] + cuts[j + 1]) / 2.0
            n30 = len(past) - np.searchsorted(past, middle - 30.0, side='left')
            n7 = len(past) - np.searchsorted(past, middle - 7.0, side='left')
            z = min(2.0, max(-2.0, math.log1p(n7) - math.log1p(7.0 * n30 / 30.0)))
            total += (cuts[j + 1] - cuts[j]) * math.exp(gamma * z)
        result[day] = total
    return result


def cell_quadrature(engine, cell, background, order):
    """Same points/AEQD quadrilateral areas/weights as R4 covariate_measure."""
    np = engine.np
    nodes, weights = np.polynomial.legendre.leggauss(order)
    ix, iy = next(iter(cell.cells))
    lon, lat = ix / 10 - 180, iy / 10 - 90
    x, y = cell.transformer.transform([lon, lon + .1, lon + .1, lon],
                                      [lat, lat, lat + .1, lat + .1])
    area = abs(sum(x[k] * y[(k + 1) % 4] - x[(k + 1) % 4] * y[k]
                   for k in range(4))) / 2e6
    points, areas = [], []
    for a, wa in zip(nodes, weights):
        for b, wb in zip(nodes, weights):
            px, py = cell.transformer.transform(lon + .05 * (1 + a), lat + .05 * (1 + b))
            points.append([px / 1000, py / 1000])
            areas.append(area * wa * wb / 4)
    points = np.array(points)
    return points, background.density(points) * np.asarray(areas)


def modulated_mass(engine, cell, background, tree, history, starts, ends, order):
    np = engine.np
    points, weights = cell_quadrature(engine, cell, background, order)
    result = np.zeros(NDAYS)
    for point, weight in zip(points, weights):
        times = np.sort(history[tree.query_ball_point(point, 50), 0])
        result += weight * engine.z_integral(times, starts, ends, GAMMA)
    # Compare the optimized frozen-history adapter to the unchanged R4 routine.
    # Positions are fixed before outcomes: first, middle, final fractional day.
    parity = []
    for day in (0, NDAYS // 2, NDAYS - 1):
        a, b = starts[day], ends[day]
        state = types.SimpleNamespace(domain=cell, bg=background, t0=a, t1=b,
                                      h=history[(history[:, 0] >= a - 30) & (history[:, 0] < a)])
        z, mass, unused = engine.Masked.covariate_measure(state, cell_order=order)
        original = float(mass @ np.exp(GAMMA * z))
        delta = abs(original - result[day])
        require(delta <= 1e-12 + 1e-10 * abs(original), 'Frozen z adapter disagrees with R4')
        parity.append({'day': day, 'absolute_difference': delta})
    return result, float(weights.sum()), parity


def radial_mass(engine, domain, history, scales, p, order):
    domain._masses_original = domain.masses
    return engine.masses_fast(domain, history[:, 1:3], scales, q=p.q,
                              order=order, gradient=True)[:, 0]


def mass_qa(np, values, refined, label, evidence_dir, *, check_difference=True):
    delta = np.abs(values - refined)
    passed = (np.all(np.isfinite(values)) and np.all(np.isfinite(refined)) and
              np.all((values >= -1e-5) & (values <= 1 + 1e-5)) and
              np.all((refined >= -1e-5) & (refined <= 1 + 1e-5)) and
              (not check_difference or np.all(delta <= 1e-5 + 1e-3 * np.abs(refined))))
    if not passed:
        path = evidence_dir / ('FAILED_MASS_' + uuid.uuid4().hex + '.npz')
        with path.open('xb') as stream:
            np.savez(stream, values=values, refined=refined, absolute_delta=delta)
        raise ArithmeticError(label + ': nonfinite/R4 mass range/tolerance failure; raw evidence ' + str(path))
    return float(delta.max(initial=0))


def temporal_weights(engine, run, history, starts, ends, p, definition_sha):
    np = engine.np
    receipt = run / 'TEMPORAL_WEIGHTS.json'
    if receipt.exists():
        record = read(receipt)
        require(record['definition_sha256'] == definition_sha, 'Temporal context changed')
        return np.load(checked_artifact(run, record['artifact']), mmap_mode='r', allow_pickle=False)
    guard(NDAYS * len(history) * 8)
    path = run / ('temporal_weights_' + uuid.uuid4().hex + '.npy')
    weights = np.lib.format.open_memmap(path, mode='w+', dtype='float64', shape=(NDAYS, len(history)))
    productivity = p.kappa * np.exp(p.alpha * (history[:, 3] - p.m0))
    for day, (a, b) in enumerate(zip(starts, ends)):
        guard()
        stop = int(np.searchsorted(history[:, 0], a, side='left'))
        weights[day] = 0
        past = history[:stop, 0]
        require(np.all(past < a), 'Future parent in temporal weights')
        weights[day, :stop] = productivity[:stop] * (engine.cdf(b - past, p.c, p.p) -
                                                    engine.cdf(a - past, p.c, p.p))
        require(np.all(np.isfinite(weights[day])) and np.all(weights[day] >= 0),
                'Invalid temporal integral')
        weights.flush()
    weights.flush()
    del weights
    write_json(receipt, {'definition_sha256': definition_sha, 'artifact': artifact(path, run),
                        'future_parent_weights_exactly_zero': True, 'utc': now()})
    return np.load(path, mmap_mode='r', allow_pickle=False)


def generate_controls(engine, lock, definition, run, resume):
    np = engine.np
    from scipy.spatial import cKDTree
    sources = lock['sources']
    definition_sha = hashlib.sha256(json.dumps(definition, sort_keys=True).encode()).hexdigest()
    context_path = run / 'RUN_CONTEXT.json'
    if context_path.exists():
        require(resume and read(context_path)['definition'] == definition, 'Existing run; explicit matching resume required')
    else:
        write_json(context_path, {'definition': definition, 'definition_sha256': definition_sha,
                                  'utc': now(), 'pid': os.getpid(), 'python': sys.version,
                                  'pins': lock['environment_pins'], 'resources': guard()})
    require(not (run / 'FORECASTS_COMPLETE.json').exists(), 'Generation already completed; do not repeat')
    with np.load(sources['prepared_history']['path'], allow_pickle=False) as data:
        history = data['history'].copy()
        flags = data['target_flags'].copy()
    require(history.shape[1] == 4 and np.all(np.isfinite(history)) and
            np.all(np.diff(history[:, 0]) >= 0), 'Invalid prepared history')
    prep = read(sources['prepared_receipt']['path'])
    cap = read(sources['capsule']['path'])
    require(prep['event_treatment'] == 'keep_unknown' and prep['prepared_npz_sha256'] ==
            cap['input_sha256'] == sources['prepared_history']['sha256'], 'Prepared lineage mismatch')
    p = engine.Parameters(**definition['model_parameters']['ETAS']).check()
    all_starts, all_ends = calendar()
    starts = np.array([(s - EPOCH).total_seconds() / 86400 for s in all_starts])
    ends = np.array([(s - EPOCH).total_seconds() / 86400 for s in all_ends])
    training_start = (dt.datetime(2016, 1, 1, tzinfo=dt.timezone.utc) - EPOCH).days
    training = history[flags & (history[:, 0] >= training_start) & (history[:, 0] < starts[0])]
    require(len(training) == 9025, 'Historical training membership changed')
    background = engine.Background(training[:, 1:3], prep['parent_radius_km'])
    # No observed event from the final partial day is required for any forecast.
    history = history[history[:, 0] < starts[-1]]
    cells = sorted(read(sources['support']['path'])['cells'])
    require(len(cells) == NCELLS and len({tuple(c) for c in cells}) == NCELLS, 'Wrong cell support')
    scales = p.d0 * np.exp(p.eta * (history[:, 3] - p.m0))
    tree = cKDTree(history[:, 1:3])
    weights = temporal_weights(engine, run, history, starts, ends, p, definition_sha)
    # Sum the unchanged daily weights once for the window-wide geographic QA.
    window_parent_weights = np.asarray(weights).sum(axis=0)
    (run / 'cells').mkdir(exist_ok=True)
    mass_sum = np.zeros(len(history))
    gaussian_mass_sum = np.zeros(len(background.xy))
    # Dictamen 6: geographic refinement is an R4-style domain aggregate; per cell only gross check.
    geo_totals = {'primary': 0.0, 'refined': 0.0, 'etas': 0.0}
    cell_receipts = []
    for index, origin in enumerate(cells):
        guard((len(history) + len(background.xy)) * 8 + 1025 * 16)
        receipt_path = run / 'cells' / ('cell_%04d.json' % index)
        if receipt_path.exists():
            require(resume, 'Existing cell without resume request')
            receipt = read(receipt_path)
            require(receipt['definition_sha256'] == definition_sha and
                    receipt['index'] == index and receipt['origin'] == origin and
                    receipt['status'] == 'CELL_FORECASTS_QA_PASS', 'Cell context conflict')
            with np.load(checked_artifact(run, receipt['payload']), allow_pickle=False) as saved:
                mass_sum += saved['parent_mass64']
                gaussian_mass_sum += saved['gaussian_mass64']
            saved_geo = receipt['QA']['geographic_subdivision_window_trigger']
            geo_totals['primary'] += saved_geo['trigger_order64_total']
            geo_totals['refined'] += saved_geo['trigger_order64_subdivision2_total']
            geo_totals['etas'] += saved_geo['ETAS_total_expected']
            cell_receipts.append(artifact(receipt_path, run))
            continue
        cell = engine.Polygon.from_geographic_cells([origin])
        refined = engine.Polygon.from_geographic_cells([origin], subdivide=2)
        m32 = radial_mass(engine, cell, history, scales, p, 32)
        m64 = radial_mass(engine, cell, history, scales, p, 64)
        m128 = radial_mass(engine, cell, history, scales, p, 128)
        m64s = radial_mass(engine, refined, history, scales, p, 64)
        delta32 = mass_qa(np, m32, m64, '32/64 parent-cell integral', run)
        delta64 = mass_qa(np, m64, m128, '64/128 parent-cell integral', run)
        # Geographic refinement changes the projected boundary. Keep its finite/range
        # checks here; compare expected triggering over the whole window below.
        delta_sub = mass_qa(np, m64, m64s, 'Geographic subdivision mass range', run,
                            check_difference=False)
        gaussian = cell.masses(background.xy, background.h, gaussian=True, order=64)
        gaussian_pass = (np.all(np.isfinite(gaussian)) and
                         np.all((gaussian >= -1e-5) & (gaussian <= 1 + 1e-5)))
        if not gaussian_pass:
            path = run / ('FAILED_GAUSSIAN_' + uuid.uuid4().hex + '.npz')
            with path.open('xb') as stream:
                np.savez(stream, gaussian=gaussian, cell_origin=np.asarray(origin))
            raise ArithmeticError('Gaussian cell R4 mass range failure; raw evidence ' + str(path))
        base_mass = .95 * gaussian.sum() / (len(background.xy) * background.Z) + .05 * cell.area / (math.pi * background.R**2)
        require(math.isfinite(base_mass) and base_mass > 0, 'Nonpositive or nonfinite KDE cell mass')
        mass2, zero2, parity2 = modulated_mass(engine, cell, background, tree, history, starts, ends, 2)
        mass4, zero4, parity4 = modulated_mass(engine, cell, background, tree, history, starts, ends, 4)
        # Dictamen 5: z is a step field (50 km / 7-30 d counts), so the per-day order 2/4
        # comparison is a sensitivity diagnostic; the stopping QA uses the window total.
        x1_window_order2 = float(mass2.sum())
        x1_window_order4 = float(mass4.sum())
        x1_window_delta = abs(x1_window_order2 - x1_window_order4)
        x1_daily_over = int(np.count_nonzero(np.abs(mass2 - mass4) > 1e-5 + .005 * np.abs(mass4)))
        background_pass = (np.all(np.isfinite(mass2)) and np.all(np.isfinite(mass4)) and
                           np.all(mass4 > 0) and
                           x1_window_delta <= 1e-5 + .005 * abs(x1_window_order4) and
                           abs(zero4 - base_mass) <= 1e-5 + .005 * abs(base_mass))
        if not background_pass:
            path = run / ('FAILED_BACKGROUND_' + uuid.uuid4().hex + '.npz')
            with path.open('xb') as stream:
                np.savez(stream, order2=mass2, order4=mass4, gamma0=zero4, base_mass=base_mass,
                         cell_origin=np.asarray(origin))
            raise ArithmeticError('R4 X1 background QA failure; raw evidence ' + str(path))
        trigger = np.asarray(weights) @ m64
        etas = trigger + p.mu * base_mass * (ends - starts)
        x1 = trigger + p.mu * mass4
        require(np.all(np.isfinite(etas)) and np.all(etas > 0) and
                np.all(np.isfinite(x1)) and np.all(x1 > 0), 'Nonpositive or nonfinite daily intensity')
        geographic_trigger_primary = float(trigger.sum())
        geographic_trigger_refined = float(window_parent_weights @ m64s)
        geographic_etas_total = float(etas.sum())
        geographic_delta = abs(geographic_trigger_primary - geographic_trigger_refined)
        geographic_tolerance = 1e-2 * geographic_etas_total
        geographic_parent_count = int(np.count_nonzero(
            np.abs(m64 - m64s) > 1e-5 + 1e-3 * np.abs(m64s)))
        if not (math.isfinite(geographic_trigger_primary) and
                math.isfinite(geographic_trigger_refined) and
                math.isfinite(geographic_etas_total) and geographic_etas_total > 0 and
                geographic_delta <= geographic_tolerance):
            path = run / ('FAILED_GEOGRAPHIC_WINDOW_' + uuid.uuid4().hex + '.npz')
            with path.open('xb') as stream:
                np.savez(stream, order64=m64, order64_subdivision2=m64s,
                         window_parent_weights=window_parent_weights, ETAS=etas,
                         trigger_primary=geographic_trigger_primary,
                         trigger_subdivision2=geographic_trigger_refined,
                         absolute_delta=geographic_delta, tolerance=geographic_tolerance,
                         parent_absolute_delta_max=delta_sub,
                         parents_above_mass_tolerance=geographic_parent_count,
                         cell_origin=np.asarray(origin))
            raise ArithmeticError('Geographic subdivision window-trigger QA failure; raw evidence ' + str(path))
        geographic_qa = {
            'scope': 'one_cell_all_days_common_trigger_expected_counts',
            'trigger_order64_total': geographic_trigger_primary,
            'trigger_order64_subdivision2_total': geographic_trigger_refined,
            'ETAS_total_expected': geographic_etas_total,
            'absolute_delta': geographic_delta,
            'relative_delta_to_ETAS_total': geographic_delta / geographic_etas_total,
            'absolute_tolerance': geographic_tolerance, 'relative_tolerance': 1e-2,
            'per_cell_role': 'gross_error_stop_only; R4-style 1e-3 test is the domain aggregate',
            'parent_absolute_delta_max': delta_sub,
            'parents_above_mass_tolerance_diagnostic_only': geographic_parent_count,
            'pass': True}
        payload = run / 'cells' / ('cell_%04d_%s.npz' % (index, uuid.uuid4().hex))
        with payload.open('xb') as stream:
            np.savez(stream, ETAS=etas, ETAS_X1=x1, parent_mass64=m64,
                     gaussian_mass64=gaussian)
            stream.flush()
            os.fsync(stream.fileno())
        receipt = {'utc': now(), 'status': 'CELL_FORECASTS_QA_PASS', 'index': index,
                   'origin': origin, 'definition_sha256': definition_sha,
                   'payload': artifact(payload, run),
                   'gaussian_mass_diagnostics': {
                       'negative_count': int(np.count_nonzero(gaussian < 0)),
                       'minimum': float(gaussian.min()), 'maximum': float(gaussian.max()),
                       'negative_signed_sum': float(gaussian[gaussian < 0].sum()),
                       'sum': float(gaussian.sum()), 'base_mass': float(base_mass)},
                   'parent_mass_diagnostics': {
                       label: {'negative_count': int(np.count_nonzero(values < 0)),
                               'minimum': float(values.min())}
                       for label, values in [('order32', m32), ('order64', m64), ('order128', m128),
                                             ('order64_subdivision2', m64s)]},
                   'QA': {'parent_mass_abs_delta32_64': delta32,
                          'parent_mass_abs_delta64_128': delta64,
                          'parent_mass_abs_delta_subdivision2': delta_sub,
                          'geographic_subdivision_window_trigger': geographic_qa,
                          'X1_abs_delta_order2_4_max': float(np.max(np.abs(mass2 - mass4))),
                          'X1_window_total_order2': x1_window_order2,
                          'X1_window_total_order4': x1_window_order4,
                          'X1_window_relative_delta': x1_window_delta / x1_window_order4,
                          'X1_daily_days_above_R4_tolerance_diagnostic_only': x1_daily_over,
                          'X1_daily_max_relative_delta': float(np.max(np.abs(mass2 - mass4) / mass4)),
                          'gamma0_absolute_mass_delta': float(abs(zero4 - base_mass)),
                          'R4_measure_parity_order2': parity2, 'R4_measure_parity_order4': parity4},
                   'no_within_day_parents': True, 'no_mass_clipping_or_renormalization': True}
        write_json(receipt_path, receipt)
        cell_receipts.append(artifact(receipt_path, run))
        mass_sum += m64
        gaussian_mass_sum += gaussian
        geo_totals['primary'] += geographic_trigger_primary
        geo_totals['refined'] += geographic_trigger_refined
        geo_totals['etas'] += geographic_etas_total
        print(json.dumps({'stage': 'GENERATING', 'cell_complete': index + 1,
                          'cells': NCELLS, 'scores_computed': False}), flush=True)
    # Domain aggregate geographic refinement QA (R4 scope), tolerance 1e-3 of total ETAS expectation.
    geo_delta = abs(geo_totals['primary'] - geo_totals['refined'])
    geo_domain = {'trigger_order64_total': geo_totals['primary'],
                  'trigger_order64_subdivision2_total': geo_totals['refined'],
                  'ETAS_total_expected': geo_totals['etas'], 'absolute_delta': geo_delta,
                  'relative_delta_to_ETAS_total': geo_delta / geo_totals['etas'],
                  'relative_tolerance': 1e-3, 'cells': len(cell_receipts),
                  'pass': bool(math.isfinite(geo_delta) and geo_delta <= 1e-3 * geo_totals['etas'])}
    geo_path = run / ('GEOGRAPHIC_DOMAIN_QA_' + uuid.uuid4().hex + '.json')
    write_json(geo_path, geo_domain)
    require(geo_domain['pass'], 'Domain geographic subdivision QA failure; evidence ' + str(geo_path))
    # Internal cell edges must cancel; verify their sum against the exact union.
    guard()
    union = engine.Polygon.from_geographic_cells(cells)
    union_mass = radial_mass(engine, union, history, scales, p, 64)
    union_delta = mass_qa(np, mass_sum, union_mass, 'Sum of cells versus R4 union', run)
    gaussian_union = union.masses(background.xy, background.h, gaussian=True, order=64)
    gaussian_union_path = run / ('GAUSSIAN_UNION_' + uuid.uuid4().hex + '.npz')
    with gaussian_union_path.open('xb') as stream:
        np.savez(stream, sum_cells=gaussian_mass_sum, union=gaussian_union,
                 absolute_delta=np.abs(gaussian_mass_sum - gaussian_union),
                 tolerance=1e-5 + 1e-3 * np.abs(gaussian_union))
    gaussian_union_delta = mass_qa(np, gaussian_mass_sum, gaussian_union,
                                  'Gaussian sum of cells versus R4 union', run)
    assembly = run / ('assembled_' + uuid.uuid4().hex)
    assembly.mkdir()
    arrays = {}
    for model in MODELS:
        guard(NDAYS * NCELLS * 8)
        arrays[model] = np.lib.format.open_memmap(assembly / (model + '.npy'),
                            mode='w+', dtype='float64', shape=(NDAYS, NCELLS))
    for index, record in enumerate(cell_receipts):
        receipt = read(checked_artifact(run, record))
        with np.load(checked_artifact(run, receipt['payload']), allow_pickle=False) as saved:
            for model in MODELS:
                arrays[model][:, index] = saved[model]
    for model in MODELS:
        arrays[model].flush()
    arrays.clear()
    write_json(assembly / 'calendar_and_cells.json', {
        'cells_lon_lat_origins': cells,
        'days': [{'start': a.isoformat(), 'end_exclusive': b.isoformat(),
                  'exposure_seconds': (b-a).total_seconds(),
                  'conditioning_history_end_exclusive': a.isoformat(),
                  'parent_count': int(np.searchsorted(history[:, 0], starts[i], side='left'))}
                 for i, (a, b) in enumerate(zip(all_starts, all_ends))]})
    forecasts = {m: artifact(assembly / (m + '.npy'), run) for m in MODELS}
    for key, row in sources.items():
        require(sha(row['path']) == row['sha256'], 'Pinned source changed during generation: ' + key)
    write_json(run / 'FORECASTS_COMPLETE.json', {
        'status': 'BOTH_MODELS_GENERATED_QA_PASS_NOT_SCORED', 'utc': now(),
        'definition_sha256': definition_sha, 'definition': definition,
        'forecasts': forecasts, 'calendar_cells': artifact(assembly / 'calendar_and_cells.json', run),
        'cell_receipts': cell_receipts, 'union_mass_absolute_delta_max': union_delta,
        'gaussian_union_mass_absolute_delta_max': gaussian_union_delta,
        'gaussian_union_evidence': artifact(gaussian_union_path, run),
        'geographic_domain_qa': geo_domain, 'geographic_domain_evidence': artifact(geo_path, run),
        'generation_RNG_calls': 0, 'within_day_descendants': False,
        'target_observations_opened_for_scoring': False, 'operational_forecasts_issued': 0})


def target_counts(np, lock, calendar_cells):
    """Use the 2122 already admitted IDs. Do not rerun event selection/counting."""
    sources = lock['sources']
    audit = read(sources['count_ids']['path'])
    count_receipt = read(sources['count_receipt']['path'])
    require(len(audit) == len({r['id'] for r in audit}) == N_EXPECTED, 'Admitted ID set changed')
    origins = calendar_cells['cells_lon_lat_origins']
    positions = {(round((lo + 180) * 10), round((la + 90) * 10)): i
                 for i, (lo, la) in enumerate(origins)}
    counts = np.zeros((NDAYS, NCELLS), dtype=np.int64)
    unix = dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)
    start_ms = int((START - unix).total_seconds()) * 1000
    delta = END - unix
    end_us = (delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds
    path = Path(sources['catalog']['path'])
    db = sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True)
    yearly = {}
    try:
        db.execute('PRAGMA query_only=ON')
        db.execute('PRAGMA cache_size=-2048')
        for accepted in audit:
            found = db.execute('SELECT time_ms,lon,lat,mag,mag_type,depth FROM events WHERE id=?',
                               (accepted['id'],)).fetchall()
            require(len(found) == 1, 'Missing or repeated admitted event ID')
            time_ms, lon, lat, magnitude, mag_type, depth = found[0]
            require(time_ms == accepted['time_ms'] and magnitude == accepted['magnitude'] and
                    mag_type == accepted['mag_type'] and 0 <= depth <= 70,
                    'Previously admitted target changed')
            require(start_ms <= time_ms and time_ms * 1000 < end_us, 'Target outside exact window')
            cell = (math.floor((lon + 180) * 10 + 1e-8), math.floor((lat + 90) * 10 + 1e-8))
            require(cell in positions, 'Admitted event outside R4 mask')
            day = (time_ms - start_ms) // 86400000
            counts[day, positions[cell]] += 1
            year = str(dt.datetime.fromtimestamp(time_ms / 1000, dt.timezone.utc).year)
            yearly[year] = yearly.get(year, 0) + 1
    finally:
        db.close()
    require(int(counts.sum()) == N_EXPECTED and yearly == count_receipt['by_year_UTC'],
            'Counts do not reproduce the already admitted IDs')
    return counts


def write_csv(path, rows):
    require(bool(rows), 'Empty CSV')
    with Path(path).open('x', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def finite_json(value):
    """Preserve undefined/infinite diagnostics explicitly; never replace by zero."""
    if isinstance(value, float) and not math.isfinite(value):
        return 'NaN' if math.isnan(value) else ('+Infinity' if value > 0 else '-Infinity')
    if isinstance(value, dict):
        return {k: finite_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [finite_json(v) for v in value]
    return value


def ns_descriptive(np, forecast, counts, model, lock):
    from scipy.stats import poisson
    total = float(np.sum(forecast, dtype=np.float64))
    require(math.isfinite(total) and total > 0, 'Invalid N_fore')
    upper = float(poisson.sf(N_EXPECTED - 1, total))
    lower = float(poisson.cdf(N_EXPECTED, total))
    label = 'R5_Q2_STEST|' + model
    seed = int.from_bytes(hashlib.sha256(label.encode('utf-8')).digest()[:8], 'big')
    rng = np.random.default_rng(seed)
    simulated = np.zeros(1000)
    observed = 0.0
    for day in range(NDAYS):
        guard()
        nday = int(counts[day].sum())
        if not nday:
            continue
        rates = np.asarray(forecast[day])
        denominator = float(rates.sum())
        require(denominator > 0 and math.isfinite(denominator), 'S normalization undefined')
        probabilities = rates / denominator
        observed_cells = np.flatnonzero(counts[day])
        if np.any(probabilities[observed_cells] == 0):
            observed = -math.inf
        elif math.isfinite(observed):
            observed += float(counts[day, observed_cells] @ np.log(probabilities[observed_cells]))
        # Fixed traversal: day-major, then 1000 catalogues, then the n_d events.
        # ETAS and ETAS_X1 have separate registered label-derived RNG streams.
        draws = rng.choice(NCELLS, size=(1000, nday), replace=True, p=probabilities)
        with np.errstate(divide='ignore'):
            simulated += np.log(probabilities[draws]).sum(axis=1)
    require(np.all(np.isfinite(simulated)), 'Nonfinite S null simulation retained as failure')
    quantiles = np.quantile(simulated, [.025, .5, .975])
    zeta = float(np.mean(simulated <= observed))
    row = {'model': model, 'N_fore': total, 'N_obs': N_EXPECTED,
           'delta1_P_X_ge_Nobs': upper, 'delta2_P_X_le_Nobs': lower,
           'N_label_descriptive': 'SUBPRONOSTICA' if upper < .025 else
                                  ('SOBREPRONOSTICA' if lower < .025 else 'NO_RECHAZO_DESCRIPTIVO'),
           'S_obs': observed, 'S_sim_q025': float(quantiles[0]),
           'S_sim_q50': float(quantiles[1]), 'S_sim_q975': float(quantiles[2]),
           'zeta_fraction_Ssim_le_Sobs': zeta,
           'S_label_descriptive': 'INCONSISTENCIA_ESPACIAL' if zeta < .025 else 'NO_RECHAZO_DESCRIPTIVO',
           'S_simulation_count': 1000, 'S_seed': str(seed), 'S_seed_label': label,
           'numpy_version': importlib.metadata.version('numpy'),
           'scipy_version': importlib.metadata.version('scipy'),
           'N_S_clarification_sha256': lock['sources']['ns_clarification']['sha256'],
           'decision_affected_by_N_or_S': False}
    return row, simulated


def score(engine, lock, definition, run):
    np = engine.np
    from scipy.special import xlogy, gammaln
    complete_path = run / 'FORECASTS_COMPLETE.json'
    complete = read(complete_path)
    require(complete['status'] == 'BOTH_MODELS_GENERATED_QA_PASS_NOT_SCORED' and
            complete['definition'] == definition and set(complete['forecasts']) == set(MODELS),
            'Both frozen forecast products must be closed and verified before scoring')
    require(not (run / 'R6_SCORE_COMPLETE.json').exists(), 'R6 score already completed; do not repeat')
    # Rehash BOTH model arrays before opening the admitted target IDs/database.
    forecasts = {model: np.load(checked_artifact(run, complete['forecasts'][model]),
                               mmap_mode='r', allow_pickle=False) for model in MODELS}
    for model in MODELS:
        require(forecasts[model].shape == (NDAYS, NCELLS) and
                np.all(np.isfinite(forecasts[model])) and np.all(forecasts[model] >= 0),
                'Invalid forecast matrix: ' + model)
    calendar_cells = read(checked_artifact(run, complete['calendar_cells']))
    starts, ends = calendar()
    require(len(calendar_cells['days']) == NDAYS and all(
        r['start'] == a.isoformat() and r['end_exclusive'] == b.isoformat() and
        r['conditioning_history_end_exclusive'] == a.isoformat()
        for r, a, b in zip(calendar_cells['days'], starts, ends)), 'Calendar changed')
    guard(100 * 2**20)
    folder = run / ('score_' + uuid.uuid4().hex)
    folder.mkdir()
    write_json(folder / 'SCORING_OPENED.json', {'utc': now(), 'definition': definition,
                    'forecasts_complete_sha256': sha(complete_path),
                    'both_forecast_sha256_before_target_access':
                    {m: complete['forecasts'][m]['sha256'] for m in MODELS}})
    counts = target_counts(np, lock, calendar_cells)
    with (folder / 'observed_counts_from_admitted_IDs.npy').open('xb') as stream:
        np.save(stream, counts, allow_pickle=False)
    nd = counts.sum(axis=1)
    daily = []
    differences = []
    for day in range(NDAYS):
        guard()
        obs = counts[day]
        e = np.asarray(forecasts['ETAS'][day])
        x = np.asarray(forecasts['ETAS_X1'][day])
        common = gammaln(obs + 1)
        ll_e = float(np.sum(xlogy(obs, e) - e - common))
        ll_x = float(np.sum(xlogy(obs, x) - x - common))
        # Includes all zero-count cells, all daily integrals, and the fractional day.
        difference = ll_x - ll_e
        differences.append(difference)
        daily.append({'day_start_UTC': starts[day].isoformat(),
                      'day_end_exclusive_UTC': ends[day].isoformat(),
                      'exposure_seconds': (ends[day] - starts[day]).total_seconds(),
                      'conditioning_history_end_exclusive_UTC': starts[day].isoformat(),
                      'N': int(nd[day]), 'LL_ETAS_all_4296_cells': ll_e,
                      'LL_X1_all_4296_cells': ll_x, 'LL_difference': difference,
                      'N_fore_ETAS': float(e.sum()), 'N_fore_ETAS_X1': float(x.sum()),
                      'R6_ETAS_fit_sha256': definition['R6_fit_hashes']['ETAS'],
                      'X1_fit_sha256': definition['R6_fit_hashes']['ETAS_X1'],
                      'input_snapshot_sha256': lock['sources']['prepared_history']['sha256']})
    write_csv(folder / 'R6_DIARIO.csv', daily)
    d = np.asarray(differences)
    # N/S evidence is retained even when a zero observed probability yields -infinity.
    descriptions = []
    for model in MODELS:
        row, simulated = ns_descriptive(np, forecasts[model], counts, model, lock)
        descriptions.append(row)
        with (folder / ('S_null_' + model + '.npy')).open('xb') as stream:
            np.save(stream, simulated, allow_pickle=False)
    write_csv(folder / 'R6_DESCRIPTIVOS_N_S.csv', descriptions)
    write_json(folder / 'R6_DESCRIPTIVOS_N_S.json', finite_json(descriptions))
    require(np.all(np.isfinite(d)), 'Nonfinite IG components; no epsilon, CI or decision rescue')
    ig = float(d.sum() / N_EXPECTED)
    intervals_by_block = {}
    for block in (7, 14):
        guard()
        percentile, studentized = intervals(d[None, :], nd[None, :], block, 9999)
        values = {'percentile_original_95': percentile[0].tolist(),
                  'bootstrap_t_95': studentized[0].tolist(), 'resamples': 9999,
                  'seed': 20261020, 'days_including_final_fraction': NDAYS}
        write_json(folder / ('R6_INTERVALS_L%d.json' % block), finite_json(values))
        require(np.all(np.isfinite(percentile)) and np.all(np.isfinite(studentized)),
                'Undefined registered interval; retain failure without dropping resamples')
        intervals_by_block[str(block)] = values
    annual = []
    for year in (2024, 2025, 2026):
        indices = np.array([a.year == year for a in starts])
        number = int(nd[indices].sum())
        annual.append({'year_UTC': year, 'N': number, 'LL_difference': float(d[indices].sum()),
                       'IG_descriptive': float(d[indices].sum() / number) if number else 'UNDEFINED_N0',
                       'primary_decision_uses_this_subperiod': False})
    write_csv(folder / 'R6_IG_POR_ANO.csv', annual)
    passed = all(intervals_by_block[str(b)]['bootstrap_t_95'][1] < .05 for b in (7, 14))
    for model in MODELS:
        checked_artifact(run, complete['forecasts'][model])
    require(sha(complete_path) == read(folder / 'SCORING_OPENED.json')['forecasts_complete_sha256'],
            'Generation manifest changed during scoring')
    # Q3 PASS was checked before generation and again before scoring. N/S and Q1
    # do not participate in this expression, nor does the old percentile interval.
    result = {'status': 'R6_COMPLETE', 'utc': now(),
              'decision': 'NEGATIVO ROBUSTO' if passed else 'NEGATIVO NO ROBUSTO',
              'N': N_EXPECTED, 'days': NDAYS, 'cells': NCELLS, 'IG_nats_per_event': ig,
              'intervals': intervals_by_block,
              'Q3_receipt_sha256': lock['sources']['q3_receipt']['sha256'],
              'Q3_scope': 'Synthetic fixed-window calibration, not adjusted ETAS-X1 power',
              'Q1_used': 'TWO_FIXED_INITIAL_VECTORS_ONLY', 'Q1_completion_required_for_Q2': False,
              'robustness_after_observed_Q2': True,
              'definition': definition, 'generation_manifest_sha256': sha(complete_path),
              'source_hashes': {k: v['sha256'] for k, v in lock['sources'].items()},
              'limitations': [
                  'Analytic frozen-history base plus 500-trajectory mean of generations >=1; X1 uses no simulated events in its z history.',
                  'Retrospective out-of-sample evidence; X1 form may have been designed using the full catalogue.',
                  'Parameters and KDE frozen to historical epoch; observational differences between epochs remain.',
                  'Poisson scoring includes zeros and integral; N-test is descriptive under potentially overdispersed counts.',
                  'Robustness analysis after observing Q2; neither independent nor prospective validation.'],
              'R4': 'HOLD_NO_SEAL_NO_FORECAST', 'operational_forecasts_issued': 0,
              'seals_publications_emails': 0}
    write_json(folder / 'R6_DECISION.json', result)
    report = ('# R6 — robustez posterior a Q2\n\n'
              + 'Decisión: **' + result['decision'] + '**. IG=' + str(ig) + ' nats/evento.\n\n'
              + 'L7: ' + str(intervals_by_block['7']['bootstrap_t_95']) + '\n\n'
              + 'L14: ' + str(intervals_by_block['14']['bootstrap_t_95']) + '\n\n'
              + 'NEGATIVO ROBUSTO exige ambos límites superiores <0.05. N/S e IG anual son descriptivos. '
              + 'Base analítica positiva más descendientes intradiarios (500 trayectorias); error Monte Carlo. '
              + 'Periodo ya examinado en Q2: robustez, no nueva validación ciega o prospectiva. '
              + 'Cotas activas se conservan; R4 HOLD_NO_SEAL_NO_FORECAST. Sin emisión operativa.\n')
    with (folder / 'INFORME_R6_ES.md').open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(report)
    outputs = [artifact(p, run) for p in sorted(folder.iterdir()) if p.is_file()]
    write_json(run / 'R6_SCORE_COMPLETE.json', {'utc': now(), 'status': 'R6_COMPLETE',
                'decision': result['decision'], 'artifacts': outputs,
                'forecasts_complete_sha256': sha(complete_path),
                'Q1_used_only_for_two_preregistered_initial_vectors': True, 'R4': 'HOLD_NO_SEAL_NO_FORECAST'})


# Verbatim registered R4 bootstrap-t and percentile implementation.
def intervals(d,n,length,draws):
    """Same resampling indices for percentile and the single proposed repair."""
    import numpy as np
    size=d.shape[1];groups=d.shape[0];k=math.ceil(size/length)
    if k<2:raise ValueError('Too few calendar blocks')
    starts=np.random.default_rng(20261020).integers(0,size-length+1,size=(draws,k))
    lengths=np.full(k,length);lengths[-1]=size-(k-1)*length
    D=np.c_[np.zeros(groups),np.cumsum(d,axis=1)];N=np.c_[np.zeros(groups),np.cumsum(n,axis=1)]
    point=d.sum(axis=1)/n.sum(axis=1)
    # Overlapping residual block sums define the registered original SE.
    od=D[:,length:]-D[:,:-length];on=N[:,length:]-N[:,:-length]
    original_se=np.sqrt((size/length)*np.var(od-point[:,None]*on,axis=1,ddof=1)*size/(size-length+1))/n.sum(axis=1)
    per=[];stud=[];undefined_p=[];undefined_t=[]
    # Keep the temporary cube below ~10 MiB even for short 7-day blocks.
    for first in range(groups):
        bd=D[first,starts+lengths]-D[first,starts]
        bn=N[first,starts+lengths]-N[first,starts]
        totaln=bn.sum(axis=1);g=np.divide(bd.sum(axis=1),totaln,out=np.full(draws,np.nan),where=totaln>0)
        star_se=np.sqrt(size*np.sum((bd-g[:,None]*bn)**2/lengths,axis=1)/(k-1))/totaln
        statistic=np.divide(g-point[first],star_se,out=np.full(draws,np.nan),where=star_se>0)
        badp=not np.all(np.isfinite(g));badt=not np.all(np.isfinite(statistic)) or not original_se[first]>0
        per.append(np.quantile(g,[.025,.975]) if not badp else [np.nan,np.nan])
        if badt:stud.append([np.nan,np.nan])
        else:
            qt=np.quantile(statistic,[.025,.975]);stud.append([point[first]-qt[1]*original_se[first],point[first]-qt[0]*original_se[first]])
        undefined_p.append(badp);undefined_t.append(badt)
    return np.asarray(per),np.asarray(stud)



# R6 additions below are never executed by importing this file.
# DRAFT FOR EXACT-BYTE REVIEW: no review receipt has been issued.
import time
from dataclasses import asdict

PREREG_SHA = '666cb2d5b78aa87a34491dd4510d5dc8e944fbdae3ac62b9de0594872dc11f9c'
R6_LOCK = HERE / 'R6_SOURCE_LOCK.json'
TRAJECTORIES = 500


def write_or_match(path, value):
    if path.exists():
        require(read(path)==value,'Existing checkpoint differs: '+str(path))
    else:
        write_json(path,value)


def verify_r6(review_path, review_sha, stage, run):
    require(sha(LOCK_PATH) == LOCK_SHA, 'R5 source lock changed')
    lock = read(LOCK_PATH)
    registry = read(REGISTRATION)
    require(registry['script_sha256'] == sha(__file__), 'Unregistered R6 bytes')
    require(sha(R6_LOCK) == registry['R6_source_lock_sha256'], 'R6 lock changed')
    extra = read(R6_LOCK)
    for row in list(lock['sources'].values()) + extra['sources']:
        require(Path(row['path']).stat().st_size == row['bytes'] and
                sha(row['path']) == row['sha256'], 'Pinned input changed: ' + row['path'])
    require(sha(HERE / 'R6_PREREGISTRO_ES.md') == PREREG_SHA, 'Preregistration changed')
    for name, expected in [('r6_cascade_forecast.py', sha(__file__)),
                           ('R6_SOURCE_LOCK.json', sha(R6_LOCK))]:
        blob = subprocess.check_output(['git', '-C', str(ROOT), 'show',
                          registry['commit'] + ':amendment_R6/' + name])
        require(hashlib.sha256(blob).hexdigest() == expected, 'Registered blob differs')
    require(sha(review_path) == review_sha, 'Review hash differs')
    approval = read(review_path)
    require(approval['adenda_sha256']==extra['adenda_sha256'],'Adenda review pending')
    require(approval['status'] == 'APPROVED_FOR_R6_FIT_GENERATION_AND_SCORING' and
            approval['reviewer'] == 'Claude' and approval['script_sha256'] == sha(__file__) and
            approval['R6_source_lock_sha256'] == sha(R6_LOCK) and
            approval['preregistration_sha256'] == PREREG_SHA,
            'Exact-byte R6 review pending')
    require(approval['z_definition']=='FROZEN_PREFIX_TIME_AGING_NO_SIMULATED_EVENTS',
            'Pending explicit clarification: Q2 prefix-frozen z(t) versus midnight-constant z')
    require(approval['simulation_semantics'] ==
            'R4_DISK_ANALYTIC_PLUS_GENERATION_GE1_FROZEN_HISTORY_X1', 'Simulation semantics unresolved')
    require(approval['zero_mean_rule'] == 'POSITIVE_ANALYTIC_BASE_NO_PSEUDOCOUNT',
            'Zero-mean rule unresolved')
    warm = extra['Q1_warm_starts']
    require(len(warm)==2 and approval['Q1_warm_start_hashes']==[r['sha256'] for r in warm], 'Warm-start lineage pending')
    require(dt.datetime.fromisoformat(approval['recorded_utc']) <= dt.datetime.now(dt.timezone.utc),
            'Future review')
    require(read(lock['sources']['q3_receipt']['path'])['admitted_Q3'] ==
            'PASS_SYNTHETIC_FIXED_WINDOW_CALIBRATION', 'Q3 missing')
    for package, version in lock['environment_pins'].items():
        require(importlib.metadata.version(package) == version, 'Wrong numerical pin: ' + package)
    definition = {'script_sha256': sha(__file__), 'source_lock_sha256': sha(R6_LOCK),
        'review_receipt_sha256': review_sha, 'preregistration_sha256': PREREG_SHA,
        'start_inclusive': START.isoformat(), 'end_exclusive': END.isoformat(),
        'generation_method': 'R4_MONTE_CARLO_INTRADAY_CASCADES', 'trajectories_per_day': 500,
        'adenda_sha256':extra['adenda_sha256'],
        'simulation_semantics': approval['simulation_semantics'],
        'zero_mean_rule': approval['zero_mean_rule'], 'z_definition':approval['z_definition'], 'Q1_warm_starts': warm,
        'day_seed': "first8 big-endian SHA256('R6|'+UTC YYYY-MM-DD)",
        'replicate_seed': 'SeedSequence(day_seed).spawn(500); same replicate seeds both models',
        'Q1_results_used': 'TWO_FIXED_INITIAL_VECTORS_ONLY', 'R4': 'HOLD_NO_SEAL_NO_FORECAST',
        'analysis': 'POST_Q2_ROBUSTNESS_NOT_NEW_UNSEEN_VALIDATION'}
    require(approval['day_seed_rule'] == definition['day_seed'] and
            approval['replicate_seed_rule'] == definition['replicate_seed'], 'Seed convention pending')
    if stage != 'fit':
        closed = read(run / 'FIT_COMPLETE.json')
        require(closed['status'] == 'R6_ETAS_X1_FITS_QA_PASS' and
                closed['definition'] == definition, 'Matching R6 fits not closed')
        fits = {model: read(checked_artifact(run, closed['fits'][model])) for model in MODELS}
        definition['model_parameters'] = {model: fits[model]['parameters'] for model in MODELS}
        definition['R6_fit_hashes'] = {m: closed['fits'][m]['sha256'] for m in MODELS}
        definition['fit_complete_sha256'] = sha(run / 'FIT_COMPLETE.json')
    return lock, definition


def r6_runtime(run, stage):
    engine = runtime(run, 'score' if stage == 'score' else 'generate')
    if stage == 'score':
        return engine
    from point_models import ETASParameters
    class R6Parameters(ETASParameters):
        def check(self):
            vals = asdict(self)
            require(all(math.isfinite(v) for v in vals.values()), 'Nonfinite R6 parameters')
            require(0 <= self.m0 < 8 and 1e-6 <= self.mu <= 1e4 and .01 <= self.n <= .99
                and 0 <= self.alpha_ratio <= .95 and .5 <= self.b <= 2
                and .001 <= self.c <= 1 and 1.01 <= self.p <= 2.5 and 1.01 <= self.q <= 3
                and .1 <= self.d0 <= 50 and 0 <= self.eta <= math.log(10)/2
                and -1 <= self.gamma <= 1, 'Outside preregistered R6 bounds')
            return self
    engine.Parameters = R6Parameters
    engine.simulate = simulate_r6
    engine.prepare_history_offspring = prepare_history_offspring
    sys.path.insert(0, str(ROOT / 'amendment_P1A1_R4'))
    from r4_numba_warmstart_profile import install_backend
    engine.backend = install_backend(ROOT.parent / 'bootstrap_nube_R4/aceleracion_adoptada_R4_v1', 3)
    return engine


def transformed(parameters):
    return [math.log(parameters['mu']), parameters['n'], parameters['alpha_ratio'],
        parameters['b'], math.log(parameters['c']), parameters['p'], parameters['q'],
        math.log(parameters['d0']), parameters['eta']]


def unpack_r6(engine, vector):
    x = vector
    # Dictamen 4: L-BFGS-B keeps x inside the log-bounds, but exp() can leave a
    # bound by one ulp (exp(log(1e4)) = 1e4 + 1e-11). Only that rounding is
    # clamped; any larger excursion still fails.
    def back(value, lower, upper):
        raw = math.exp(value)
        kept = min(max(raw, lower), upper)
        require(abs(kept - raw) <= 1e-12 * abs(raw), 'Log-parameter outside bounds beyond rounding')
        return kept
    return engine.Parameters(mu=back(x[0], 1e-6, 1e4), n=x[1], alpha_ratio=x[2], b=x[3],
        c=back(x[4], .001, 1), p=x[5], q=x[6], d0=back(x[7], .1, 50), eta=x[8], gamma=0, m0=2.5).check()


def fit_r6(engine, lock, definition, run, resume):
    from scipy.optimize import minimize
    from scipy.stats import qmc
    from point_models import FIT_BOUNDS
    np = engine.np
    folder = run / 'fit'
    folder.mkdir(exist_ok=resume)
    context = run / 'FIT_CONTEXT.json'
    if context.exists():
        require(resume and read(context)['definition'] == definition, 'Fit context mismatch')
    else:
        write_json(context, {'definition': definition, 'utc': now()})
    with np.load(lock['sources']['prepared_history']['path'], allow_pickle=False) as data:
        history = data['history'].copy()
        flags = data['target_flags'].copy()
    t0 = (dt.datetime(2016, 1, 1, tzinfo=dt.timezone.utc) - EPOCH).days
    t1 = (START - EPOCH).days
    before = history[:, 0] < t1
    support = read(lock['sources']['support']['path'])['cells']
    domain = engine.Polygon.from_geographic_cells(support)
    radius = read(lock['sources']['prepared_receipt']['path'])['parent_radius_km']
    likelihood = engine.Masked(history[before], flags[before], domain, radius, t0, t1, order=16)
    bounds = list(FIT_BOUNDS)
    bounds[1] = (.01, .99)
    bounds[7] = (math.log(.1), math.log(50))
    reference = read(lock['sources']['capsule']['path'])['parameters']
    warm = definition['Q1_warm_starts']
    design = qmc.Sobol(9, scramble=True, seed=20261020).random_base2(3)
    starts = [('reference', transformed(reference))]
    for row in warm:
        point=read(row['path'])
        require(point['status']=='QA_PASS' and len(point['best_x'])==9,'Warm point invalid')
        starts.append((row['label'],point['best_x']))
    for index in (1, 4, 7):
        starts.append(('sobol_%d' % index, [a + (b-a)*u for (a,b),u in zip(bounds, design[index])]))
    results = []
    for label, initial in starts:
        guard()
        require(all(a <= v <= b for v, (a,b) in zip(initial,bounds)), 'Start outside R6 bounds')
        checkpoint = folder / (label + '.json')
        if checkpoint.exists():
            require(resume, 'Duplicate fit checkpoint')
            row = read(checkpoint)
            require(row['definition'] == definition and row['initial_x'] == initial, 'Changed start')
            require(row['success'], 'Failed start cannot be resumed')
            results.append(row)
            continue
        calls = 0
        started = time.perf_counter()
        cpu = time.process_time()
        with (folder / (label + '_progress_' + uuid.uuid4().hex + '.jsonl')).open('x', encoding='utf8') as log:
            def objective(x):
                nonlocal calls
                guard()
                calls += 1
                try:
                    candidate = unpack_r6(engine, x)
                except Exception:
                    log.write(json.dumps({'utc': now(), 'call': calls, 'rejected_x': x.tolist()})+'\n')
                    log.flush()
                    raise
                value, gradient = likelihood.value_gradient(candidate)
                require(math.isfinite(value) and np.all(np.isfinite(gradient)), 'Nonfinite fit objective')
                log.write(json.dumps({'utc': now(), 'call': calls, 'nll': value, 'x': x.tolist()})+'\n')
                log.flush()
                return value, gradient
            opt = minimize(objective, initial, jac=True, method='L-BFGS-B', bounds=bounds,
                options={'maxiter':1000, 'maxfun':20000, 'ftol':1e-10, 'gtol':1e-5})
        row = {'definition': definition, 'start': label, 'initial_x': initial,
            'success': bool(opt.success), 'message': str(opt.message), 'nll': float(opt.fun),
            'x': opt.x.tolist(), 'calls': calls, 'iterations': int(opt.nit),
            'active_bounds': [i for i,(v,(a,b)) in enumerate(zip(opt.x,bounds)) if min(v-a,b-v)<1e-5],
            'wall_seconds': time.perf_counter()-started, 'CPU_seconds': time.process_time()-cpu}
        write_json(checkpoint, row)
        results.append(row)
        require(row['success'], 'Numerical fit failure retained; consult before proceeding')
    best = min(results, key=lambda r:r['nll'])
    p = unpack_r6(engine, best['x'])
    original = float(likelihood.value_gradient(p)[0])
    checks = []
    for order in (32,64):
        guard()
        likelihood.order = order
        v = float(likelihood.value_gradient(p)[0])
        checks.append({'order':order, 'nll':v, 'delta_per_target':abs(v-original)/len(likelihood.ev)})
    guard()
    refined = engine.Polygon.from_geographic_cells(support, subdivide=2)
    ref = engine.Masked(history[before],flags[before],refined,radius,t0,t1,order=64)
    v = float(ref.value_gradient(p)[0])
    checks.append({'order':64,'subdivision':2,'nll':v,'delta_per_target':abs(v-original)/len(likelihood.ev)})
    write_or_match(folder/'ETAS_QA.json', {'checks':checks})
    require(all(math.isfinite(r['nll']) and r['delta_per_target']<=1e-3 for r in checks), 'R6 ETAS refined QA failed')
    del ref
    etas = {'parameters':asdict(p), 'selected_start':best['start'], 'nll':best['nll'],
            'starts':results, 'bounds':bounds, 'QA':checks, 'active_bounds':best['active_bounds']}
    etas_path = folder/'ETAS_FIT_RESULT.json'
    if not etas_path.exists():
        write_json(etas_path, etas)
    else:
        require(read(etas_path) == etas, 'Existing ETAS fit differs')
    guard()
    m2 = likelihood.covariate_measure(cell_order=2)
    guard()
    m4 = likelihood.covariate_measure(cell_order=4)
    comparisons = [{'gamma':g,'order2':float(m2[1]@np.exp(g*m2[0])),
                    'order4':float(m4[1]@np.exp(g*m4[0]))} for g in (-1,-.5,0,.5,1)]
    write_or_match(folder/'X1_QA.json', {'comparisons':comparisons,'principal_cell_order':4})
    require(all(abs(r['order2']-r['order4'])<=1e-5+.005*abs(r['order4']) for r in comparisons), 'R6 X1 integral QA failed')
    x1_path = folder/'X1_FIT_RESULT.json'
    if x1_path.exists():
        require(resume and read(x1_path)['base_point_sha256']==sha(etas_path),'Gamma checkpoint context differs')
    else:
        guard()
        x1, runs = likelihood.fit_gamma(p,m4)
        require(all(r['success'] for r in runs), 'R6 gamma numerical failure retained')
        write_json(x1_path, {'parameters':asdict(x1),'starts':runs,'cell_order':4,
            'base_point_sha256':sha(etas_path), 'nine_ETAS_fixed':True,
            'active_gamma_bound': min(x1.gamma+1,1-x1.gamma)<1e-5})
    write_json(run/'FIT_COMPLETE.json', {'status':'R6_ETAS_X1_FITS_QA_PASS',
        'definition':definition, 'fits':{'ETAS':artifact(etas_path,run),
        'ETAS_X1':artifact(x1_path,run)}, 'utc':now(), 'R4':'HOLD_NO_SEAL_NO_FORECAST'})


def generate_r6(engine, lock, definition, run, resume):
    global GAMMA
    np = engine.np
    GAMMA = definition['model_parameters']['ETAS_X1']['gamma']
    require({k:v for k,v in definition['model_parameters']['ETAS'].items() if k!='gamma'} ==
            {k:v for k,v in definition['model_parameters']['ETAS_X1'].items() if k!='gamma'}, 'X1 changed ETAS')
    controls = run/'integration_controls'
    controls.mkdir(exist_ok=True)
    # Same analytic R4/Q2 controls, using the NEW R6 fits, before any trajectories.
    # Audit intensities are kept separate and never used as cascade forecast means.
    if not (controls/'FORECASTS_COMPLETE.json').exists():
        control_wall=time.perf_counter();control_cpu=time.process_time()
        generate_controls(engine,lock,definition,controls,resume)
        write_json(run/'INTEGRATION_CONTROLS_TIMING.json',{'wall_seconds':time.perf_counter()-control_wall,
            'CPU_seconds':time.process_time()-control_cpu,'current_attempt_only':True})
    control = read(controls/'FORECASTS_COMPLETE.json')
    require(control['definition']==definition, 'Control context changed')
    for model in MODELS:
        checked_artifact(controls,control['forecasts'][model])
    with np.load(lock['sources']['prepared_history']['path'],allow_pickle=False) as data:
        h = data['history'].copy()
        flags = data['target_flags'].copy()
    starts,ends = calendar()
    t0=(dt.datetime(2016,1,1,tzinfo=dt.timezone.utc)-EPOCH).days
    stop=(START-EPOCH).days
    training=h[flags & (h[:,0]>=t0) & (h[:,0]<stop)]
    require(len(training)==9025,'Training changed')
    radius=read(lock['sources']['prepared_receipt']['path'])['parent_radius_km']
    background=engine.Background(training[:,1:3],radius)
    domain=engine.Polygon.from_geographic_cells(read(lock['sources']['support']['path'])['cells'])
    cells=sorted(read(lock['sources']['support']['path'])['cells'])
    lookup={(round((lo+180)*10),round((la+90)*10)):i for i,(lo,la) in enumerate(cells)}
    polygons=[engine.Polygon.from_geographic_cells([origin]) for origin in cells]
    require(len(lookup)==NCELLS,'Cell keys conflict')
    inverse=domain.transformer
    daydir=run/'days'
    daydir.mkdir(exist_ok=True)
    definition_sha=hashlib.sha256(json.dumps(definition,sort_keys=True).encode()).hexdigest()
    analytic={m:np.load(checked_artifact(controls,control['forecasts'][m]),mmap_mode='r',allow_pickle=False) for m in MODELS}
    receipts=[]
    for day,(a,b) in enumerate(zip(starts,ends)):
        guard()
        receipt_path=daydir/('day_%04d.json'%day)
        if receipt_path.exists():
            require(resume,'Day checkpoint exists without resource resume')
            receipt=read(receipt_path)
            require(receipt['day']==day and receipt['start']==a.isoformat() and receipt['end_exclusive']==b.isoformat(),'Saved day/calendar mismatch')
            require(receipt['definition_sha256']==definition_sha and receipt['status']=='R6_DAY_COMPLETE', 'Day context differs')
            checked_artifact(run,receipt['payload'])
            receipts.append(artifact(receipt_path,run))
            if day==0 or day%25==0:record_cost_projection(run,receipts)
            continue
        started=time.perf_counter()
        cpu=time.process_time()
        cutoff=(a-EPOCH).total_seconds()/86400
        end=(b-EPOCH).total_seconds()/86400
        prior=h[h[:,0]<cutoff]
        history_offspring=engine.prepare_history_offspring(engine.Parameters(**definition['model_parameters']['ETAS']),prior,cutoff,end)
        day_seed=int.from_bytes(hashlib.sha256(('R6|'+a.date().isoformat()).encode()).digest()[:8],'big')
        seeds=[int(s.generate_state(1,dtype=np.uint64)[0]) for s in np.random.SeedSequence(day_seed).spawn(TRAJECTORIES)]
        sums={m:np.zeros(NCELLS,dtype=np.int64) for m in MODELS}
        totals={m:0 for m in MODELS}
        for j,seed in enumerate(seeds):
            for model in MODELS:
                guard()
                p=engine.Parameters(**definition['model_parameters'][model]).check()
                events=engine.simulate(p,prior,background,cutoff,end,seed,max_events=200000,history_offspring=history_offspring)
                require(events.ndim==2 and events.shape[1]==6 and np.all(np.isfinite(events)), 'Invalid trajectory')
                events=events[events[:,5]>=1]
                if len(events):
                    require(np.all((events[:,0]>=cutoff)&(events[:,0]<end)), 'Trajectory escaped time interval')
                    lon,lat=inverse.transform(events[:,1]*1000,events[:,2]*1000,direction='INVERSE')
                    keys=np.c_[np.floor((lon+180)*10+1e-8).astype(int),np.floor((lat+90)*10+1e-8).astype(int)]
                    indices=[]
                    for xy,key in zip(events[:,1:3],keys):
                        hits=[]
                        for dx in (-1,0,1):
                            for dy in (-1,0,1):
                                candidate=lookup.get((int(key[0])+dx,int(key[1])+dy))
                                if candidate is None:continue
                                polygon=polygons[candidate]
                                delta=xy-polygon.starts
                                cross=polygon.v[:,0]*delta[:,1]-polygon.v[:,1]*delta[:,0]
                                if np.all(cross>=0):hits.append(candidate)
                        require(len(hits)<=1,'Simulated point lies on multiple cell boundaries; preserve and consult')
                        if hits:indices.append(hits[0])
                    sums[model]+=np.bincount(indices,minlength=NCELLS)
                    totals[model]+=len(events)
            print(json.dumps({'stage':'R6_DAY_SIMULATING','day':day,'replicate':j+1}),flush=True)
        path=daydir/('day_%04d_'%day+uuid.uuid4().hex+'.npz')
        with path.open('xb') as stream:
            np.savez(stream,**{m:np.asarray(analytic[m][day])+sums[m]/TRAJECTORIES for m in MODELS},
                     **{m+'_descendant_sum':sums[m] for m in MODELS})
        write_json(receipt_path, {'status':'R6_DAY_COMPLETE','definition_sha256':definition_sha,
            'day':day,'start':a.isoformat(),'end_exclusive':b.isoformat(),'day_seed':day_seed,
            'replicate_seeds':seeds,'trajectories_per_model':TRAJECTORIES,'disk_generation_ge1_events':totals,
            'parent_count':len(prior),'payload':artifact(path,run),'wall_seconds':time.perf_counter()-started,
            'CPU_seconds':time.process_time()-cpu,'zero_descendant_cells':{m:int((sums[m]==0).sum()) for m in MODELS}})
        receipts.append(artifact(receipt_path,run))
        if day==0 or day%25==0:record_cost_projection(run,receipts)
    assembly=run/('cascade_assembled_'+uuid.uuid4().hex)
    assembly.mkdir()
    arrays={m:np.lib.format.open_memmap(assembly/(m+'.npy'),mode='w+',dtype='float64',shape=(NDAYS,NCELLS)) for m in MODELS}
    for i,record in enumerate(receipts):
        guard()
        receipt=read(checked_artifact(run,record))
        with np.load(checked_artifact(run,receipt['payload']),allow_pickle=False) as saved:
            for model in MODELS:
                require(saved[model].shape==(NCELLS,) and np.all(np.isfinite(saved[model])) and np.all(saved[model]>0),'Invalid positive analytic + descendant mean')
                arrays[model][i]=saved[model]
                arrays[model].flush()
    arrays.clear()
    calendar_file=assembly/'calendar_and_cells.json'
    write_json(calendar_file,read(checked_artifact(controls,control['calendar_cells'])))
    for row in lock['sources'].values():
        require(sha(row['path'])==row['sha256'],'Input changed during generation')
    write_json(run/'FORECASTS_COMPLETE.json',{'status':'BOTH_MODELS_GENERATED_QA_PASS_NOT_SCORED',
        'definition':definition,'utc':now(),'forecasts':{m:artifact(assembly/(m+'.npy'),run) for m in MODELS},
        'calendar_cells':artifact(calendar_file,run),'day_receipts':receipts,
        'integration_control_manifest':artifact(controls/'FORECASTS_COMPLETE.json',run),
        'within_day_descendants':True,'operational_forecasts_issued':0,
        'target_observations_opened_for_scoring':False})


def main():
    parser=argparse.ArgumentParser(description='R6 review-gated robustness; no default calculation')
    parser.add_argument('--stage',choices=('fit','generate','score'),required=True)
    parser.add_argument('--run-dir',type=Path,required=True)
    parser.add_argument('--review-receipt',type=Path,required=True)
    parser.add_argument('--review-sha256',required=True)
    parser.add_argument('--resume',action='store_true')
    args=parser.parse_args()
    run=args.run_dir.resolve()
    require(run.is_relative_to(CACHE/'R6'),'Only separate R6 cache paths allowed')
    lock,definition=verify_r6(args.review_receipt,args.review_sha256,args.stage,run)
    with single_worker() as process_rows:
        values=guard()
        if values['free_RAM_MiB']<1200:
            print('WARNING_RAM_BELOW_1200_MiB '+json.dumps(values),flush=True)
        if args.resume:
            require(args.stage!='score' and run.exists(),'Resource resume only for fit/generate')
            failures=sorted(run.glob('FAILURE_*.json'))
            require(failures and all(read(p)['failure_kind']=='RESOURCE_HOLD' for p in failures),
                    'Resume requires exclusively preserved resource failures')
        elif args.stage=='fit':
            run.mkdir(parents=True,exist_ok=False)
        else:
            require(run.exists(),'Fit stage required')
        marker={'fit':'FIT_COMPLETE.json','generate':'FORECASTS_COMPLETE.json','score':'R6_SCORE_COMPLETE.json'}[args.stage]
        require(not (run/marker).exists(),'Stage complete; never repeat')
        stamp=uuid.uuid4().hex
        write_json(run/('STAGE_START_'+stamp+'.json'),{'utc':now(),'stage':args.stage,
            'definition':definition,'processes':process_rows,'resources':values})
        wall=time.perf_counter()
        cpu=time.process_time()
        try:
            engine=r6_runtime(run,args.stage)
            if args.stage=='fit':fit_r6(engine,lock,definition,run,args.resume)
            elif args.stage=='generate':generate_r6(engine,lock,definition,run,args.resume)
            else:
                score(engine,lock,definition,run)
                completed=read(run/'R6_SCORE_COMPLETE.json')
                records=completed['artifacts']+[artifact(run/name,run) for name in ('FIT_COMPLETE.json','FORECASTS_COMPLETE.json','R6_SCORE_COMPLETE.json')]
                write_json(run/'R6_DELIVERY_SHA256.json',{'utc':now(),'artifacts':records,'definition':definition})
            write_json(run/('STAGE_COMPLETE_'+stamp+'.json'),{'utc':now(),'stage':args.stage,
                'wall_seconds':time.perf_counter()-wall,'CPU_seconds':time.process_time()-cpu,
                'outputs':artifact(run/marker,run)})
        except Exception as error:
            write_json(run/('FAILURE_'+stamp+'.json'),{'utc':now(),'stage':args.stage,
                'failure_kind':'RESOURCE_HOLD' if 'RESOURCE_HOLD' in str(error) else 'UNRESOLVED',
                'error':repr(error),'traceback':traceback.format_exc(),
                'wall_seconds':time.perf_counter()-wall,'CPU_seconds':time.process_time()-cpu})
            raise


def prepare_history_offspring(p, history, cutoff, end):
    """Once per day, same nine ETAS parameters for both models and all replicas."""
    from point_models import temporal_cdf, ModelFailure
    h = np.asarray(history, float).reshape(-1, 4)
    p.check()
    if not (end > cutoff and np.all(np.isfinite(h)) and
            np.all(h[:, 0] < cutoff) and np.all(h[:, 3] >= p.m0)):
        raise ValueError('Noncausal/invalid history for offspring preparation')
    lo = temporal_cdf(cutoff - h[:, 0], p.c, p.p)
    hi = temporal_cdf(end - h[:, 0], p.c, p.p)
    means = p.kappa * np.exp(p.alpha * (h[:, 3] - p.m0)) * (hi - lo)
    if not (np.all(np.isfinite(means)) and np.all(means >= 0)):
        raise ModelFailure('Nonfinite offspring mean')
    for value in (lo, hi, means):
        value.flags.writeable = False
    return {'lo': lo, 'hi': hi, 'means': means,
            'history_sha256': hashlib.sha256(h.tobytes()).hexdigest(),
            'cutoff': cutoff, 'end': end,
            'nine_parameters': {k:v for k,v in asdict(p).items() if k != 'gamma'}}


def simulate_r6(p,history,bg,cutoff,end,seed,max_events=200000,history_offspring=None):
    """R4 branching law; vector generation-0 counts, frozen-prefix aging z(t).

    Only generation >=1 enters the additive intraday descendant forecast.
    Gen0 immigrants and direct children of the past seed all later generations.
    """
    import heapq
    from point_models import temporal_cdf,inverse_temporal,covariate,ModelFailure
    p.check();h=np.asarray(history,float).reshape(-1,4)
    if np.any(h[:,0]>=cutoff) or end<=cutoff:raise ValueError('Noncausal history/interval')
    if not np.all(np.isfinite(h)) or np.any(h[:,3]<p.m0):raise ValueError('Invalid ETAS simulation history support')
    rng=np.random.default_rng(seed);heap=[];serial=0;accepted=[];generated=0
    def push(t,xy,mag,kind,generation):
        nonlocal serial,generated
        generated+=1
        if generated>max_events:raise ModelFailure('Trajectory budget exceeded; discard whole trajectory')
        heapq.heappush(heap,(float(t),serial,float(xy[0]),float(xy[1]),float(mag),kind,generation));serial+=1
    def sample_children(event,generation,lo,hi,count):
        tj,xj,yj,mj=event[:4]
        for _ in range(count):
            time=tj+float(inverse_temporal(lo+rng.random()*(hi-lo),p.c,p.p))
            r=p.d0*math.exp(p.eta*(mj-p.m0))*math.sqrt(math.expm1(-math.log1p(-rng.random())/(p.q-1)))
            ang=rng.uniform(0,2*math.pi);xy=np.array([xj+r*math.cos(ang),yj+r*math.sin(ang)])
            if np.linalg.norm(xy)<=bg.R:push(time,xy,p.m0+rng.exponential(1/p.beta),'child',generation)
    def children(event,generation):
        tj=event[0];mj=event[3];lower=max(cutoff,tj)
        lo=float(temporal_cdf(lower-tj,p.c,p.p));hi=float(temporal_cdf(end-tj,p.c,p.p))
        mean=p.kappa*math.exp(p.alpha*(mj-p.m0))*(hi-lo)
        if not math.isfinite(mean):raise ModelFailure('Nonfinite offspring mean')
        count=int(rng.poisson(mean))
        if generated+count>max_events:raise ModelFailure('Offspring budget exceeded; no tail clipping')
        sample_children(event,generation,lo,hi,count)
    prepared=history_offspring if history_offspring is not None else prepare_history_offspring(p,h,cutoff,end)
    if not (prepared['cutoff']==cutoff and prepared['end']==end and
            prepared['history_sha256']==hashlib.sha256(h.tobytes()).hexdigest() and
            prepared['nine_parameters']=={k:v for k,v in asdict(p).items() if k!='gamma'}):
        raise ValueError('History offspring preparation context changed')
    lo,hi,means=prepared['lo'],prepared['hi'],prepared['means']
    if not (len(lo)==len(h) and len(hi)==len(h) and len(means)==len(h) and
            np.all(np.isfinite(means)) and np.all(means>=0)):
        raise ModelFailure('Invalid prepared offspring means')
    counts=rng.poisson(means)
    if generated+int(counts.sum())>max_events:
        raise ModelFailure('Offspring budget exceeded; no tail clipping')
    for i in np.flatnonzero(counts):
        sample_children(h[i],0,float(lo[i]),float(hi[i]),int(counts[i]))
    low=p.mu*math.exp(-2*abs(p.gamma));high=p.mu*math.exp(2*abs(p.gamma))
    for rate,kind in [(low,'floor'),(high-low,'residual')]:
        count=int(rng.poisson(rate*(end-cutoff)))
        if generated+count>max_events:raise ModelFailure('Immigrant proposal budget exceeded')
        for _ in range(count):push(rng.uniform(cutoff,end),bg.sample(rng),p.m0+rng.exponential(1/p.beta),kind,0)
    while heap:
        t,_,x,y,m,kind,generation=heapq.heappop(heap)
        if kind=='residual':
            z=covariate(t,np.array([x,y]),h)
            accept=(p.mu*math.exp(p.gamma*z)-low)/(high-low)
            if not -1e-12<=accept<=1+1e-12:raise ModelFailure('Invalid X1 thinning probability')
            if rng.random()>accept:continue
        event=[t,x,y,m];accepted.append(event+[kind=='floor',generation]);children(event,generation+1)
    return np.asarray(accepted,float).reshape(-1,6)


def record_cost_projection(run, receipts):
    """Diagnostic only, never relax guards or stop/extend scientific budgets."""
    rows=[read(checked_artifact(run,r)) for r in receipts]
    measured=[float(r['wall_seconds']) for r in rows]
    mean=sum(measured)/len(measured)
    projected=mean*NDAYS
    controls=run/'INTEGRATION_CONTROLS_TIMING.json'
    timing=read(controls) if controls.exists() else {}
    control_seconds=timing.get('wall_seconds')
    total=projected+control_seconds if control_seconds is not None else None
    receipt={'utc':now(),'completed_days':len(rows),'last_day_index':rows[-1]['day'],
        'measured_seconds_by_day':[{'day':r['day'],'seconds':r['wall_seconds']} for r in rows],
        'mean_seconds_per_day':mean,'projected_cascade_seconds_1025_days':projected,
        'measured_integration_controls_seconds':control_seconds,
        'projected_total_generation_seconds':total,
        'projection_basis':'Measured cascade+cell-assignment days; plus analytic controls if measured. Fit/score excluded.',
        'projection_is_estimate_not_operational_forecast':True,
        'exceeds_72_hours':(total if total is not None else projected)>72*3600,
        'Claude_review_required_if_exceeds_72_hours':True,'automatic_stop':False}
    history=run/'cost_projection_history';history.mkdir(exist_ok=True)
    saved=history/('R6_COST_'+uuid.uuid4().hex+'.json');write_json(saved,receipt)
    temporary=run/('R6_COST_PROJECTION_'+uuid.uuid4().hex+'.tmp')
    write_json(temporary,receipt)
    os.replace(temporary,run/'R6_COST_PROJECTION.json')
    print(json.dumps({'R6_COST_PROJECTION':receipt}),flush=True)


if __name__=='__main__':
    main()
