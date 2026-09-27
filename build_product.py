"""Build selected engine components into an independently runnable product."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'runtime'))
from engine_policy import validate_move_policy
READ_ONLY = ('nioh_memory','boss_probe','action_banks','controller_reader')


def stage_product(project, destination):
    # Products explicitly choose a capability set; recorder cannot acquire modification modules.
    # Copy only source/runtime inputs needed by that product, never tests, captures or engine headers.
    # Record source fingerprints so releases can be traced to the exact engine implementation.
    project, destination = Path(project).resolve(), Path(destination).resolve()
    spec=json.loads((project/'product.json').read_text(encoding='utf8'))
    if spec['kind'] not in ('recorder','sword'): raise ValueError('Unsupported product backend')
    if destination.exists(): raise ValueError('Build destination must be new')
    policy_path=project/'data/move-policy.json';policy=None
    if spec['kind']=='sword' and policy_path.is_file():
        identifiers={move['id'] for name in ('okatsu','jin_hayabusa')
            for move in json.loads((project/'data/imports'/f'{name}.json').read_text(encoding='utf8'))['moves']
            if move['flags'] not in (0x8078000000,0x8038000000)}
        policy=validate_move_policy(json.loads(policy_path.read_text(encoding='utf-8-sig')),identifiers)
    destination.mkdir(parents=True)
    runtime=destination/'runtime';runtime.mkdir()
    modules=READ_ONLY if spec['kind']=='recorder' else tuple(p.stem for p in (ROOT/'runtime').glob('*.py'))
    for name in modules: shutil.copyfile(ROOT/'runtime'/f'{name}.py',runtime/f'{name}.py')
    if spec['kind']=='sword':
        # Omit recorder/report CLI and catalogue editing from the consumer runtime.
        # Keep the validated read/discovery primitives used by live preparation.
        # Cut at explicit module boundaries so build tests can check the exported surface.
        for name,boundary in [('boss_probe','def record('),('catalogue','def save_catalogue('),('action_banks','def inspect_pair(')]:
            path=runtime/f'{name}.py';source=path.read_text(encoding='utf8')
            path.write_text(source[:source.index(boundary)],encoding='utf8')
    shutil.copytree(project/('src' if spec['kind']=='recorder' else 'app'),destination/('src' if spec['kind']=='recorder' else 'app'),ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copyfile(project/'launch.py',destination/'launch.py')
    data=destination/'data';data.mkdir()
    if spec['kind']=='recorder':
        shutil.copyfile(project/'data/bosses.json',data/'bosses.json')
    else:
        for name in ('mod.json','moves.json','preset.json','controller-calibration.json'):
            shutil.copyfile(project/'data'/name,data/name)
        for name in ('imports','resources'): shutil.copytree(project/'data'/name,data/name)
        if policy is not None:
            (data/'move-policy.json').write_text(json.dumps(policy,indent=2)+'\n',encoding='utf8')
        native=runtime/'native/build';native.mkdir(parents=True)
        for name in ('nioh_skill_runtime.dll','nioh_resources.dll'):
            shutil.copyfile(ROOT/'runtime/native/build'/name,native/name)
        shutil.copyfile(ROOT/'third_party/minhook/LICENSE.txt',destination/'MinHook-LICENSE.txt')
    files={p.relative_to(destination).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
           for p in destination.rglob('*') if p.is_file()}
    (destination/'build-manifest.json').write_text(json.dumps(dict(product=spec,engine_commit=subprocess.check_output(
        ['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),engine_dirty=bool(subprocess.check_output(
        ['git','status','--porcelain'],cwd=ROOT,text=True).strip()),files=files),indent=2)+'\n',encoding='utf8')
    return spec


def main():
    # Stage first so dependency and data boundaries can be checked without packaging.
    # PyInstaller is a build-only tool; consumers receive a self-contained application.
    # Use a fresh build directory rather than deleting or overwriting source workspaces.
    parser=argparse.ArgumentParser(description='Build a Tanto product from selected engine components')
    parser.add_argument('project',type=Path);parser.add_argument('--stage-only',action='store_true')
    parser.add_argument('--onedir',action='store_true');args=parser.parse_args()
    project=args.project.resolve();build=project/'.build'/str(time.time_ns());stage=build/'stage'
    spec=stage_product(project,stage)
    if args.stage_only: print(stage);return
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    if spec.get('engine_commit') != revision:
        raise ValueError('Review and pin this engine revision in product.json before packaging')
    if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip():
        raise ValueError('Commit engine changes before packaging a reproducible release')
    local={p.stem for p in stage.rglob('*.py')};imports=set(local)
    for p in stage.rglob('*.py'):
        for node in ast.walk(ast.parse(p.read_text(encoding='utf8'))):
            if isinstance(node,ast.Import): imports.update(item.name for item in node.names)
            elif isinstance(node,ast.ImportFrom) and node.module: imports.add(node.module)
    command=[sys.executable,'-m','PyInstaller','--noconfirm','--onedir' if args.onedir else '--onefile','--windowed',
             '--name',spec['name'],'--distpath',str(project/'dist'),'--workpath',str(build/'work'),'--specpath',str(build),
             '--paths',str(stage/'runtime'),'--paths',str(stage/'app'),'--paths',str(stage/'src')]
    for name in sorted(imports):
        if name.split('.')[0] in local or name.split('.')[0] in sys.stdlib_module_names:
            command+=['--hidden-import',name]
    for folder in ('data','runtime','app','src'):
        if (stage/folder).exists(): command+=['--add-data',f'{stage/folder};{folder}']
    command+=['--add-data',f'{stage/"build-manifest.json"};.']
    if (stage/'MinHook-LICENSE.txt').exists(): command+=['--add-data',f'{stage/"MinHook-LICENSE.txt"};.']
    subprocess.run(command+[str(stage/'launch.py')],check=True)
    shutil.copyfile(stage/'build-manifest.json',project/'dist'/f'{spec["name"]}-manifest.json')


if __name__=='__main__': main()
