"""Sword configuration UI and developer review, using disposable files only."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
MOD=ROOT/'mwm'
sys.path[:0]=[str(MOD),str(MOD/'app'),str(ROOT/'runtime')]
from review_import import review_import


class SwordImportReviewTests(unittest.TestCase):
    def test_valid_manifest_report_never_promotes_execution_or_gameplay(self):
        # Review a valid authored import through the offline helper.
        # Inspect its structural review result and explicit execution/gameplay flags.
        # Passing definition checks must not install the move or fabricate a gameplay acceptance receipt.
        report=review_import(MOD/'data/imports/okatsu.json')
        self.assertTrue(report['definition_valid']);self.assertFalse(report['executable']);self.assertFalse(report['gameplay_accepted'])
        self.assertFalse(report['issues']);self.assertTrue(report['requirements'])

    def test_raw_recording_and_unknown_source_need_authored_adapter(self):
        # Present evidence without a supported authored import/source adaptation.
        # Check the helper's missing-requirement report instead of accepting the recording as implementation.
        # New boss data must still pass explicit developer review and adapter work.
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'raw.json';path.write_text(json.dumps(dict(kind='encounter_reconstruction',schema_version=1,boss_id='unreviewed',actions=[])))
            report=review_import(path)
            self.assertFalse(report['definition_valid']);self.assertTrue(report['issues']);self.assertFalse(report['executable'])
            self.assertTrue(any('adapter' in requirement for requirement in report['requirements']))

    def test_missing_resources_and_mismatched_evidence_are_reported(self):
        # Review an import with missing package mappings or conflicting reconstruction identities.
        # Inspect the concrete resource/evidence issues reported to the developer.
        # A matching move name alone cannot replace source-byte and resource-identity agreement.
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'reconstruction.json';path.write_text(json.dumps(dict(kind='encounter_reconstruction',schema_version=1,boss_id='maria',actions=[])))
            report=review_import(MOD/'data/imports/okatsu.json',resources=Path(td),evidence=path,reviewed=True)
            self.assertTrue(any('resource profile' in issue for issue in report['issues']))
            self.assertTrue(any('different boss' in issue for issue in report['issues']))
            self.assertFalse(report['executable'])
