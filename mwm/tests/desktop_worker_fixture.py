"""Private worker for UI checks: temporary settings, simulated binding, no game lifecycle."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'app'))
import web_worker

# Route every saved setting to the test directory and treat Engine as stopped.
# Controller capture is simulated by the hidden Electron host before it reaches this pipe.
# Reject lifecycle calls even if a renderer regression unexpectedly tries to enable gameplay.
web_worker.Desktop.location = lambda self: Path(sys.argv[1])
web_worker.process_matches = lambda value: False
original = web_worker.Desktop.dispatch


def dispatch(self, method, params):
    # Limit this fixture to configuration and file roundtrips.
    # A lifecycle/capture request reaching Python is a failed test, never a real side effect.
    # All allowed requests execute production validation and persistence code.
    if method == 'capture_start':
        if not getattr(self, 'fixture_capture_failed', False):
            self.fixture_capture_failed = True
            raise AssertionError('Controller listener fixture failure')
        return dict(status='Press one input')
    if method == 'test_bad_reply':
        return float('nan')
    if method in ('enable', 'disable', 'capture_poll'):
        raise ValueError('Live operation forbidden in desktop fixture')
    return original(self, method, params)


web_worker.Desktop.dispatch = dispatch
web_worker.main()
