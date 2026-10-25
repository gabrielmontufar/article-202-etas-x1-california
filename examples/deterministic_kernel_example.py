"""Exercise preserved kernels against analytic values; no random sampling, fit or score."""
from pathlib import Path
import argparse,hashlib,json,os,sys,importlib.metadata
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[key]='1'
sys.dont_write_bytecode=True
root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--fixture',type=Path,default=Path(__file__).with_name('deterministic_fixture.json'))
args=parser.parse_args()
fixture=json.loads(args.fixture.read_text(encoding='utf-8'))
sys.path.insert(0,str(root/'source/ART/scripts'))
from point_models import temporal_cdf,radial_cdf
from polygon_integration import PolygonIntegrator
import numpy as np
t,r,s=fixture['temporal'],fixture['radial'],fixture['square']
values={'temporal_cdf':temporal_cdf(t['t'],t['c'],t['p']).tolist(),'radial_cdf':radial_cdf(r['r'],r['d'],r['q']).tolist(),'square_gaussian_mass':float(PolygonIntegrator(s['starts'],s['ends']).masses([s['parent']],s['sigma'],order=s['order'],gaussian=True)[0])}
errors={'temporal_cdf':max(abs(a-b) for a,b in zip(values['temporal_cdf'],t['expected_cdf'])),'radial_cdf':max(abs(a-b) for a,b in zip(values['radial_cdf'],r['expected_cdf'])),'square_gaussian_mass':abs(values['square_gaussian_mass']-s['expected_gaussian_mass'])}
if not all(np.isfinite(x) and x<=fixture['absolute_tolerance'] for x in errors.values()):
    raise AssertionError(json.dumps(errors))
print(json.dumps({'status':'PASS_DETERMINISTIC_DUMMY_CASE_ONLY','values':values,'absolute_errors':errors,'versions':{'Python':sys.version.split()[0],'numpy':importlib.metadata.version('numpy'),'scipy':importlib.metadata.version('scipy')},'sources_sha256':{n:hashlib.sha256((root/'source/ART/scripts'/n).read_bytes()).hexdigest() for n in ['point_models.py','polygon_integration.py']},'random_samples':0,'fits':0,'forecast_or_IG_scoring':0,'proves_full_study_reproduction':False},indent=2))
