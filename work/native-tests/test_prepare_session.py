"""Offline session generation and cache selection checks; never opens a process."""
import contextlib
import copy
import io
import json
from pathlib import Path
import re
import struct
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'outputs/okatsu-prototype'))
import prepare_session as prepare

FIXTURES = Path(__file__).resolve().parent / 'fixtures'
PROFILE = json.loads((FIXTURES / 'session-profile.json').read_text())


class PreparationTests(unittest.TestCase):
    def test_generation_matches_verified_session_and_header_layout(self):
        fields, originals = prepare.boss_fields(PROFILE)
        verified = json.loads((FIXTURES / 'boss-session.json').read_text())
        self.assertEqual(fields, {key: verified[key] for key in fields})
        self.assertEqual(originals, verified['originals'])
        candidate = PROFILE['charged_candidate']
        payload = bytearray(0xB0)
        struct.pack_into('<i', payload, 0x20, 1230)
        struct.pack_into('<i', payload, 0x34, -1)
        reads = []
        def read(address, size):
            reads.append((address, size))
            self.assertEqual((address, size), (verified['charge_payload'], 0xB0))
            return bytes(payload)
        game = type('OwnedGame', (), {'bytes': staticmethod(read)})()
        with patch.object(prepare, 'inspect_banks', return_value={}), \
             patch.object(prepare, 'resolve', return_value=candidate['resolution']), \
             patch.object(prepare, 'motion_lookup', return_value=candidate['motion_resource']), \
             patch.object(prepare, 'timing_lookup', return_value=candidate['timing_resource']):
            prepare.charge_fields(game, copy.deepcopy(PROFILE), fields)
        self.assertEqual(reads, [(verified['charge_payload'], 0xB0)])
        self.assertEqual(fields, {key: verified[key] for key in fields})
        header = prepare.session_header(fields, originals)
        stub = (FIXTURES / 'boss_session.stub.h').read_text()
        declarations = lambda text: re.findall(r'^    uint64_t (\w+);$', text, re.MULTILINE)
        self.assertEqual(declarations(header), declarations(stub))
        self.assertEqual(declarations(header), list(fields))
        for name, value in fields.items():
            self.assertIn(f'0x{value:x}ULL, // {name}', header)
        self.assertIn('uint64_t originals[4];', header)
        self.assertIn('{' + ', '.join(f'0x{x:x}ULL' for x in originals) + '}', header)

    def test_valid_cached_actors_are_reprofiled_without_full_scan(self):
        game = type('Game', (), {'identity': PROFILE['session']})()
        with patch.object(prepare, 'run_profile', return_value=PROFILE) as profile, \
             patch.object(prepare, 'discover') as discover:
            result, method, reason = prepare.fresh_profile(game, PROFILE)
        self.assertIs(result, PROFILE)
        self.assertEqual(method, 'revalidated_profile')
        self.assertIsNone(reason)
        self.assertEqual(profile.call_args.args[1]['candidates'], [
            dict(object=PROFILE[who]['actor'], owner_like=PROFILE[who]['owner']) for who in ('source', 'player')])
        discover.assert_not_called()

    def test_changed_birth_discovers_fresh_without_reusing_saved_pointers(self):
        game = type('Game', (), {'identity': dict(PROFILE['session'], creation_filetime='1')})()
        discovered = dict(candidates=[])
        with patch.object(prepare, 'run_profile', return_value='new') as profile, \
             patch.object(prepare, 'discover', return_value=discovered) as discover, \
             contextlib.redirect_stderr(io.StringIO()):
            result, method, reason = prepare.fresh_profile(game, PROFILE)
        self.assertEqual((result, method), ('new', 'fresh_discovery'))
        self.assertEqual(reason, 'Saved process identity differs')
        discover.assert_called_once_with(game)
        profile.assert_called_once_with(game, discovered)


if __name__ == '__main__':
    unittest.main()
