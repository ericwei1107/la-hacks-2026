from analytics.evidence import METRIC_ORDER

RULE_VERSION = 1
MIN_OPPORTUNITIES = 5
ACTIONS = {
    'low_defense': 'Review these lows and practice recognizing low/mid choices; avoid crouching continuously.',
    'throw_defense': 'Review these throws and practice the appropriate break against the recorded throw.',
    'punish_conversion': 'Review these unsafe blocks and verify an appropriate punish with the character data.',
}


def select(metrics, override=None, punish_validated=False):
    if override is not None and override not in METRIC_ORDER:
        raise ValueError('Unknown focus; choose low_defense, throw_defense or punish_conversion')
    eligible = [key for key in METRIC_ORDER if metrics[key]['state'] == 'observed'
                and metrics[key]['opportunities'] >= MIN_OPPORTUNITIES and metrics[key]['failures']
                and (key != 'punish_conversion' or punish_validated)]
    eligible.sort(key=lambda key: (-metrics[key]['failures'], -metrics[key]['failures'] / metrics[key]['opportunities'], METRIC_ORDER.index(key)))
    chosen = eligible[0] if eligible else None
    mode = 'automatic'
    if override is not None:
        if metrics[override]['state'] in ('invalid', 'no_opportunities'):
            raise ValueError('Selected focus has no usable observed opportunities')
        if override == 'punish_conversion' and not punish_validated:
            raise ValueError('Punish focus awaits owner mechanical/advice validation')
        chosen, mode = override, 'manual'
    if chosen is None:
        reason = 'No qualifying weakness observed' if any(m['opportunities'] >= MIN_OPPORTUNITIES and m['state'] == 'observed' for m in metrics.values()) else 'More observations needed'
        return {'rule_version': RULE_VERSION, 'mode': mode, 'metric': None, 'reason': reason, 'action': None}
    metric = metrics[chosen]
    return {'rule_version': RULE_VERSION, 'mode': mode, 'metric': chosen,
            'reason': f"{metric['successes']}/{metric['opportunities']} successful observed opportunities; {metric['failures']} failures",
            'action': ACTIONS[chosen], 'action_status': 'draft_awaiting_Garrett_review',
            'state': metric['state'], 'population': 'completed_rounds'}
