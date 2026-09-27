"""A product owns its data and writable state; the engine owns implementation."""
import os
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
MOD_ROOT = Path(os.environ.get('TANTO_MOD_ROOT', ENGINE_ROOT if (ENGINE_ROOT/'data/mod.json').is_file()
                              else ENGINE_ROOT.parent/'MWM')).resolve()
DATA = MOD_ROOT/'data'
