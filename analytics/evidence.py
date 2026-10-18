from analytics.stats import opportunities

DEFINITION_VERSION = 2
METRIC_ORDER = ('low_defense', 'throw_defense', 'punish_conversion')
LABELS = {'low_defense': 'Low defense', 'throw_defense': 'Throw defense', 'punish_conversion': 'Estimated punish conversion'}


def reference(sid, digest, line, record):
    return {'session_id': sid, 'source': 'recording', 'sha256': digest, 'line': line,
            'round': record['round'], 'frame': record.get('frame')}


def analyze(entries, human, sid, digest, invalid_source=False):
    events = [record for line, record in entries if record.get('t') == 'event']
    refs = {id(record): reference(sid, digest, line, record) for line, record in entries}
    selected = opportunities(events, human, [record for line, record in entries])
    paired = {}
    orphans = []
    throws = selected['throw_defense']
    for broken in sorted(selected['breaks'], key=lambda e: (e['round'], e['frame'])):
        candidates = [i for i, thrown in enumerate(throws) if i not in paired and thrown['round'] == broken['round']
                      and thrown['frame'] <= broken['frame'] and refs[id(thrown)]['line'] < refs[id(broken)]['line']]
        if candidates:
            paired[max(candidates, key=lambda i: (throws[i]['frame'], i))] = broken
        else:
            orphans.append(refs[id(broken)])
    matches = {'low_defense': {i: event for i, event in enumerate(selected['low_defense']) if event['kind'] == 'block'},
               'throw_defense': paired, 'punish_conversion': selected['punish_matches']}
    output = {}
    for key in METRIC_ORDER:
        population = selected[key]
        successes = len(selected['breaks']) if key == 'throw_defense' else len(matches[key])
        total = len(population)
        anomalies = []
        if key == 'punish_conversion' and selected['punish_uncertain']:
            anomalies.append({'kind': 'uncertain_punish_timing', 'count': len(selected['punish_uncertain']),
                              'evidence': [refs[id(event)] for event, reason in selected['punish_uncertain'][:3]]})
        if key == 'throw_defense' and orphans:
            anomalies.append({'kind': 'orphan_throw_break', 'count': len(orphans), 'evidence': orphans[:3]})
        if successes > total:
            anomalies.append({'kind': 'successes_exceed_opportunities'})
        if invalid_source:
            anomalies.append({'kind': 'invalid_recording_lines'})
        state = 'invalid' if anomalies else 'no_opportunities' if not total else 'early_signal' if total < 5 else 'observed'
        evidence = [{'opportunity': refs[id(event)], 'outcome': 'success' if i in matches[key] else 'failure',
                     'response': refs[id(matches[key][i])] if i in matches[key] else None}
                    for i, event in enumerate(population)]
        output[key] = {'label': LABELS[key], 'definition_version': DEFINITION_VERSION,
                       'successes': successes, 'opportunities': total,
                       'failures': total - successes if successes <= total else None,
                       'value': round(successes / total, 3) if total and not anomalies else None,
                       'state': state, 'estimated': key == 'punish_conversion',
                       'anomalies': anomalies, 'evidence': evidence}
    return output
