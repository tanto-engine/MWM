# Select packaged or repository Engine code and dispatch the trainer or an allowed runtime worker.
# PyInstaller exposes bundled files through _MEIPASS; source development uses this checkout.
# Keep product data/state paths separate from shared implementation; see CODE_GUIDE.md.
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys

ROOT=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))
engine=Path(os.environ.get('TANTO_ENGINE_ROOT',ROOT.parent))
code=ROOT/'runtime' if (ROOT/'runtime/engine_config.py').exists() else engine/'runtime'
sys.path[:0]=[str(ROOT/'app'),str(code)]
os.environ['TANTO_MOD_ROOT']=str(ROOT)
os.environ['TANTO_RUNTIME_CODE']=str(code)
if getattr(sys,'frozen',False):
    os.environ.setdefault('NIOH_RUNTIME_HOME',str(Path(os.environ['LOCALAPPDATA'])/'Tanto/Sword/runtime'))

if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--desktop-worker':
        # Electron owns presentation while this console worker owns reviewed configuration requests.
        # Gameplay subprocesses continue to use the separate existing --worker allowlist.
        # Keeping the legacy trainer path permits comparison until desktop acceptance is complete.
        from web_worker import main
        raise SystemExit(main())
    elif len(sys.argv)>2 and sys.argv[1]=='--worker':
        worker=sys.argv[2]
        if worker not in ('prepare_session','supervisor','run_dispatch','native_loader'): raise SystemExit('Unsupported worker')
        sys.argv=[worker,*sys.argv[3:]]
        runpy.run_module(worker,run_name='__main__')
    elif not getattr(sys,'frozen',False) and len(sys.argv)==1:
        # The default source entry now opens Electron through the configured PowerShell launcher.
        # Pass this interpreter explicitly so its worker uses the same installed Engine dependencies.
        # Compilation is JavaScript-only; every EXE build still belongs to Engine's release gate.
        raise SystemExit(subprocess.run(['pwsh.exe','-NoProfile','-File',str(ROOT/'Trainer.ps1'),
                                        '-PythonRuntime',sys.executable],check=False).returncode)
    else:
        if len(sys.argv)>1 and sys.argv[1]=='--legacy-ui': sys.argv.pop(1)
        from trainer import main
        raise SystemExit(main())
