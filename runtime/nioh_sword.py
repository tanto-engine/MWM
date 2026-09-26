"""Recorded signatures for the exact-build Nioh 1 sword backend."""
SUPPORTED_SOURCE_FLAGS = 0x184C0000
GRAB_ATTEMPT_FLAGS = 0x594C0000
PAIRED_ATTACKER_FLAGS = 0x8078000000
PLAYER_REPLACEMENT_FLAGS = 0x194C0000
PLAYER_PAIRED_FLAGS = 0x8038000000
PLAYER_TEMPLATES = {0xCF5: (4300, 46, 38), 0xCF6: (4310, 46, 29), 0xCF7: (4320, 44, 33),
                    0xCB7: (3300, 40, 58), 0xC7A: (2300, 42, 46)}
STANCE_OPENERS = {'low': 0xCF5, 'mid': 0xC7A, 'high': 0xCB7}


def is_airborne_sword(move):
    # Admit the recorded Flying Swallow and somersault graphs.
    # Bound zero-flag airborne imports by exact source identity and adapter role.
    # Grounded sword adaptation is used only after the landing action begins.
    return (move.get('key'),move.get('motion'),move.get('flags'),move.get('adapter_kind')) in (
        (0xC71,1050,0,2),(0xC71,1050,0,5),(0xC72,5000,0,4),(0xC73,5001,0,4),(0xC74,5002,0x1BCE0000,4),
        (0xC81,1050,0,2),(0xC82,5050,0,4),(0xC83,5051,0x1BCE0000,4))


def is_izuna_bridge(move):
    # Admit only the recorded airborne contact bridge, not an arbitrary zero-flag action.
    # Match its action, motion and continuation adapter together.
    # Its native condition22 remains the sole entry to the paired attacker.
    return (move.get('key'),move.get('motion'),move.get('flags'),move.get('adapter_kind')) == (0xC7A,1050,0,4)


NATIVE_SKILLS = {'tiger_sprint': (0xFAA,5090,21,0x40017C00000),
                 'dodge_attack': (0xBC8,-1,18,0), 'heavy_attack': (0xC7A,2300,42,0x8000000594C0000)}
