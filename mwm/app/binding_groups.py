"""Portable product-owned binding groups; Engine still validates the merged moveset."""
from copy import deepcopy
from engine_config import validate_preset
from trainer import remap_preset

GROUPS = {
    'chord': ('Custom chord', ('tap_move', 'hold_move', 'modifier_mask', 'trigger_mask', 'hold_seconds', 'chord_stance')),
    'stances': ('Stance overrides', ('low_heavy', 'stance_holds')),
    'skills': ('Native overrides', ('skill_bindings',)),
    'frost': ('Frost Moon', ('frost_moon',)),
}


def describe_groups():
    # Give the editor one authoritative list of reusable groups.
    # Labels describe player controls; IDs identify the portable file contract.
    # File operations never accept renderer-supplied field lists.
    return [dict(id=key, label=value[0]) for key, value in GROUPS.items()]


def group_fields(group):
    # Restrict an operation to a known group before reading or writing a file.
    # Each group owns disjoint preset fields, preventing hidden changes to other bindings.
    # Speed, profile name and controller selection are deliberately outside these groups.
    if not isinstance(group, str) or group not in GROUPS:
        raise ValueError('Choose a supported binding group')
    return GROUPS[group][1]


def export_group(preset, calibration, group):
    # Copy only this group's settings from a validated draft.
    # Chord files include their source controller map so button meaning survives remapping.
    # Independent dictionaries prevent later edits from changing the exported document.
    fields = group_fields(group)
    preset = validate_preset(preset)
    value = dict(schema_version=1, kind='mwm_binding_group', weapon='sword', group=group,
                 bindings={field: deepcopy(preset[field]) for field in fields})
    if group == 'chord' or group == 'skills' and any('input' in row for row in preset['skill_bindings']):
        value['controller'] = {key: deepcopy(calibration[key]) for key in ('device', 'button_map') if key in calibration}
    return value


def import_group(document, preset, calibration, group):
    # Replace exactly one group in a copy, retaining all unrelated pending choices.
    # Reject mismatched files and unexpected fields rather than silently widening their scope.
    # Validate the merged result; cross-group prerequisites remain Engine's authority.
    fields = group_fields(group)
    keys = {'schema_version', 'kind', 'weapon', 'group', 'bindings'}
    allowed = [keys | {'controller'}] if group == 'chord' else [keys, keys | {'controller'}] if group == 'skills' else [keys]
    if not isinstance(document, dict) or set(document) not in allowed or type(document.get('schema_version')) is not int or document['schema_version'] != 1:
        raise ValueError('Unsupported binding-group file')
    if document['kind'] != 'mwm_binding_group' or document['weapon'] != 'sword' or document['group'] != group:
        raise ValueError('This file does not contain the selected binding group')
    if not isinstance(document['bindings'], dict) or set(document['bindings']) != set(fields):
        raise ValueError('Binding file contains missing or unrelated settings')
    result = deepcopy(preset)
    result.update(deepcopy(document['bindings']))
    if group == 'chord' or group == 'skills' and 'controller' in document:
        controller = document['controller']
        if (not isinstance(controller, dict) or not isinstance(controller.get('device'), dict)
                or 'backend' not in controller['device'] or set(controller) - {'device', 'button_map'}):
            raise ValueError('Chord file requires its source controller mapping')
        return remap_preset(result, controller, calibration, top_level=group == 'chord')
    if group == 'skills' and any('input' in row for row in result['skill_bindings']):
        raise ValueError('Custom input group requires its source controller mapping')
    return validate_preset(result)
