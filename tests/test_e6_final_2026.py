import json
from pathlib import Path
import pytest
from residue_experiment import e6_final_2026 as final
from residue_experiment.instruction_repeats import read_csv


def test_all_86_no_target_answers_or_source_comments(tmp_path, monkeypatch):
    monkeypatch.setattr('residue_experiment.runner.Provider',lambda *a,**k: pytest.fail('API client'))
    result=final.execute(tmp_path/'check')
    assert result['cases']==258 and result['calls']==0
    plan=json.loads((tmp_path/'check/plan.json').read_text())
    assert plan['prior_input_overlap']==['2026-14-01','2026-22-01']
    assert plan['system_prompt']==final.guided.GUIDED_SYSTEM
    for n in (1,2,3):
        folder=tmp_path/'check/dry-run'/f'round-{n:02d}'
        prompts=final.guided.prompts(folder)
        assert len(prompts)==86
        for payload in prompts.values():
            assert set(payload['test'])==set(final.FIELDS)
            assert len(payload['examples'])==4
            assert all(set(e)=={*final.FIELDS,'EFSA'} for e in payload['examples'])
        assert all(r['example_year']=='2025' for r in read_csv(folder/'examples.csv'))


def test_fake_live_resumes_and_does_not_send_answerkey(tmp_path,monkeypatch):
    calls=[]
    class Fake:
        def __init__(self,*a,system_prompt,**k):
            assert system_prompt==final.guided.GUIDED_SYSTEM
        def call(self,prompt):
            payload=json.loads(prompt)
            assert set(payload['test'])==set(final.FIELDS)
            assert 'efsa_comments' not in prompt and 'source_url' not in prompt
            calls.append(prompt)
            return 'Yes',{},'fake'
    monkeypatch.setattr('residue_experiment.runner.Provider',Fake)
    monkeypatch.setenv('OPENROUTER_API_KEY','fake-key-for-mocked-provider')
    out=tmp_path/'live'
    final.execute(out,'live',True)
    assert len(calls)==258
    final.execute(out,'live',True)
    assert len(calls)==258
    summary=final.execute(out,'analyze')['summary']
    assert summary['repeats_complete']==3
    assert summary['accuracy_mean']==pytest.approx(64/86)


def test_missing_key_and_approval_no_calls(tmp_path,monkeypatch):
    monkeypatch.delenv('OPENROUTER_API_KEY',raising=False)
    with pytest.raises(ValueError,match='approve-paid-api'):final.execute(tmp_path/'one','live')
    with pytest.raises(ValueError,match='not configured'):final.execute(tmp_path/'two','live',True)
    assert not (tmp_path/'two').exists()
