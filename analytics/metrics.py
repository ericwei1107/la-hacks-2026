from analytics.stats import Situations, block, compute, winners
from analytics.observability import traced

CONTRACT_KEYS = ("damage_taken_by_situation", "punish_rate", "throw_break_rate", "low_block_rate", "counter_hits_taken", "counter_hits_given", "avg_adv_after_block")


def rate(num, den):
    return round(num / den, 3) if den else None


def stat_totals(human_slot, evs):
    body = block(evs, human_slot, Situations([]), None)
    return {key: body[key] for key in CONTRACT_KEYS}


@traced('learning.derive')
def learning_metrics(sid, rounds, evaluation):
    detect, mastery = {}, {}
    for record in rounds:
        for habit, value in record['habits'].items():
            if value['n'] >= 4 and value['p'] >= 0.6:
                detect.setdefault(habit, record['round'])
            if value.get('fixed') is True:
                mastery.setdefault(habit, record['round'])
    return {'session_id': sid, 'rounds': rounds, 'time_to_detect': detect, 'time_to_mastery': mastery, 'finetune': evaluation}


def trend_values(meta, records, metrics):
    totals = compute(meta['session_id'], meta, records)['totals']
    values = {key: value for key, value in totals.items() if key not in ('damage_taken_by_situation', 'throw_breaks_by_type')}
    values.update({f'throw_breaks_by_type:{key}': value for key, value in totals['throw_breaks_by_type'].items()})
    values.update({f'damage_taken_by_situation:{key}': value for key, value in totals['damage_taken_by_situation'].items()})
    for record in metrics['rounds']:
        for habit, value in record['habits'].items():
            values[f'habit_probability:{habit}'] = value['p']
            if 'mastery' in value:
                values[f'mastery:{habit}'] = value['mastery']
    values.update({f'time_to_mastery:{habit}': value for habit, value in metrics['time_to_mastery'].items()})
    decided = [winner for winner in winners(records, meta).values() if winner is not None]
    values[f"win_rate:difficulty:{meta['difficulty']}"] = rate(sum(winner == meta['human_slot'] for winner in decided), len(decided))
    return values
