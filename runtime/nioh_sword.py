"""Recorded signatures for the exact-build Nioh 1 sword backend."""
SUPPORTED_SOURCE_FLAGS = 0x184C0000
GRAB_ATTEMPT_FLAGS = 0x594C0000
PAIRED_ATTACKER_FLAGS = 0x8078000000
PLAYER_REPLACEMENT_FLAGS = 0x194C0000
PLAYER_PAIRED_FLAGS = 0x8038000000
PLAYER_TEMPLATES = {0xCF5: (4300, 46, 38), 0xCF6: (4310, 46, 29), 0xCF7: (4320, 44, 33),
                    0xCB7: (3300, 40, 58), 0xC7A: (2300, 42, 46)}
STANCE_OPENERS = {'low': 0xCF5, 'mid': 0xC7A, 'high': 0xCB7}

# Grounded trial families matched to full recorded payloads and installed assets.
# Keep these signatures exact: Tachibana's positive-recovery 594C action is not
# Okatsu's negative-recovery grab despite sharing the flags word.
RECORDED_GROUNDED = (
    (0xC5B,1030,0x10018480000,30,-1),
    (0xC5C,1031,0x10018480000,26,-1),
    (0xC58,1022,0x10018480000,28,-1),
    (0xC71,1030,0x10018480000,34,-1),
    (0xC72,1031,0x10018480000,32,-1),
    (0xC6E,1022,0x10018480000,36,-1),
    (0xC7A,1051,0x10018480000,28,-1),
    (0xC78,1051,0x10018480000,26,-1),
    (0xC6C,1020,0x10018480000,40,-1),
    (0xC6D,1021,0x10018480000,38,-1),

    (0xD30,2000,0x184C0000,46,45),(0xD31,2010,0x184C0000,46,30),
    (0xD32,2020,0x184C0000,46,35),(0xD33,2030,0x184C0000,42,-1),
    (0xC6E,1010,0x19400000,10,-1),(0xC6F,1011,0x19400000,6,-1),
    (0xD8D,5011,0x594C0000,27,120),(0xC6A,1130,0x40019480000,9,-1),
    (0xC80,1000,0x184C0000,31,36),(0xC81,1001,0x184C0000,23,36),
    (0xC82,1002,0x184C0000,13,36),(0xC83,1010,0x184C0000,15,36),
    (0xC84,1011,0x184C0000,13,36),(0xC85,1020,0x184C0000,17,52),
    (0xC86,1021,0x184C0000,15,52),(0xC89,1030,0x184C0000,17,70),
    (0xC8A,1030,0x184C0000,17,70),
)


def is_recorded_grounded(move):
    # Reuse William's input/recovery adapter only for researched trial phases.
    # Exact motion, family, row count and recovery distinguish reused boss action numbers.
    # Native preparation additionally checks the complete archived payload prefix.
    return move.get('adapter_kind') in (2,4) and tuple(move.get(k) for k in
        ('key','motion','flags','transition_count','recovery_frame')) in RECORDED_GROUNDED


def is_ishida_sword(move):
    return move.get('flags') == 0x10018480000 and is_recorded_grounded(move)


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
