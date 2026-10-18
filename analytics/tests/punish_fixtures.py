"""Recorded recovery evidence for reducer regressions (no timing tolerance)."""
import copy
import json
from analytics.repository import ROOT


def timed(opp, human=0, human_free=None):
    read = opp['frame'] + 1
    human_free = opp['frame'] + 2 if human_free is None else human_free
    bot_free = human_free - opp['frame_advantage']
    opp.setdefault('move_id', 42)
    opp['detail'] = {'read_frame': read, 'attacker_total': bot_free - read + 1,
                     'attacker_frame': 1, 'defender_total': human_free - read + 1,
                     'defender_frame': 1, 'string_continued': False}
    base = json.loads((ROOT / 'contracts/examples/gamestate.json').read_text())
    states = []
    for frame in range(read, bot_free + 1):
        state = copy.deepcopy(base)
        state.update(session_id=opp['session_id'], round=opp['round'], frame=frame, human_slot=human)
        for slot, free in ((human, human_free), (1-human, bot_free)):
            state['players'][slot].update(move_id=opp['move_id'] if slot != human else 99,
                frame_in_move=frame-read+1, hit_level='mid' if slot != human else 'none',
                frames_until_actionable=max(0, free-frame), free_movement=frame >= free)
        states.append(state)
    return [opp, *states]
