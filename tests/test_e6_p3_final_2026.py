import json
from collections import Counter
import pytest
from residue_experiment import e6_p3_final_2026 as exp
from residue_experiment.instruction_repeats import read_csv


def test_dry_run_all_86_frozen_prompts_no_target_answers(tmp_path,monkeypatch):
    monkeypatch.setattr('residue_experiment.runner.Provider',lambda *a,**k:pytest.fail('API client'))
    out=tmp_path/'check'
    info=exp.execute(out)
    assert info['cases']==516 and info['calls']==0 and info['runs']==6
    plan=json.loads((out/'plan.json').read_text())
    assert plan['system_prompts']=={'E6':exp.SYSTEM,'P3':exp.P3}
    for c in ('E6','P3'):
        for n in (1,2,3):
            folder=out/c/'dry-run'/f'round-{n:02d}'
            rows=read_csv(folder/'predictions.csv')
            assert len({r['id'] for r in rows})==86
            for line in (folder/'prompts.jsonl').read_text(encoding='utf-8-sig').splitlines():
                p=json.loads(json.loads(line)['prompt'])
                assert set(p['test'])==set(exp.final.FIELDS)
                assert len(p['examples'])==(4 if c=='E6' else 0)


def test_fake_live_both_conditions_resume_and_analyze(tmp_path,monkeypatch):
    calls=[]
    class Fake:
        def __init__(self,provider,model,config,*,system_prompt):
            self.condition=config['conditions'][0]
            assert system_prompt==exp.PROMPTS[self.condition]
        def call(self,prompt):
            calls.append(self.condition)
            return 'Yes',{},'fake'
    monkeypatch.setattr('residue_experiment.runner.Provider',Fake)
    monkeypatch.setenv('OPENROUTER_API_KEY','fake-for-mocked-client')
    out=tmp_path/'check'
    exp.execute(out,'live',True)
    assert Counter(calls)=={'E6':258,'P3':258}
    exp.execute(out,'live',True)
    assert len(calls)==516
    result=exp.execute(out,'analyze')
    assert result['calls']==0
    assert all(r['repeats_complete']==3 and r['accuracy_mean']==pytest.approx(64/86) for r in result['summary'])
    plan=json.loads((out/'plan.json').read_text());plan['total_cases']=0
    (out/'plan.json').write_text(json.dumps(plan))
    with pytest.raises(ValueError,match='Frozen plan'):exp.execute(out,'live',True)
    assert len(calls)==516


def test_no_approval_or_no_key_never_calls(tmp_path,monkeypatch):
    with pytest.raises(ValueError,match='approve-paid-api'):exp.execute(tmp_path/'a','live')
    monkeypatch.delenv('OPENROUTER_API_KEY',raising=False)
    with pytest.raises(ValueError,match='not configured'):exp.execute(tmp_path/'b','live',True)
