import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import Store, Conflict, validate_analysis


class ReviewWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'review.sqlite')
        self.case = next(c for c in self.store.cases() if c['year'] == '2025')

    def tearDown(self):
        self.temp.cleanup()

    def body(self, **kwargs):
        return dict(status='completed', label='Yes', reviewer='테스트 검토자', notes='원문 확인',
                    confirmed=True, revision=0, **kwargs)

    def test_real_data_and_no_target_answer_leak(self):
        self.assertEqual(len(self.store.cases()), 490)
        c = self.store.detail(self.case['id'])
        self.assertNotIn('EFSA', c)
        self.assertNotIn('efsa_comments', c)
        self.assertEqual(c['status'], 'pending')

    def test_review_requirements_and_conflicting_tab(self):
        for change in ({'reviewer': ''}, {'label': 'Unknown'}, {'confirmed': False}):
            b = self.body(); b.update(change)
            with self.assertRaises(ValueError):
                self.store.save_review(self.case['id'], b)
        saved = self.store.save_review(self.case['id'], self.body())
        self.assertEqual(saved['status'], 'completed')
        self.assertEqual(saved['revision'], 1)
        with self.assertRaises(Conflict):
            self.store.save_review(self.case['id'], self.body())
        self.assertEqual(len(self.store.detail(self.case['id'])['history']), 1)

    def test_rerun_preserves_expert_decision_and_persists(self):
        saved = self.store.save_review(self.case['id'], self.body())
        with patch('server.urlopen', side_effect=AssertionError('No paid calls in preview')):
            c = self.store.analyze(self.case['id'], {'strategy': 'E2'})
        self.assertEqual(c['review'], saved['review'])
        self.assertEqual(c['status'], 'completed')
        self.assertEqual(c['revision'], 1)
        a = c['analyses'][0]
        self.assertEqual(a['mode'], 'preview')
        self.assertEqual(a['label'], 'Unknown')
        self.assertEqual(len(a['examples']), 4)
        self.assertTrue(all(int(e['year']) == 2024 for e in a['examples']))
        self.assertEqual([e['EFSA'] for e in a['examples']].count('Yes'), 2)
        self.assertNotIn('EFSA', a['input_snapshot'])
        reloaded = Store(self.store.path).detail(self.case['id'])
        self.assertEqual(reloaded['review'], saved['review'])
        self.assertEqual(len(reloaded['analyses']), 1)

    def test_missing_year_rejected_and_similarity_uses_past(self):
        c2018 = next(c for c in self.store.cases() if c['year'] == '2018')
        with self.assertRaises(ValueError):
            self.store.analyze(c2018['id'], {'strategy': 'E2'})
        result = self.store.analyze(self.case['id'], {'strategy': 'E5'})
        self.assertTrue(all(int(e['year']) == 2024 for e in result['analyses'][0]['examples']))

    def test_quote_substring_checks(self):
        a = validate_analysis({'label':'No', 'summary':'확인 필요', 'uncertainties':[],
            'checks':[{'item':'성분','finding':'차이','jmpr_quote':'NOT PRESENT', 'eu_quote':self.case['EU']}]}, self.case)
        self.assertFalse(a['checks'][0]['jmpr_verified'])
        self.assertTrue(a['checks'][0]['eu_verified'])

    def test_manual_case_and_hold(self):
        c = self.store.create({'substance':'직접 등록 <test>', 'year':2025, 'purpose':'Enforcement',
                              'commodity':'Plant products', 'JMPR':'A', 'EU':'B', 'source_url':'https://example.org'})
        with self.assertRaises(ValueError):
            self.store.save_review(c['id'], {'status':'hold', 'revision':0, 'notes':''})
        c = self.store.save_review(c['id'], {'status':'hold', 'revision':0, 'notes':'대사산물 자료 추가 확인'})
        self.assertEqual(c['status'], 'hold')
        self.assertFalse(c['review']['confirmed'])
        self.assertEqual(len(c['history']), 1)

    def test_foreign_analysis_cannot_be_attached(self):
        other=next(c for c in self.store.cases() if c['id']!=self.case['id'])
        a=self.store.analyze(other['id'], {'strategy':'E0'})['analyses'][0]
        b=self.body();b['analysis_id']=a['analysis_id']
        with self.assertRaises(ValueError):
            self.store.save_review(self.case['id'],b)


if __name__ == '__main__':
    unittest.main()
