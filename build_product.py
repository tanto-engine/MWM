"""Build selected engine components into an independently runnable product."""
import argparse
import ast
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'runtime'))
from engine_policy import validate_move_policy
READ_ONLY = ('nioh_memory','boss_probe','action_banks','controller_reader')


def source_state(project):
    # Identify the exact saved source behind an EXE, like a build's fingerprint.
    # Git HEAD names the commit; porcelain status also detects staged and untracked changes.
    # Ignored compiler outputs are not source changes and do not make the checkout dirty.
    def git(*args):
        # Run a read-only Git query inside the requested repository.
        # Argument lists preserve spaces in Windows paths without invoking another shell.
        # A failed query raises instead of inventing a clean revision for the release receipt.
        return subprocess.check_output(['git','-C',str(project),*args],text=True).strip()
    return dict(commit=git('rev-parse','HEAD'),dirty=bool(git('status','--porcelain')))


def release_inputs(project):
    # Reject a release whose version, notes, source or dependencies cannot be traced.
    # Check both local and remote tags so another checkout cannot silently reuse a published version.
    # All three checkouts participate in integration tests; their exact clean commits enter the receipt.
    spec=json.loads((project/'product.json').read_text(encoding='utf8'))
    version=spec.get('version','')
    if not re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-(?:alpha|beta|rc)\.[1-9]\d*)?',version):
        raise ValueError('Set a release version such as 0.2.0-alpha.1 in product.json')
    if f'## {version}\n' not in (project/'CHANGELOG.md').read_text(encoding='utf8'):
        raise ValueError('Add release notes for this version to CHANGELOG.md')
    sources={p.name:source_state(p) for p in (ROOT,ROOT.parent/'SKM',ROOT.parent/'tanto-recorder')}
    if any(state['dirty'] for state in sources.values()):
        raise ValueError('Commit all Engine, SKM and Recorder changes before compiling an EXE')
    if spec.get('engine_commit')!=sources[ROOT.name]['commit']:
        raise ValueError('Review and pin this Engine revision in product.json before packaging')
    used=(project/'dist'/version).exists()
    for args in (['tag','--list',f'v{version}'],['ls-remote','--tags','origin',f'refs/tags/v{version}']):
        used=used or bool(subprocess.check_output(['git','-C',str(project),*args],text=True).strip())
    if used:
        raise ValueError('This release version already exists; increment it before rebuilding')
    dependencies={}
    for path in (ROOT/'requirements-build.txt',project/'requirements.txt'):
        if not path.exists():continue
        for line in path.read_text().splitlines():
            if not line or line.startswith('#'):continue
            name,expected=line.split('==');actual=importlib.metadata.version(name)
            if actual!=expected:raise ValueError(f'Install {name}=={expected} before building (found {actual})')
            dependencies[name]=actual
    return spec,sources,dependencies


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
    engine=source_state(ROOT)
    (destination/'build-manifest.json').write_text(json.dumps(dict(product=spec,
        engine_commit=engine['commit'],engine_dirty=engine['dirty'],files=files),indent=2)+'\n',encoding='utf8')
    return spec


def main():
    # Stage first so dependency and data boundaries can be checked without packaging.
    # PyInstaller is a build-only tool; consumers receive a self-contained application.
    # Use a fresh build directory rather than deleting or overwriting source workspaces.
    parser=argparse.ArgumentParser(description='Build a Tanto product from selected engine components')
    parser.add_argument('project',type=Path);parser.add_argument('--stage-only',action='store_true')
    parser.add_argument('--onedir',action='store_true');args=parser.parse_args()
    project=args.project.resolve();build=project/'.build'/str(time.time_ns());stage=build/'stage'
    if args.stage_only: stage_product(project,stage);print(stage);return
    spec,sources,dependencies=release_inputs(project)
    build.mkdir(parents=True)
    if spec['kind']=='sword':
        subprocess.run(['pwsh','-NoProfile','-File',str(ROOT/'runtime/native/Build.ps1')],check=True)
    with (build/'offline-tests.log').open('w',encoding='utf8') as log:
        subprocess.run(['pwsh','-NoProfile','-File',str(ROOT/'Test-Offline.ps1'),'-PythonRuntime',sys.executable],
                       stdout=log,stderr=subprocess.STDOUT,check=True)
    counts=re.findall(r'Ran (\d+) tests?',(build/'offline-tests.log').read_text(encoding='utf8'))
    if len(counts)!=2:raise ValueError('Both maintained offline test entrypoints must report their results')
    stage_product(project,stage)
    numeric=tuple(int(n) for n in spec['version'].split('-')[0].split('.'))+(0,)
    version_file=build/'version-info.txt'
    version_file.write_text(f"VSVersionInfo(ffi=FixedFileInfo(filevers={numeric!r},prodvers={numeric!r},mask=0x3f,flags=0,OS=0x40004,fileType=1,subtype=0,date=(0,0)),kids=[StringFileInfo([StringTable('040904B0',[StringStruct('ProductName',{spec['name']!r}),StringStruct('FileVersion',{spec['version']!r}),StringStruct('ProductVersion',{spec['version']!r})])]),VarFileInfo([VarStruct('Translation',[1033,1200])])])",encoding='utf8')
    local={p.stem for p in stage.rglob('*.py')};imports=set(local)
    for p in stage.rglob('*.py'):
        for node in ast.walk(ast.parse(p.read_text(encoding='utf8'))):
            if isinstance(node,ast.Import): imports.update(item.name for item in node.names)
            elif isinstance(node,ast.ImportFrom) and node.module: imports.add(node.module)
    command=[sys.executable,'-m','PyInstaller','--noconfirm','--onedir' if args.onedir else '--onefile','--windowed',
             '--name',spec['name'],'--distpath',str(build/'package'),'--workpath',str(build/'work'),'--specpath',str(build),
             '--version-file',str(version_file),
             '--paths',str(stage/'runtime'),'--paths',str(stage/'app'),'--paths',str(stage/'src')]
    for name in sorted(imports):
        if name.split('.')[0] in local or name.split('.')[0] in sys.stdlib_module_names:
            command+=['--hidden-import',name]
    for folder in ('data','runtime','app','src'):
        if (stage/folder).exists(): command+=['--add-data',f'{stage/folder};{folder}']
    command+=['--add-data',f'{stage/"build-manifest.json"};.']
    if (stage/'MinHook-LICENSE.txt').exists(): command+=['--add-data',f'{stage/"MinHook-LICENSE.txt"};.']
    subprocess.run(command+[str(stage/'launch.py')],check=True)
    package=build/'package'
    if spec['kind']=='recorder':
        exe=package/spec['name']/f'{spec["name"]}.exe' if args.onedir else package/f'{spec["name"]}.exe'
        smoke=package/'ui-smoke.json'
        subprocess.run([str(exe),'--ui-smoke',str(smoke)],check=True,timeout=60)
        if not json.loads(smoke.read_text())['passed']:raise ValueError('Packaged UI check failed')
        (package/'recorder-smoke-settings.json').unlink(missing_ok=True)
    if release_inputs(project)[1]!=sources:raise ValueError('Source changed during the build; discard this candidate')
    shutil.copyfile(stage/'build-manifest.json',package/'build-manifest.json')
    shutil.copyfile(build/'offline-tests.log',package/'offline-tests.log')
    shutil.copyfile(project/'CHANGELOG.md',package/'CHANGELOG.md')
    receipt=dict(schema_version=1,product=spec['name'],version=spec['version'],prerelease='-' in spec['version'],
        built_at=datetime.now(timezone.utc).isoformat(),sources=sources,python=sys.version,dependencies=dependencies,
        packaging='onedir' if args.onedir else 'onefile',workflow_tests=int(counts[0]),resource_tests=int(counts[1]),
        gameplay_acceptance=False,other_pc_acceptance=False)
    (package/'release.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf8')
    hashes={p.relative_to(package).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(package.rglob('*')) if p.is_file()}
    (package/'SHA256SUMS.txt').write_text(''.join(f'{sha}  {name}\n' for name,sha in hashes.items()),encoding='utf8')
    destination=project/'dist'/spec['version'];destination.parent.mkdir(exist_ok=True)
    package.rename(destination)
    subprocess.run(['git','-C',str(project),'tag','-a',f'v{spec["version"]}',sources[project.name]['commit'],
        '-m',f'{spec["name"]} {spec["version"]}; Engine {sources[ROOT.name]["commit"]}; SHA256SUMS '+
        hashlib.sha256((destination/'SHA256SUMS.txt').read_bytes()).hexdigest()],check=True)
    print(destination)


if __name__=='__main__': main()
