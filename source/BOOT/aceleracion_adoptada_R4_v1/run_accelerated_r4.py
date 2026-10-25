"""Gated R4 numerical acceleration and authorized one-start bootstrap CLI."""
import hashlib,importlib.metadata,json,os,pathlib,sys
HERE=pathlib.Path(__file__).resolve().parent;BASE=HERE.parent
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):os.environ[key]='1'
os.environ['NUMBA_NUM_THREADS']='1' if sys.platform=='win32' else os.environ.get('NUMBA_NUM_THREADS','2')
sys.path.insert(0,str(BASE));sys.path.insert(0,str(HERE));import run_r4 as base
reference_capsule=base.reference_capsule
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def check_package():
    base.check_package();path=HERE/'ADOPTION_MANIFEST.json'
    if not path.exists():raise RuntimeError('ADOPTION_NOT_APPROVED_WINDOWS_EQUIVALENCE_PENDING')
    manifest=json.loads(path.read_text())
    if manifest['status']!='ADOPTED_AFTER_WINDOWS_EQUIVALENCE_PASS':raise RuntimeError('No adopted profile')
    for name,expected in manifest['files'].items():
        if sha(HERE/name)!=expected:raise RuntimeError('ACCELERATED_PROFILE_HASH_MISMATCH: '+name)
    for name,version in manifest['versions'].items():
        if importlib.metadata.version(name)!=version:raise RuntimeError('ACCELERATED_ENVIRONMENT_VERSION_HOLD: '+name)
    receipt=json.loads((HERE/'WINDOWS_EQUIVALENCE_RESULT.json').read_text())
    if receipt['status']!='PASS':raise RuntimeError('No Windows numerical PASS')
    return manifest
def configure_backend():
    check_package()
    from r4_numba_warmstart_profile import install_backend,patch_package_bootstrap
    threads=1 if sys.platform=='win32' else int(os.environ['NUMBA_NUM_THREADS'])
    if threads not in (1,2):raise RuntimeError('This profile authorizes one Windows thread, at most two cloud threads')
    metadata=install_backend(HERE,threads);patch_package_bootstrap(base,HERE/'ADOPTION_MANIFEST.json')
    return metadata
def main():
    check_package()
    if len(sys.argv)>1 and sys.argv[1] in ('verify','-h','--help'):
        base.main();print('ACCELERATED_PROFILE_AND_PINS_PASS');return
    base.guard();configure_backend();base.main()
if __name__=='__main__':main()
