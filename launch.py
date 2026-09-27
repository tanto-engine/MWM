# Select packaged or sibling Engine code and dispatch the trainer or an allowed runtime worker.
# PyInstaller exposes bundled files through _MEIPASS; source development uses this checkout.
# Keep product data/state paths separate from shared implementation; see CODE_GUIDE.md.
import json
import os
from pathlib import Path
import runpy
import sys

ROOT=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))
engine=Path(os.environ.get('TANTO_ENGINE_ROOT',ROOT.parent/'tanto-engine'))
code=ROOT/'runtime' if (ROOT/'runtime/engine_config.py').exists() else engine/'runtime'
sys.path[:0]=[str(ROOT/'app'),str(code)]
os.environ['TANTO_MOD_ROOT']=str(ROOT)
os.environ['TANTO_RUNTIME_CODE']=str(code)
if getattr(sys,'frozen',False):
    os.environ.setdefault('NIOH_RUNTIME_HOME',str(Path(os.environ['LOCALAPPDATA'])/'Tanto/Sword/runtime'))

if __name__=='__main__':
    if len(sys.argv)>2 and sys.argv[1]=='--worker':
        worker=sys.argv[2]
        if worker not in ('prepare_session','supervisor','run_dispatch','native_loader'): raise SystemExit('Unsupported worker')
        sys.argv=[worker,*sys.argv[3:]]
        runpy.run_module(worker,run_name='__main__')
    else:
        from trainer import main
        raise SystemExit(main())
