import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from residue_experiment.data import Dataset, FIELDS
from residue_experiment.evaluation import write_csv
from residue_experiment.instruction_prompts import COMMON, MODEL_SPECIFIC, VARIANTS, system_for
from residue_experiment.instruction_repeats import execute, aggregate, prepare, read_csv
from residue_experiment.prompt import SYSTEM, build_prompt
from residue_experiment.providers import Provider
from residue_experiment.runner import run

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def experiment(tmp_path):
    config = json.loads((ROOT/'config.openrouter.instructions.json').read_text())
    config.update(data_dir=str(ROOT/'data'), models={'openai': 'openai/gpt-6-sol'},
                  retry_delay_seconds=0)
    data = Dataset(config['data_dir'])
    tests = [r for y in config['years'] for r in data.tests[y]]
    baseline = tmp_path/'baseline'
    (baseline/'analysis').mkdir(parents=True)
    summary = []
    for index, r in enumerate(tests):
        opposite = 'No' if r['EFSA'] == 'Yes' else 'Yes'
        nwrong = 3 if index == 0 else 2 if index == 1 else 0
        row = dict(id=r['id'], year=r['year'], actual=r['EFSA'], valid_runs=3,
                   wrong_count=nwrong, complete=True, analysis_group='fixture')
        for number in (1, 2, 3):
            row[f'round_{number}_prediction'] = opposite if number <= nwrong else r['EFSA']
            row[f'round_{number}_status'] = 'success'
        summary.append(row)
    write_csv(baseline/'analysis/all_210_error_frequency.csv', summary)
    old = copy.deepcopy(config)
    old['conditions'] = ['E0']
    for number in (2, 3):
        folder = baseline/'live'/f'round-{number:02d}'
        folder.mkdir(parents=True)
        (folder/'manifest.json').write_text(json.dumps(dict(mode='live', system_prompt=SYSTEM, config=old)))
        write_csv(folder/'predictions.csv', [
            dict(id=r['id'], year=r['year'], actual=r['EFSA'], provider='openai',
                 model='openai/gpt-6-sol', mode='live', condition='E0', status='success',
                 prediction=summary[i][f'round_{number}_prediction'],
                 prompt_sha256=hashlib.sha256((SYSTEM+build_prompt(r,[]).replace('\\r\\n','\\n')).encode()).hexdigest())
            for i, r in enumerate(tests)])
    return config, data, baseline


def test_prompt_variants_are_frozen_and_do_not_change_original():
    original = SYSTEM
    assert VARIANTS == ('P1', 'P2')
    assert len({system_for(p,'P1') for p in MODEL_SPECIFIC}) == 1
    assert len({system_for(p,'P2') for p in MODEL_SPECIFIC}) == 3
    for p in MODEL_SPECIFIC:
        assert system_for(p,'P1').startswith(original+'\n\n')
        assert system_for(p,'P2') == system_for(p,'P1')+'\n\n'+MODEL_SPECIFIC[p]
    with pytest.raises(ValueError):
        system_for('openai','P0')
    assert SYSTEM == original


def test_dry_plan_1260_no_calls_and_no_labels(experiment,tmp_path,monkeypatch):
    config, data, baseline = experiment
    monkeypatch.setattr('residue_experiment.runner.Provider',lambda *a,**k:pytest.fail('SDK constructed'))
    monkeypatch.setattr('residue_experiment.runner.mock_call',lambda *a:pytest.fail('Mock called'))
    output = tmp_path/'instructions'
    before = (baseline/'analysis/all_210_error_frequency.csv').read_bytes()
    info = execute(config,output,baseline)
    assert info['cases'] == 1260 and info['calls'] == 0
    assert len(info['runs']) == 6
    assert all(r['condition'] in VARIANTS for r in info['runs'])
    plan = json.loads((output/'plan.json').read_text())
    assert plan['P0_is_not_executed'] is True
    all_hashes = {}
    for variant in VARIANTS:
        variants = []
        for number in (1,2,3):
            folder = output/'dry-run'/variant/f'round-{number:02d}'
            rows = read_csv(folder/'predictions.csv')
            assert len(rows) == 210 and {r['condition'] for r in rows} == {variant}
            assert {r['status'] for r in rows} == {'planned'}
            manifest = json.loads((folder/'manifest.json').read_text())
            assert manifest['system_prompt'] == system_for('openai',variant)
            variants.append({r['id']:r['prompt_sha256'] for r in rows})
            assert read_csv(folder/'examples.csv') == []
            for line in (folder/'prompts.jsonl').read_text().splitlines():
                payload = json.loads(json.loads(line)['prompt'])
                assert payload['examples'] == []
                assert set(payload['test']) == set(FIELDS)
        assert variants[0] == variants[1] == variants[2]
        all_hashes[variant] = variants[0]
    assert all(all_hashes['P1'][i] != all_hashes['P2'][i] for i in all_hashes['P1'])
    assert (baseline/'analysis/all_210_error_frequency.csv').read_bytes() == before
    report = read_csv(output/'dry-run/analysis/baseline_comparison.csv')
    assert all(r['n_complete'] == '0' and r['core_fully_fixed'] == '0' for r in report)


def test_live_approval_guard(experiment,tmp_path,monkeypatch):
    config,_,baseline=experiment
    monkeypatch.setattr('residue_experiment.runner.Provider',lambda *a,**k:pytest.fail('SDK constructed'))
    with pytest.raises(ValueError,match='approve-paid-api'):
        execute(config,tmp_path/'out',baseline,mode='live')
    assert not (tmp_path/'out').exists()


def test_live_custom_system_resume_and_partial_round(experiment,tmp_path,monkeypatch):
    config,_,baseline=experiment
    calls=[]
    class FakeProvider:
        def __init__(self,provider,model,c,*,system_prompt=None):
            assert system_prompt == system_for('openai','P2')
        def call(self,prompt):
            payload=json.loads(prompt)
            assert payload['examples'] == [] and 'EFSA' not in payload['test']
            calls.append(prompt)
            return 'Yes',{},'fake'
    monkeypatch.setattr('residue_experiment.runner.Provider',FakeProvider)
    output=tmp_path/'out'
    first=execute(config,output,baseline,'live',True,condition='P2',only_round=2)
    assert first['cases']==210 and len(calls)==210
    execute(config,output,baseline,'live',True,condition='P2',only_round=2)
    assert len(calls)==210
    freq=read_csv(output/'live/analysis/P2_error_frequency.csv')
    assert all(r['complete']=='False' and r['core_fully_fixed']=='' for r in freq)
    execute(config,output,baseline,'analyze')
    assert len(calls)==210


def test_reject_P0_changed_plan_and_baseline(experiment,tmp_path):
    config,_,baseline=experiment
    with pytest.raises(ValueError,match='P0'):
        execute(config,tmp_path/'p0',baseline,condition='P0')
    output=tmp_path/'out'
    execute(config,output,baseline,condition='P1',only_round=1)
    changed=copy.deepcopy(config)
    changed['seeds']=[123]
    with pytest.raises(ValueError,match='changed'):
        execute(changed,output,baseline)
    p=baseline/'analysis/all_210_error_frequency.csv'
    rows=read_csv(p)
    rows[0]['valid_runs']='2'
    write_csv(p,rows)
    with pytest.raises(ValueError,match='incomplete'):
        execute(config,tmp_path/'incomplete',baseline)


def test_reject_baseline_input_change_before_calls(experiment,tmp_path,monkeypatch):
    config,_,baseline=experiment
    p=baseline/'live/round-02/predictions.csv'
    rows=read_csv(p)
    rows[0]['prompt_sha256']='incorrect'
    write_csv(p,rows)
    monkeypatch.setattr('residue_experiment.runner.Provider',lambda *a,**k:pytest.fail('SDK constructed'))
    with pytest.raises(ValueError,match='Baseline input'):
        execute(config,tmp_path/'out',baseline)


def test_core_fixed_and_stable_damage_aggregation(experiment,tmp_path):
    config,data,baseline=experiment
    _,old,_=prepare(config,baseline)
    output=tmp_path/'out'
    originals=[r for y in config['years'] for r in data.tests[y]]
    damaged=originals[2]['id']
    for variant in VARIANTS:
        for number in (1,2,3):
            folder=output/'mock'/variant/f'round-{number:02d}'
            folder.mkdir(parents=True)
            child=dict(config,conditions=[variant],instruction_round=number)
            (folder/'manifest.json').write_text(json.dumps(dict(mode='mock',config=child,
                system_prompt=system_for('openai',variant))))
            rows=[]
            for r in originals:
                answer=r['EFSA']
                if r['id']==damaged and number==1:
                    answer='No' if answer=='Yes' else 'Yes'
                prompt=build_prompt(r,[]).replace('\\r\\n','\\n')
                rows.append(dict(id=r['id'],year=r['year'],actual=r['EFSA'],prediction=answer,
                    condition=variant,mode='mock',provider='openai',model='openai/gpt-6-sol',status='success',
                    prompt_sha256=hashlib.sha256((system_for('openai',variant)+prompt).encode()).hexdigest()))
            write_csv(folder/'predictions.csv',rows)
    summary=aggregate(output,'mock',config,data,old)
    assert all(r['n_complete']==210 and r['baseline_core']==1 and r['core_fully_fixed']==1
               and r['stable_correct_damaged']==1 for r in summary)
    for variant in VARIANTS:
        new=read_csv(output/'mock/analysis'/f'{variant}_new_errors.csv')
        assert [r['id'] for r in new]==[damaged]


def test_provider_sends_selected_system(monkeypatch):
    import openai
    monkeypatch.setenv('OPENROUTER_API_KEY','dummy-test')
    factory=MagicMock()
    monkeypatch.setattr(openai,'OpenAI',factory)
    factory.return_value.chat.completions.create.return_value=SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='Yes'))],usage=None,id='test')
    config=dict(api_backend='openrouter',timeout_seconds=120,max_output_tokens=1000)
    system=system_for('gemini','P2')
    client=Provider('gemini','google/test',config,system_prompt=system)
    assert client.call('input')[0]=='Yes'
    assert factory.return_value.chat.completions.create.call_args.kwargs['messages']==[
        {'role':'system','content':system},{'role':'user','content':'input'}]


def test_runner_refuses_implicit_instruction_system(experiment,tmp_path):
    config,_,_=experiment
    with pytest.raises(ValueError,match='explicit system'):
        run(dict(config,conditions=['P1']),tmp_path/'out')
