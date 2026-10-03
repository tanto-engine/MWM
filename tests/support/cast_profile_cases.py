"""Keep shipped timing quotas synchronized with the complete import catalogue."""
import runpy
import unittest
from pathlib import Path


class CastProfiles(unittest.TestCase):
    def test_profiles_match_all_shipped_sources(self):
        root = Path(__file__).resolve().parents[2]
        generator = runpy.run_path(str(root / 'tools/generate_cast_profiles.py'))
        self.assertEqual(generator['DESTINATION'].read_text(encoding='utf-8'), generator['generate'](),
                         'Run tools/generate_cast_profiles.py after changing imported source phases')
