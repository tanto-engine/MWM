# Private engine policy. Never accepted from a public moveset.
from nioh_sword import NATIVE_SKILLS
LAUNCH_PROFILES = [dict(resistance_below=75,weight_scale=.75,vertical_impulse=14),
                   dict(resistance_below=200,weight_scale=.45,vertical_impulse=17)]
TRACKING_RATES = dict(izuna=720,somersault=720,flying_swallow=540)
AIR_JUGGLE_BOOST = 2
FROST_MILLISECONDS, FROST_STARTUP_SPEED = 0, 8
KI_PULSE = dict(percent=40, fill_frames=25, hold_frames=24)


def validate_move_policy(value, identifiers):
    # Check developer-authored Ki Pulse settings before they reach imported moves.
    # Accept only implemented move IDs and the bounded percent, fill-frame and hold-frame fields.
    # Reject extra fields and booleans posing as integers; public presets cannot author this policy.
    if not isinstance(value,dict) or set(value)!={'schema_version','moves'} or type(value['schema_version']) is not int or value['schema_version']!=1 or not isinstance(value['moves'],dict):
        raise ValueError('Move policy requires schema_version 1 and moves')
    for identifier, policy in value['moves'].items():
        if identifier not in identifiers or not isinstance(policy,dict) or set(policy)!={'ki_pulse'}:
            raise ValueError('Developer move policy requires an implemented move and ki_pulse')
        pulse=policy['ki_pulse']
        if not isinstance(pulse,dict) or set(pulse)!=set(KI_PULSE):
            raise ValueError('Ki Pulse requires percent, fill_frames and hold_frames')
        for key,lower,upper in (('percent',0,100),('fill_frames',1,120),('hold_frames',0,120)):
            if type(pulse[key]) is not int or not lower<=pulse[key]<=upper:
                raise ValueError('Ki Pulse '+key+' is outside developer policy bounds')
    return value


def validate_tracking_rates(rates):
    # Turn speed is expressed in degrees per real gameplay second for each move graph.
    # Zero disables a graph's assistance; native pauses never accumulate a catch-up turn.
    # Fixed keys keep the saved preset and native array in the same explicit order.
    if not isinstance(rates,dict) or set(rates)!=set(TRACKING_RATES) or any(type(v) not in (int,float) or not 0<=v<=720 for v in rates.values()):
        raise ValueError('Tracking rates require Izuna, somersault and Flying Swallow values from 0 to 720 degrees/second')


def validate_launch_profiles(profiles, boost):
    # Ordered resistance bands distinguish the two observed humans without inventing enemy IDs.
    # Their weight and upward impulse are separate native quantities.
    # Unmatched humans and nonhumans retain the existing launcher baseline.
    if not isinstance(profiles,list) or len(profiles)!=2:
        raise ValueError('Launcher requires two ascending human resistance bands')
    previous=0
    for profile in profiles:
        if not isinstance(profile,dict) or set(profile)!={'resistance_below','weight_scale','vertical_impulse'}:
            raise ValueError('Invalid launch profile fields')
        limit,weight,impulse=(profile[k] for k in ('resistance_below','weight_scale','vertical_impulse'))
        if type(limit) is not int or not previous<limit<=10000 or type(weight) not in (int,float) or not 0<weight<=1 or type(impulse) not in (int,float) or not 0<impulse<=20:
            raise ValueError('Invalid launch profile bounds')
        previous=limit
    if type(boost) not in (int,float) or not 0<=boost<=5:
        raise ValueError('Airborne hit lift must be between 0 and 5')
