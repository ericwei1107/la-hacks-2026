import copy
import json
import os
import tempfile
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ['SENTRY_DSN'] = ''

from fastapi.testclient import TestClient
from analytics.main import create_app
from analytics.metrics import stat_totals
from analytics.repository import ROOT, VALIDATORS, FileRepository


class AnalyticsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ('sessions', 'recordings', 'learning', 'eval', 'samples'):
            (self.root/name).mkdir()
        self.sid = 'test-session'
        self.meta = json.loads((ROOT/'contracts/examples/session.json').read_text())
        self.meta.update(session_id=self.sid, player='alice', started_at='2026-10-17T13:00:00Z', difficulty=3, rounds=[{'round':1,'winner':1},{'round':2,'winner':0},{'round':3,'winner':None}])
        self.meta.pop('recording', None)
        self.write_meta(self.meta)
        self.write_records([])
        self.app = create_app(self.root)
        self.client = TestClient(self.app)

    def write_meta(self, meta):
        (self.root/'sessions'/f"{meta['session_id']}.json").write_text(json.dumps(meta))

    def write_records(self, records, sid=None):
        path = self.root/'recordings'/f'{sid or self.sid}.jsonl'
        path.write_text(''.join(json.dumps(record)+'\n' for record in records))
        return path

    def write_learning(self, records):
        path = self.root/'learning'/f'{self.sid}.jsonl'
        path.write_text(''.join(json.dumps(record)+'\n' for record in records))
        return path

    def round(self, number, p=0.6, n=4, **fields):
        return {'t':'learning_round','session_id':self.sid,'round':number,'prediction_accuracy':0.5,'habits':{'low_defense':{'p':p,'n':n,**fields}}}

    def learning(self):
        response = self.client.get(f'/learning/{self.sid}')
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(list(VALIDATORS['metrics'].iter_errors(body)), [])
        return body

    def trends(self, suffix=''):
        response = self.client.get('/trends/alice/devil_jin'+suffix)
        self.assertEqual(response.status_code,200,response.text)
        return response.json()['series']

    def test_health_cors_and_scope(self):
        self.assertTrue(self.client.get('/health').json()['ok'])
        response = self.client.options('/learning/test-session',headers={'Origin':'http://localhost:5173','Access-Control-Request-Method':'GET'})
        self.assertEqual(response.headers['access-control-allow-origin'],'*')

    def test_unknown_and_empty_learning(self):
        self.assertEqual(self.client.get('/learning/unknown').status_code,404)
        body = self.learning()
        self.assertEqual(body['rounds'],[])
        self.assertEqual(body['time_to_detect'],{})
        self.assertEqual(body['time_to_mastery'],{})
        self.assertEqual(body['finetune'],{'before':None,'after':None})
        self.assertEqual(self.client.get('/trends/unknown/devil_jin').json()['series'],[])

    def test_detection_boundaries_and_mastery_regression(self):
        self.write_learning([self.round(1,p=0.599,n=10),self.round(2,p=0.8,n=3),self.round(3,p=0.6,n=4,fixed=True,mastery=0.85),self.round(4,p=0.4,n=12,fixed=False,mastery=0.4)])
        body = self.learning()
        self.assertEqual(body['time_to_detect'],{'low_defense':3})
        self.assertEqual(body['time_to_mastery'],{'low_defense':3})
        values = self.trends()[0]['values']
        self.assertEqual(values['habit_probability:low_defense'],0.4)
        self.assertEqual(values['mastery:low_defense'],0.4)
        self.assertEqual(values['time_to_mastery:low_defense'],3)

    def test_fixed_is_producer_authority(self):
        self.write_learning([self.round(2,p=0.1,n=1,fixed=True)])
        self.assertEqual(self.learning()['time_to_mastery'],{'low_defense':2})

    def test_duplicate_round_sort_unknown_fields_and_types(self):
        first = self.round(1,p=0.1)
        second = self.round(2,mastery=0.6)
        last = self.round(1,p=0.8)
        last['future']={'keep':True}
        self.write_learning([second, first, {'t':'future','garbage':True}, last])
        self.assertEqual(self.learning()['rounds'],[last,second])

    def test_truncated_tail_is_completed_on_next_request(self):
        path = self.write_learning([self.round(1,p=0.4)])
        with path.open('a') as stream:
            stream.write('{"t":"learning_round","round":')
        self.assertEqual(len(self.learning()['rounds']),1)
        self.write_learning([self.round(1,p=0.4),self.round(2,p=0.9)])
        self.assertEqual(len(self.learning()['rounds']),2)

    def test_invalid_stored_data_returns_503_and_logs(self):
        for text in ('garbage\n', '{"t":"learning_round","round":1}\n', json.dumps(self.round(1,p=2))+'\n', json.dumps({**self.round(1),'session_id':'wrong'})+'\n', json.dumps(self.round(1)).replace('0.5','NaN')+'\n'):
            (self.root/'learning'/f'{self.sid}.jsonl').write_text(text)
            with self.assertLogs('analytics.main',level='ERROR'):
                self.assertEqual(self.client.get(f'/learning/{self.sid}').status_code,503)

    def test_evaluation_creation_change_deletion_and_validation(self):
        self.assertIsNone(self.learning()['finetune']['before'])
        path = self.root/'eval'/f'{self.sid}.json'
        path.write_text(json.dumps({'before':0.4,'after':0.7}))
        self.assertEqual(self.learning()['finetune'],{'before':0.4,'after':0.7})
        path.write_text(json.dumps({'before':None,'after':0.9}))
        self.assertEqual(self.learning()['finetune']['after'],0.9)
        for bad in ({'before':-1,'after':0.8},{'before':True,'after':0.8},{'after':0.8}):
            path.write_text(json.dumps(bad))
            self.assertEqual(self.client.get(f'/learning/{self.sid}').status_code,503)
        path.unlink()
        self.assertIsNone(self.learning()['finetune']['after'])

    def test_latest_available_habit_observations(self):
        first = self.round(1,mastery=0.7)
        first['habits']['throw_break']={'p':0.8,'n':5,'mastery':0.6}
        self.write_learning([first,self.round(2,p=0.4)])
        values = self.trends()[0]['values']
        self.assertEqual(values['habit_probability:throw_break'],0.8)
        self.assertEqual(values['mastery:low_defense'],0.7)
        self.assertEqual(values['habit_probability:low_defense'],0.4)

    def test_trends_filter_nulls_and_win_rate(self):
        values = self.trends()[0]['values']
        self.assertIsNone(values['punish_rate'])
        self.assertEqual(values['win_rate:difficulty:3'],0.5)
        self.assertEqual(self.trends('?stat=low_block_rate')[0]['values'],{'low_block_rate':None})
        self.assertEqual(self.trends('?stat=unknown')[0]['values'],{})
        self.meta['rounds']=[{'round':1,'winner':None}]
        self.write_meta(self.meta)
        self.assertIsNone(self.trends()[0]['values']['win_rate:difficulty:3'])

    def test_time_order_ties_and_player_character_isolation(self):
        for sid,started,player,character in [('earlier','2026-10-17T14:00:00+02:00','alice','devil_jin'),('aaa','2026-10-17T13:00:00Z','alice','devil_jin'),('other','2026-10-17T10:00:00Z','bob','devil_jin'),('king','2026-10-17T10:00:00Z','alice','king')]:
            meta={**self.meta,'session_id':sid,'started_at':started,'player':player,'human_character':character}
            self.write_meta(meta)
            self.write_records([],sid)
        self.assertEqual([point['session_id'] for point in self.trends()],['earlier','aaa',self.sid])

    def test_sample_discovery_and_canonical_precedence(self):
        sample = self.root/'samples'/'unrelated-name.jsonl'
        sample.write_text('')
        meta={**self.meta,'player':'sample-player'}
        sample.with_suffix('.session.json').write_text(json.dumps(meta))
        self.assertEqual(len(self.trends()),1)
        self.assertEqual(self.client.get('/trends/sample-player/devil_jin').json()['series'],[])
        (self.root/'recordings'/f'{self.sid}.jsonl').unlink()
        self.assertEqual(len(self.trends()),1)
        (self.root/'sessions'/f'{self.sid}.json').unlink()
        self.assertEqual(self.client.get('/trends/sample-player/devil_jin').status_code,200)
        self.assertEqual(self.client.get('/trends/sample-player/devil_jin').json()['series'][0]['session_id'],self.sid)

    def test_metadata_and_recording_refresh_and_cache_reuse(self):
        import analytics.metrics
        with patch('analytics.metrics.trend_values',wraps=analytics.metrics.trend_values) as reducer:
            self.trends()
            self.trends()
            self.assertEqual(reducer.call_count,1)
            self.write_records([{'t':'event','session_id':self.sid,'round':1,'frame':10,'kind':'hit','actor':1,'target':0,'damage':12,'situation':'low_defense'}])
            self.assertEqual(self.trends()[0]['values']['damage_taken_by_situation:low_defense'],12)
            self.assertEqual(reducer.call_count,2)
            self.meta['difficulty']=5
            self.write_meta(self.meta)
            self.assertIn('win_rate:difficulty:5',self.trends()[0]['values'])
            self.assertEqual(reducer.call_count,3)

    def test_required_recording_only_needed_for_trends(self):
        (self.root/'recordings'/f'{self.sid}.jsonl').unlink()
        self.learning()
        self.assertEqual(self.client.get('/trends/alice/devil_jin').status_code,503)

    def test_relative_recording_reference_and_ignored_record_type(self):
        self.meta['recording']='tools/mock/tests/fixtures/two-rounds.jsonl'
        self.meta['session_id']='fixture-two-rounds'
        (self.root/'sessions'/f'{self.sid}.json').unlink()
        self.write_meta(self.meta)
        self.assertEqual(self.client.get('/trends/alice/devil_jin').status_code,200)

    def test_record_and_metadata_validation(self):
        self.write_records([{'t':'event','session_id':self.sid,'round':1,'frame':0,'kind':'not-a-kind'}])
        self.assertEqual(self.client.get('/trends/alice/devil_jin').status_code,503)
        self.write_records([])
        self.meta['started_at']='yesterday'
        self.write_meta(self.meta)
        self.assertEqual(self.client.get(f'/learning/{self.sid}').status_code,503)

    def test_learning_changes_and_removal_refresh_trends(self):
        path = self.write_learning([self.round(1,p=0.7,mastery=0.6)])
        self.assertEqual(self.trends()[0]['values']['mastery:low_defense'],0.6)
        self.write_learning([self.round(1,p=0.8,mastery=0.9,fixed=True)])
        values = self.trends()[0]['values']
        self.assertEqual(values['mastery:low_defense'],0.9)
        self.assertEqual(values['time_to_mastery:low_defense'],1)
        path.unlink()
        self.assertNotIn('mastery:low_defense',self.trends()[0]['values'])

    def test_truncated_recording_and_unknown_fields(self):
        path=self.write_records([{'t':'future_kind','round':999,'anything':True},{'t':'event','session_id':self.sid,'round':1,'frame':1,'kind':'counter_hit','actor':1,'target':0,'damage':4,'future':True}])
        with path.open('a') as stream:
            stream.write('{"t":"event"')
        self.assertEqual(self.trends()[0]['values']['counter_hits_taken'],1)
        self.assertEqual(self.trends()[0]['values']['win_rate:difficulty:3'],0.5)

    def test_round_results_from_recording_and_invalid_winner(self):
        self.meta['rounds']=[]
        self.write_meta(self.meta)
        event={'t':'event','session_id':self.sid,'round':1,'frame':10,'kind':'round_end','detail':{'winner':0}}
        self.write_records([event])
        self.assertEqual(self.trends()[0]['values']['win_rate:difficulty:3'],1)
        event['detail']['winner']=2
        self.write_records([event])
        self.assertEqual(self.client.get('/trends/alice/devil_jin').status_code,503)

    def test_generated_demo(self):
        subprocess.run([sys.executable,str(ROOT/'tools/mock/synth.py'),'--out',str(self.root)],check=True,capture_output=True,text=True)
        sid='2026-10-17T13-05-00_synth_djin_vs_kaz'
        body=self.client.get(f'/learning/{sid}').json()
        self.assertEqual(list(VALIDATORS['metrics'].iter_errors(body)),[])
        self.assertEqual(body['time_to_detect']['low_defense'],1)
        self.assertEqual(body['time_to_mastery']['low_defense'],3)
        self.assertEqual([row['prediction_accuracy'] for row in body['rounds']],[0.41,0.58,0.71])
        values=self.client.get('/trends/synth/devil_jin').json()['series'][0]['values']
        self.assertEqual(values['mastery:low_defense'],0.88)
        self.assertEqual(values['habit_probability:low_defense'],0.47)
        self.assertEqual(values['win_rate:difficulty:3'],0.333)


class ReducerTest(unittest.TestCase):
    def event(self,frame,kind,**fields):
        return {'t':'event','session_id':'test','round':1,'frame':frame,'kind':kind,**fields}

    def test_hand_calculated_event_totals(self):
        events=[self.event(10,'block',actor=1,target=0,hit_level='low',frame_advantage=-12),self.event(25,'hit',actor=0,target=1,damage=10),self.event(50,'hit',actor=1,target=0,hit_level='low',damage=12,situation='low_defense'),self.event(70,'counter_hit',actor=1,target=0,damage=8),self.event(90,'counter_hit',actor=0,target=1,damage=6),self.event(100,'throw',actor=1,target=0,damage=35,situation='throw_break'),self.event(112,'throw',actor=1,target=0,damage=0),self.event(120,'throw_break',actor=0,target=1)]
        body=stat_totals(0,events)
        self.assertEqual(body,{'damage_taken_by_situation':{'low_defense':12,'neutral':8,'throw_break':35},'punish_rate':1.0,'throw_break_rate':0.5,'low_block_rate':0.5,'counter_hits_taken':1,'counter_hits_given':1,'avg_adv_after_block':12.0})
        self.assertEqual(stat_totals(1,[self.event(10,'block',actor=0,target=1,frame_advantage=-6)])['avg_adv_after_block'],6.0)

    def test_punish_allowance_and_round_boundary(self):
        opportunity=self.event(10,'block',actor=1,target=0,frame_advantage=-12)
        self.assertEqual(stat_totals(0,[opportunity,self.event(32,'hit',actor=0,target=1)])['punish_rate'],1)
        self.assertEqual(stat_totals(0,[opportunity,self.event(33,'hit',actor=0,target=1)])['punish_rate'],0)
        hit=self.event(15,'hit',actor=0,target=1)
        hit['round']=2
        self.assertEqual(stat_totals(0,[opportunity,hit])['punish_rate'],0)


if __name__=='__main__':
    unittest.main()
