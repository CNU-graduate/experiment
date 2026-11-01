"""Offline checks for threshold selection, test-label isolation and validation gating."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('threshold_runner',HERE/'run.py')
runner=importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class PipelineChecks(unittest.TestCase):
    def fixture(self,validation_yes_score=45):
        requests=[];results={};labels={}
        for phase,scores,gold in [('development',[20,40,45,90],['No','Yes','Yes','Yes']),
                                  ('validation',[20,validation_yes_score],['No','Yes'])]:
            for i,(score,label) in enumerate(zip(scores,gold)):
                case=f'{phase}{i}';key=f'{phase}:score:{case}'
                requests.append(dict(key=key,phase=phase,kind='score',case_id=case))
                results[key]=dict(status='success',value=score)
                labels[f'{phase}:{case}']=label
        return requests,results,labels

    def test_development_cutoff_and_tie_rule(self):
        threshold,_=runner.choose_threshold([20,40,45,90],['No','Yes','Yes','Yes'])
        self.assertEqual(threshold,40)
        threshold,_=runner.choose_threshold([50,50],['No','Yes'])
        self.assertEqual(threshold,50)

    def test_test_labels_and_scores_do_not_affect_fit(self):
        requests,results,labels=self.fixture()
        requests.append(dict(key='evaluation:score:target',phase='evaluation',kind='score',case_id='target'))
        labels['evaluation:target']='Yes';results['evaluation:score:target']=dict(status='success',value=99)
        with tempfile.TemporaryDirectory(prefix='threshold-isolation-') as directory:
            first=runner.fit_and_validate(results,labels,requests,Path(directory))
        labels['evaluation:target']='No';results['evaluation:score:target']['value']=1
        with tempfile.TemporaryDirectory(prefix='threshold-isolation-') as directory:
            second=runner.fit_and_validate(results,labels,requests,Path(directory))
        self.assertEqual(first,second)
        self.assertTrue(first['validation_passed'])

    def test_worse_validation_is_rejected(self):
        requests,results,labels=self.fixture()
        results['validation:score:validation0']['value']=40
        results['validation:score:validation1']['value']=70
        with tempfile.TemporaryDirectory(prefix='threshold-gate-') as directory:
            fitted=runner.fit_and_validate(results,labels,requests,Path(directory))
        self.assertFalse(fitted['validation_passed'])

    def test_evaluation_reuses_scores_for_b_and_c(self):
        requests,results,labels=self.fixture()
        for case,label,score,direct in [('n','No',30,'No'),('y','Yes',45,'No')]:
            labels[f'evaluation:{case}']=label
            for kind,value in [('score',score),('direct',direct)]:
                key=f'evaluation:{kind}:{case}'
                requests.append(dict(key=key,phase='evaluation',kind=kind,case_id=case))
                results[key]=dict(status='success',value=value)
        with tempfile.TemporaryDirectory(prefix='threshold-report-') as directory:
            path=Path(directory)
            fitted=runner.fit_and_validate(results,labels,requests,path)
            summary=runner.summarize(results,labels,requests,fitted,path,'mock')
        self.assertEqual(summary['evaluation']['B_score_50']['correct'],1)
        self.assertEqual(summary['evaluation']['C_score_tuned']['correct'],2)
        self.assertEqual(summary['B_to_C_changes'],dict(corrected=1,new_errors=0))

    def test_frozen_split_and_inference_payload(self):
        splits=json.loads((HERE/'splits_LOCAL_ONLY.json').read_text(encoding='utf-8'))
        dev={r['group'] for r in splits if r['phase']=='development'}
        val={r['group'] for r in splits if r['phase']=='validation'}
        self.assertTrue(dev.isdisjoint(val))
        for line in (HERE/'requests.jsonl').read_text(encoding='utf-8').splitlines():
            request=json.loads(line)
            payload=json.loads(request['body']['messages'][1]['content'])
            self.assertEqual(set(payload),{'examples','test'})
            self.assertEqual(payload['examples'],[])
            self.assertEqual(set(payload['test']),{'substance','purpose','commodity','JMPR','EU'})


if __name__=='__main__':
    unittest.main()
