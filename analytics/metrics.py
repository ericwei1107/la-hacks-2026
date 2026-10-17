from analytics.stats import Situations, block

CONTRACT_KEYS = ("damage_taken_by_situation", "punish_rate", "throw_break_rate", "low_block_rate", "counter_hits_taken", "counter_hits_given", "avg_adv_after_block")


def rate(num, den):
    return round(num / den, 3) if den else None


def stat_totals(human_slot, evs):
    body = block(evs, human_slot, Situations([]), None)
    return {key: body[key] for key in CONTRACT_KEYS}


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
    events = [record for record in records if record['t'] == 'event']
    totals = stat_totals(meta['human_slot'], events)
    values = {key: value for key, value in totals.items() if key != 'damage_taken_by_situation'}
    values.update({f'damage_taken_by_situation:{key}': value for key, value in totals['damage_taken_by_situation'].items()})
    for record in metrics['rounds']:
        for habit, value in record['habits'].items():
            values[f'habit_probability:{habit}'] = value['p']
            if 'mastery' in value:
                values[f'mastery:{habit}'] = value['mastery']
    values.update({f'time_to_mastery:{habit}': value for habit, value in metrics['time_to_mastery'].items()})
    winners = {record['round']: record.get('winner') for record in meta['rounds']}
    for record in records:
        if record['t'] == 'round_summary':
            winners[record['round']] = record['winner']
        elif record['t'] == 'event' and record['kind'] == 'round_end' and 'winner' in record.get('detail', {}):
            winner = record['detail']['winner']
            if winner is not None and (type(winner) is not int or winner not in (0, 1)):
                from analytics.repository import DataError
                raise DataError('Invalid round winner in round_end event')
            winners[record['round']] = winner
    decided = [winner for winner in winners.values() if winner is not None]
    if any(type(winner) is not int or winner not in (0, 1) for winner in decided):
        from analytics.repository import DataError
        raise DataError('Invalid round winner in session metadata')
    values[f"win_rate:difficulty:{meta['difficulty']}"] = rate(sum(winner == meta['human_slot'] for winner in decided), len(decided))
    return values
