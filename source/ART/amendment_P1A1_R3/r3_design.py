"""R3 geometric supports and unchanged A1 Mc/rate diagnostics; no forecasts."""
import bisect
import ctypes
import datetime as dt
import gzip
import hashlib
import json
import math
import os
import pathlib
import shutil
import sqlite3
import subprocess
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
HERE = pathlib.Path(__file__).resolve().parent
CACHE = pathlib.Path(r'C:\Users\gjm31\forge_cache\panama_probabilistic_20261020\amendment_20261021')
OUT = CACHE / 'R3'
RULE = HERE / 'R3_PREANALYSIS_RULES_ES.md'


def sha(p):
    h = hashlib.sha256()
    with pathlib.Path(p).open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def write(path, obj):
    with pathlib.Path(path).open('x', encoding='utf-8') as f:
        json.dump(obj, f, indent=2, ensure_ascii=False, allow_nan=False)


def guard():
    sys.path.insert(0, str(ROOT / 'scripts'))
    from run_preflight import resources
    res = resources()
    print('START_RESOURCES', json.dumps(res), flush=True)
    if res['free_RAM_MiB'] < 512 or res['free_disk_GiB'] < 4:
        raise RuntimeError('RESOURCE_HOLD: original minimum unchanged')
    k = ctypes.windll.kernel32
    k.GetCurrentProcess.restype = ctypes.c_void_p
    k.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    k.GetPriorityClass.argtypes = [ctypes.c_void_p]
    k.GetPriorityClass.restype = ctypes.c_ulong
    h = k.GetCurrentProcess()
    if not k.SetPriorityClass(h, 0x4000) or k.GetPriorityClass(h) != 0x4000:
        raise RuntimeError('BelowNormal could not be verified')
    for name in ['OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS']:
        os.environ[name] = '1'
    print('PRIORITY BelowNormal VERIFIED; numerical threads=1', flush=True)
    return resources


def geometry():
    import shapefile
    from shapely.geometry import Point, box, mapping, shape
    from shapely.ops import unary_union
    assert not (OUT / 'R3_GEOGRAPHIC_MASKS.json').exists(), 'No duplicate geometry run'
    zpath = OUT / 'ne_10m_land.zip'
    receipt = json.loads((OUT / 'ne_10m_land.zip.receipt.json').read_text())
    assert sha(zpath) == receipt['sha256']
    extracted = OUT / 'natural_earth_land'
    extracted.mkdir(exist_ok=False)
    with zipfile.ZipFile(zpath) as z:
        assert z.testzip() is None
        for item in z.infolist():
            if pathlib.PurePosixPath(item.filename).name != item.filename:
                raise ValueError('Unexpected archive member path')
            if item.file_size > 32 * 1024**2:
                raise ValueError('Archive member beyond geometry budget')
            with (extracted / item.filename).open('xb') as f:
                f.write(z.read(item))
    clip = box(-130, 25, -110, 47)
    pieces = []
    reader = shapefile.Reader(str(extracted / 'ne_10m_land.shp'))
    for raw in reader.iterShapes(bbox=clip.bounds):
        g = shape(raw.__geo_interface__)
        if not g.is_valid:
            raise ValueError('Invalid original land geometry; no automatic repair')
        cut = g.intersection(clip)
        if not cut.is_empty:
            pieces.append(cut)
    reader.close()
    union = unary_union(pieces)
    parts = [union] if union.geom_type == 'Polygon' else list(union.geoms)
    mainland = [p for p in parts if p.covers(Point(-118, 34))]
    assert len(mainland) == 1, 'Mainland component not unique'
    land = mainland[0]
    for name, lon, lat in [('San Francisco', -122.42, 37.77), ('Sacramento', -121.49, 38.58),
                            ('Ridgecrest', -117.67, 35.62), ('Reno', -119.81, 39.53)]:
        assert land.covers(Point(lon, lat)), 'Mainland QA failed: ' + name
    source = json.loads((CACHE / 'CALIFORNIA_RELM_MASK.json').read_text())
    scdata = json.loads((OUT / 'SCSN_REPORTING_BOUNDARY_DECODED.json').read_text())
    sc = shape(scdata['features'][0]['geometry'])
    assert sc.geom_type == 'Polygon' and sc.is_valid
    masks = {'R3_LAND': [], 'R3_SCSN_LAND': []}
    step = source['step']
    for lo, la in source['cells']:
        lo, la = round(lo, 7), round(la, 7)
        cell = box(lo, la, round(lo + step, 7), round(la + step, 7))
        if land.covers(cell):
            masks['R3_LAND'].append([lo, la])
            if sc.covers(cell):
                masks['R3_SCSN_LAND'].append([lo, la])
    assert 0 < len(masks['R3_SCSN_LAND']) < len(masks['R3_LAND']) < len(source['cells'])
    obj = {'status': 'GEOMETRY_ONLY_BEFORE_NEW_CATALOGUE_STATISTICS',
           'created_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
           'rule_sha256': sha(RULE), 'code_sha256': sha(__file__),
           'base_mask_sha256': sha(CACHE / 'CALIFORNIA_RELM_MASK.json'),
           'land_zip_sha256': sha(zpath), 'land_version': (extracted / 'ne_10m_land.VERSION.txt').read_text().strip(),
           'SCboundary_original_sha256': sha(OUT / 'SCSN_REPORTING_BOUNDARY_ORIGINAL.json'),
           'SCboundary_decoded_sha256': sha(OUT / 'SCSN_REPORTING_BOUNDARY_DECODED.json'),
           'step': step, 'cell_convention': 'lower-left corner; whole 0.1-degree square',
           'depth_support_km': [0, 70], 'original_RELM_cells': len(source['cells']),
           'masks': {name: {'cell_count': len(cells), 'cells': cells} for name, cells in masks.items()},
           'priority_order': list(masks), 'forecasts_issued': 0,
           'completeness_inferred_from_land_or_reporting_polygon': False}
    write(OUT / 'R3_GEOGRAPHIC_MASKS.json', obj)
    write(HERE / 'R3_GEOGRAPHIC_MASKS.json', obj)
    write(OUT / 'R3_MAINLAND_GEOMETRY.geojson', {'type': 'Feature', 'properties': {}, 'geometry': mapping(land)})
    print('GEOMETRY_COUNTS', {k: len(v) for k, v in masks.items()}, flush=True)
    return obj


def analyze(name):
    import numpy as np
    sys.path.insert(0, str(ROOT / 'amendment_P1A1'))
    from completeness_epoch import bootstrap_epochs
    gpath = OUT / 'R3_GEOGRAPHIC_MASKS_WITH_NCSN.json'
    geo = json.loads(gpath.read_text())
    pre = json.loads((OUT / 'R3_PRECOMPUTATION_RECEIPT.json').read_text())
    assert pre['geometry_sha256'] == sha(gpath) and pre['rule_sha256'] == sha(RULE)
    assert pre['NCSN_extension_rule_sha256'] == sha(HERE/'R3_NCSN_EXTENSION_BEFORE_STATISTICS_ES.md')
    assert name in geo['masks']
    output = OUT / (name + '_MC_AND_RATE_DESIGN.json')
    assert not output.exists(), 'Completed result preserved; no duplicate run'
    manifest = json.loads((CACHE / 'california_training/CAPTURE_MANIFEST.json').read_text())
    path = CACHE / 'california_training/ANSS_RELM_TRAINING.sqlite'
    assert manifest['status'] == 'COMPLETE_PUBLIC_DESIGN_TRAINING'
    assert sha(path) == manifest['database_sha256'], 'Original training changed'
    keys = {(round((lo + 180) * 10), round((la + 90) * 10)) for lo, la in geo['masks'][name]['cells']}
    db = sqlite3.connect(f'file:{path.as_posix()}?mode=ro&immutable=1', uri=True)
    db.execute('PRAGMA cache_size=-8192')
    end = dt.datetime.fromisoformat(manifest['origin_cutoff_exclusive'])
    start = dt.datetime(1995, 1, 1, tzinfo=dt.timezone.utc)
    endms = round(end.timestamp() * 1000)
    startms = round(start.timestamp() * 1000)
    recentms = endms - 365 * 86400 * 1000
    e0 = round(dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
    e1 = round(dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
    months = (end.year - 1995) * 12 + end.month
    maxmag = float(db.execute('SELECT MAX(mag) FROM events').fetchone()[0])
    centres = np.arange(10, math.ceil(maxmag * 10) + 2) / 10
    cuts = centres.tolist()
    monthly = np.zeros((months, len(centres)), dtype=np.int64)
    block_ms = 90 * 86400 * 1000
    nblocks = (endms - startms) // block_ms
    # Each raw magnitude contributes to one exact cut interval. Reverse sums
    # later count raw mag>=cut; diagnostic rounding cannot inflate target N.
    counts = np.zeros((len(cuts), 3 + nblocks), dtype=np.int64)
    nsource = 0
    included = 0
    for time_ms, mag, lon, lat in db.execute('SELECT time_ms,mag,lon,lat FROM events'):
        nsource += 1
        key = (math.floor((lon + 180) * 10 + 1e-8), math.floor((lat + 90) * 10 + 1e-8))
        if key not in keys:
            continue
        assert startms <= time_ms < endms and mag >= 1
        t = dt.datetime.fromtimestamp(time_ms / 1000, dt.timezone.utc)
        mo = (t.year - 1995) * 12 + t.month - 1
        mi = int(math.floor(mag * 10 + .5)) - 10
        monthly[mo, mi] += 1
        j = bisect.bisect_right(cuts, mag) - 1
        assert j >= 0
        counts[j, 0] += 1
        counts[j, 1] += time_ms >= recentms
        counts[j, 2] += e0 <= time_ms < e1
        block = (time_ms - startms) // block_ms
        if 0 <= block < nblocks:
            counts[j, 3 + block] += 1
        included += 1
    db.close()
    assert nsource == manifest['target_rows'] and int(monthly.sum()) == included
    cdf = np.cumsum(counts[::-1], axis=0)[::-1]
    epochs = [{'label': f'{y}-{min(y+5,end.year)}', 'first_month': (y-1995)*12,
               'last_month': min(months, (y+5-1995)*12)} for y in range(1995, end.year+1, 5)]
    pooled_epochs = epochs[:5] + [{'label': '2020-cutoff', 'first_month': 300, 'last_month': months}]
    print('SOURCE_VERIFIED', nsource, 'SUPPORT_TRAINING', name, included, flush=True)
    initial = bootstrap_epochs(monthly, epochs, centres, 1., name + '_initial', 500)
    pooled = bootstrap_epochs(monthly, pooled_epochs, centres, 1., name + '_terminal_pool', 500)

    def summarize(threshold):
        j = next(j for j, cut in enumerate(cuts) if abs(cut-threshold) < 1e-8)
        c = cdf[j]
        blocks = c[3:]
        mean = float(blocks.mean())
        return {'threshold': threshold, 'training_events': int(c[0]), 'last365_events': int(c[1]),
                'last365_rate_expected90': float(c[1])*90/365,
                'all_training_rate_expected90': float(c[0])*90/((end-start).total_seconds()/86400),
                'epoch2020_2025_rate_expected90': float(c[2])*90/((e1-e0)/86400000),
                'full_nonoverlapping_90day_blocks': int(nblocks),
                'historical_block_counts': blocks.tolist(),
                'historical_block_quantiles025_50_975': np.quantile(blocks, [.025,.5,.975]).tolist(),
                'historical_block_Fano': float(blocks.var(ddof=1))/mean if mean else None,
                'design_last365_expected_at_least100': float(c[1])*90/365>=100,
                'power_established': False, 'forecast_issued': False,
                'meaning': 'Historical planning counts; not a forecast, power test or prospective interval'}

    thresholds = sorted({math.ceil(10*x-1e-7)/10 for x in
                         [2.5, initial['global_point'], initial['proposed_Mstar_from_global_upper95'],
                          pooled['global_point'], pooled['proposed_Mstar_from_global_upper95']] if x is not None})
    proposed = initial['proposed_Mstar_from_global_upper95']
    target = max(2.5, proposed) if proposed is not None else None
    rates = [summarize(t) for t in thresholds]
    target_rate = summarize(target) if target is not None else None
    qualified = initial['threshold_design_qualified'] and target_rate['design_last365_expected_at_least100']
    result = {'status': 'REVIEW_ONLY_90DAY_DESIGN_PASS' if qualified else 'REVIEW_ONLY_90DAY_DESIGN_HOLD',
              'mask_name': name, 'completed_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
              'rule_sha256': sha(RULE), 'code_sha256': sha(__file__),
              'NCSN_extension_rule_sha256': pre['NCSN_extension_rule_sha256'],
              'estimator_code_sha256': sha(ROOT/'amendment_P1A1/completeness_epoch.py'),
              'mask_sha256': sha(gpath), 'precomputation_receipt_sha256': sha(OUT/'R3_PRECOMPUTATION_RECEIPT.json'),
              'source_manifest_sha256': sha(CACHE/'california_training/CAPTURE_MANIFEST.json'),
              'source_database_sha256': manifest['database_sha256'],
              'training_cutoff_utc': end.isoformat(), 'source_rows_scanned': nsource,
              'training_records': included, 'target_cells': len(keys),
              'initial_epochs': initial, 'terminal_pool_sensitivity_not_used_for_decision': pooled,
              'proposed_target_threshold_not_activated': target, 'proposed_target_rate': target_rate,
              'rate_design': rates, 'R3_design_qualifies': bool(qualified),
              'power_established': False, 'forecast_issued': False, 'scores_computed': False,
              'amendment_sealed': False, 'Panama_role': 'SECONDARY_DESCRIPTIVE',
              'california_duration_days_proposed': 90}
    write(output, result)
    print('RESULT', name, 'point', initial['global_point'], 'Mstar', proposed,
          'target', target, 'E90', target_rate['last365_rate_expected90'] if target_rate else None,
          'qualified', qualified, flush=True)
    return result


def extend_ncsn():
    from shapely.geometry import box, shape
    gpath = OUT / 'R3_GEOGRAPHIC_MASKS.json'
    geo = json.loads(gpath.read_text())
    data = json.loads((OUT/'USGS_NCSN_AUTHORITATIVE_DECODED.json').read_text())
    found = [f for f in data['authoritative']['features']
             if f['properties']['network'].upper() == 'NC' and f['properties']['type'] == 'anss']
    assert len(found) == 1
    nc = shape(found[0]['geometry'])
    assert nc.geom_type == 'Polygon' and nc.is_valid
    cells = [[lo,la] for lo,la in geo['masks']['R3_LAND']['cells']
             if nc.covers(box(lo,la,round(lo+.1,7),round(la+.1,7)))]
    assert cells and len(cells) < geo['masks']['R3_LAND']['cell_count']
    geo.update(initial_geometry_sha256=sha(gpath),
               NCSN_extension_rule_sha256=sha(HERE/'R3_NCSN_EXTENSION_BEFORE_STATISTICS_ES.md'),
               NC_authoritative_original_sha256=sha(OUT/'USGS_NCSN_AUTHORITATIVE_ORIGINAL.json'),
               NC_authoritative_decoded_sha256=sha(OUT/'USGS_NCSN_AUTHORITATIVE_DECODED.json'),
               extended_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
               extension_code_sha256=sha(__file__))
    geo['masks']['R3_NCSN_LAND'] = {'cell_count': len(cells), 'cells': cells}
    geo['priority_order'].append('R3_NCSN_LAND')
    write(OUT/'R3_GEOGRAPHIC_MASKS_WITH_NCSN.json',geo)
    write(HERE/'R3_GEOGRAPHIC_MASKS_WITH_NCSN.json',geo)
    print('GEOMETRY_COUNTS', {k:v['cell_count'] for k,v in geo['masks'].items()},flush=True)
    return geo


if __name__ == '__main__':
    resources = guard()
    if sys.argv[1] == 'geometry':
        geometry()
    elif sys.argv[1] == 'analyze':
        analyze(sys.argv[2])
    elif sys.argv[1] == 'extend-ncsn':
        extend_ncsn()
    else:
        raise ValueError('Unknown bounded stage')
    print('END_RESOURCES', json.dumps(resources()), flush=True)
