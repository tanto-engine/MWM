"""Offline developer review; never installs imports or accesses game memory."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
os.environ.setdefault('TANTO_MOD_ROOT', str(ROOT))
sys.path.insert(0, str(Path(os.environ.get('TANTO_ENGINE_ROOT', ROOT.parent/'tanto-engine'))/'runtime'))
from catalogue import iter_moves, load_catalogue
from engine_config import atomic_json, read_json
from move_imports import read_import_manifest


def review_import(path, catalogue_path=ROOT/'data/moves.json', resources=ROOT/'data/resources', evidence=None, reviewed=False):
    # Explain what is missing before a recorded boss move can become an MWM import.
    # Compare authored import, catalogue, resource and optional reconstruction identities without loading game memory.
    # The report stays a developer review artifact; marking reviewed never installs a move or proves gameplay.
    """Check authored definitions against maintained adapters and retained evidence."""
    path = Path(path)
    report = dict(schema_version=1, kind='import_review', import_path=str(path.resolve()),
        import_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), definition_valid=False,
        executable=False, gameplay_accepted=False, issues=[], requirements=[])
    issues, requirements = report['issues'], report['requirements']
    try:
        manifest = read_import_manifest(path, catalogue_path)
        catalogue = load_catalogue(catalogue_path)
    except (KeyError, TypeError, ValueError, OSError) as error:
        issues.append('Import definition: '+str(error))
        requirements.extend(['Author a schema 1 import using an implemented adapter and supported source family.',
            'Record and review source action, motion, timing, transitions, recovery and paired roles.',
            'Add the source identity to the catalogue and supply verified resource/archive mappings.'])
        return report
    report['definition_valid'] = True
    records = {move['id']:move for move in iter_moves(catalogue)}
    profile_path = Path(resources)/(manifest['boss_id']+'.json')
    profile = read_json(profile_path, {})
    if profile.get('resource_profile_id') != manifest['resource_profile_id'] or profile.get('boss_id') != manifest['boss_id']:
        issues.append('Missing or mismatched resource profile: '+str(profile_path))
    if profile.get('build_sha256') != catalogue['supported_build_sha256']:
        issues.append('Resource profile must match the catalogue game build.')
    for role in ('actions','motion','timing'):
        asset = profile.get('assets',{}).get(role,{})
        if any(not asset.get(field) for field in ('archive','source_name','size','sha256')) or type(asset.get('entry_id')) is not int:
            issues.append('Missing archive identity, entry, size or fingerprint: '+role)
    resource_moves = {int(key,16):value for key,value in profile.get('moves',{}).items()}
    report['moves'] = []
    for move in manifest['moves']:
        identifier = move['id']
        source = records[identifier]['source']
        resource = resource_moves.get(move['key'],{})
        missing = []
        for key,field in (('key','action_id'),('motion','motion_id'),('flags','flags'),('ki_cost','ki_cost'),('recovery_frame','recovery_frame')):
            if source.get(field) is None: missing.append('reviewed source '+field)
            elif source[field] != move[key]: issues.append(identifier+': source '+field+' disagrees with import')
        if resource.get('motion_key') != move['motion'] or resource.get('timing_key') != source.get('timing_id'):
            missing.append('matching motion/timing resource identity')
        for field in ('motion_index','motion_record_offset','timing_index','timing_record_offset','timing_event_count'):
            if type(resource.get(field)) is not int or resource[field]<0: missing.append('resource '+field)
        report['moves'].append(dict(id=identifier, missing=missing))
        requirements.extend(identifier+': '+item for item in missing)
    if evidence is not None:
        evidence = Path(evidence)
        reconstruction = read_json(evidence)
        report['evidence'] = dict(path=str(evidence.resolve()),sha256=hashlib.sha256(evidence.read_bytes()).hexdigest(),reviewed=reviewed)
        if not isinstance(reconstruction,dict) or reconstruction.get('kind')!='encounter_reconstruction' or reconstruction.get('schema_version')!=1:
            issues.append('Evidence must be Recorder encounter_reconstruction schema 1; raw recordings are not import definitions.')
        elif reconstruction.get('boss_id')!=manifest['boss_id']:
            issues.append('Reviewed evidence belongs to a different boss.')
        else:
            observed={(action.get('source',{}).get('action_id'),action.get('source',{}).get('motion_id'))
                for action in reconstruction.get('actions',[]) if action.get('role')=='boss_candidate'}
            for move in manifest['moves']:
                if (move['key'],move['motion']) not in observed:
                    requirements.append(move['id']+': reviewed action/motion evidence')
        if not reviewed: requirements.append('Human review of recording identities, labels and transitions (--reviewed records this attestation).')
    else:
        requirements.append('Reviewed Recorder reconstruction evidence; add --evidence and --reviewed after review.')
    requirements.extend(['Verify installed archive bytes and native resources during engine preparation.',
        'Review player adaptation, damage ownership, recovery, voices and all paired actor roles.',
        'Run maintained offline tests, then record current-build gameplay acceptance before distribution.'])
    return report


def main(argv=None):
    # Run the offline import-review command with explicitly selected inputs.
    # Resolve optional evidence/catalogue/resource files and reject an output that would replace source definitions.
    # Write only the review report, keeping experimental recordings outside the playable product data.
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('import_path',type=Path)
    parser.add_argument('--catalogue',type=Path,default=ROOT/'data/moves.json')
    parser.add_argument('--resources',type=Path,default=ROOT/'data/resources')
    parser.add_argument('--evidence',type=Path)
    parser.add_argument('--reviewed',action='store_true',help='Attest that the supplied reconstruction was reviewed')
    parser.add_argument('--out',type=Path,required=True,help='Write a review report; never replace runtime definitions')
    args=parser.parse_args(argv)
    protected=[args.import_path,args.catalogue,*args.resources.glob('*.json')]
    if args.evidence: protected.append(args.evidence)
    if args.out.resolve() in [path.resolve() for path in protected] or args.out.resolve().is_relative_to((ROOT/'data').resolve()):
        parser.error('Choose a report destination outside product data and input files')
    try:
        report=review_import(args.import_path,args.catalogue,args.resources,args.evidence,args.reviewed)
        atomic_json(args.out,report)
    except (OSError,ValueError,KeyError,TypeError) as error:
        parser.exit(1,str(error)+'\n')
    print(f"Definition {'valid' if report['definition_valid'] else 'invalid'}; {len(report['issues'])} issues; {len(report['requirements'])} review requirements. Report: {args.out}")
    return 1 if report['issues'] else 0


if __name__=='__main__':
    raise SystemExit(main())

