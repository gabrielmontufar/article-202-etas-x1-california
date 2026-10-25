"""Single-process synthetic/software suite, guarded before scientific imports."""
import ctypes,datetime,json,os,pathlib,shutil,sys,unittest

class MEMORYSTATUSEX(ctypes.Structure):
    _fields_=[('dwLength',ctypes.c_ulong),('dwMemoryLoad',ctypes.c_ulong),
              ('ullTotalPhys',ctypes.c_ulonglong),('ullAvailPhys',ctypes.c_ulonglong),
              ('ullTotalPageFile',ctypes.c_ulonglong),('ullAvailPageFile',ctypes.c_ulonglong),
              ('ullTotalVirtual',ctypes.c_ulonglong),('ullAvailVirtual',ctypes.c_ulonglong),
              ('ullAvailExtendedVirtual',ctypes.c_ulonglong)]

def resources():
    m=MEMORYSTATUSEX();m.dwLength=ctypes.sizeof(m)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):raise RuntimeError('Resource measurement failed')
    return {'free_RAM_MiB':m.ullAvailPhys/2**20,'free_disk_GiB':shutil.disk_usage('C:/').free/2**30}

if __name__=='__main__':
    before=resources()
    if before['free_RAM_MiB']<512 or before['free_disk_GiB']<4:
        print(json.dumps({'status':'RESOURCE_HOLD','resources':before}));raise SystemExit(3)
    for k in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='1'
    os.environ['PYTHONDONTWRITEBYTECODE']='1'
    os.environ['MPLCONFIGDIR']=r'C:\Users\gjm31\forge_cache\panama_probabilistic_20261020\matplotlib_runtime'
    kernel=ctypes.windll.kernel32
    kernel.GetCurrentProcess.restype=ctypes.c_void_p
    kernel.SetPriorityClass.argtypes=[ctypes.c_void_p,ctypes.c_ulong]
    kernel.GetPriorityClass.argtypes=[ctypes.c_void_p]
    kernel.GetPriorityClass.restype=ctypes.c_ulong
    handle=kernel.GetCurrentProcess()
    if not kernel.SetPriorityClass(handle,0x4000) or kernel.GetPriorityClass(handle)!=0x4000:
        raise RuntimeError('Cannot establish BelowNormal priority')
    root=pathlib.Path(__file__).resolve().parents[1];os.chdir(root)
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.discover('tests'))
    receipt={'status':'PASS' if result.wasSuccessful() else 'FAIL','tests_run':result.testsRun,
        'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
        'before':before,'after':resources(),'verified_priority':'BelowNormal','threads':1,'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'python':sys.executable,'real_model_fits':False,'real_scores':False,'forecasts':False,
        'meaning':'Software/synthetic fixtures only; not full preflight, power or earthquake effectiveness'}
    print(json.dumps(receipt,indent=2))
    if len(sys.argv)>1:
        with pathlib.Path(sys.argv[1]).open('x',encoding='utf-8') as f:json.dump(receipt,f,indent=2)
    raise SystemExit(0 if result.wasSuccessful() else 1)
