"""Portable resource/priority adapter; no change to numerical criteria."""
import ctypes,hashlib,json,os,pathlib,shutil,sys
BASE=pathlib.Path(__file__).resolve().parent
def sha(path):
    h=hashlib.sha256()
    with pathlib.Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
def write(path,obj):
    with pathlib.Path(path).open('x',encoding='utf8') as f:json.dump(obj,f,indent=2,allow_nan=False)
def resources():
    if sys.platform=='win32':
        class Memory(ctypes.Structure):
            _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong),('total_phys',ctypes.c_ulonglong),('avail_phys',ctypes.c_ulonglong),('total_page',ctypes.c_ulonglong),('avail_page',ctypes.c_ulonglong),('total_virtual',ctypes.c_ulonglong),('avail_virtual',ctypes.c_ulonglong),('avail_extended',ctypes.c_ulonglong)]
        m=Memory();m.length=ctypes.sizeof(m)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):raise RuntimeError('Memory probe failed')
        free=m.avail_phys/1024**2
    else:
        values={line.split(':')[0]:int(line.split()[1]) for line in pathlib.Path('/proc/meminfo').read_text().splitlines() if ':' in line}
        free=values['MemAvailable']/1024
        # Respect container limits as well as host MemAvailable.
        limit=pathlib.Path('/sys/fs/cgroup/memory.max');used=pathlib.Path('/sys/fs/cgroup/memory.current')
        if limit.exists() and used.exists() and limit.read_text().strip()!='max':
            free=min(free,(int(limit.read_text())-int(used.read_text()))/1024**2)
    return {'free_RAM_MiB':free,'free_disk_GiB':shutil.disk_usage(BASE).free/1024**3}
def guard():
    current=resources();print('RESOURCES',json.dumps(current),flush=True)
    if current['free_RAM_MiB']<512 or current['free_disk_GiB']<4:raise RuntimeError('RESOURCE_HOLD: unchanged 512 MiB / 4 GiB')
    if sys.platform=='win32':
        k=ctypes.windll.kernel32;k.GetCurrentProcess.restype=ctypes.c_void_p
        k.SetPriorityClass.argtypes=[ctypes.c_void_p,ctypes.c_ulong]
        if not k.SetPriorityClass(k.GetCurrentProcess(),0x4000):raise RuntimeError('BelowNormal failed')
    else:
        if os.getpriority(os.PRIO_PROCESS,0)<5:os.nice(5-os.getpriority(os.PRIO_PROCESS,0))
    for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):os.environ[key]='1'
    return resources
