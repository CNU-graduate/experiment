import hashlib
import json

import pytest

from residue_experiment import e6_guided as guided
from residue_experiment.instruction_repeats import read_csv


def test_paid_approval_and_protected_outputs_precede_preflight(tmp_path, monkeypatch):
    monkeypatch.setattr(guided, 'prepare', lambda: pytest.fail('Preflight must not run'))
    with pytest.raises(ValueError, match='approve-paid-api'):
        guided.execute(tmp_path/'paid', 'live')
    with pytest.raises(ValueError, match='dedicated'):
        guided.execute(guided.BASELINES[0])
    assert not (tmp_path/'paid').exists()


def test_real_archives_and_630_case_plan_without_clients(tmp_path, monkeypatch):
    monkeypatch.setattr('residue_experiment.runner.Provider',
                        lambda *a, **k: pytest.fail('Dry-run created API client'))
    tracked = [p for folder in guided.BASELINES for p in folder.rglob('*') if p.is_file()]
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in tracked}
    out = tmp_path/'guided'
    info = guided.execute(out)
    assert info['cases'] == 630 and info['calls'] == 0
    plan = json.loads((out/'plan.json').read_text())
    assert plan['preflight']['user_inputs_and_examples_match_all_archives']
    assert plan['system_prompt'] == guided.GUIDED_SYSTEM
    assert 'Think through' not in guided.ADDITION and 'regulatory scientist' not in guided.ADDITION
    for n in (1, 2, 3):
        folder = out/'dry-run'/f'round-{n:02d}'
        rows = read_csv(folder/'predictions.csv')
        assert len(rows) == 210 and {r['status'] for r in rows} == {'planned'}
        for line in (folder/'prompts.jsonl').read_text().splitlines():
            problem = json.loads(json.loads(line)['prompt'])
            assert len(problem['examples']) == 4
            assert set(problem['test']) == {'substance', 'purpose', 'commodity', 'JMPR', 'EU'}
    summary = read_csv(out/'dry-run/analysis/condition_summary.csv')
    historic = next(r for r in summary if r['condition'] == 'E6-historical' and r['year'] == 'all')
    assert float(historic['accuracy_mean']) == pytest.approx(601/630)
    new = next(r for r in summary if r['condition'] == guided.VERSION and r['year'] == 'all')
    assert new['repeats_complete'] == '0' and new['accuracy_mean'] == ''
    assert all(hashlib.sha256(p.read_bytes()).hexdigest() == h for p, h in before.items())


def test_changed_example_blocks_execution_before_clients(monkeypatch):
    actual_prompts = guided.prompts
    def changed(folder):
        result = actual_prompts(folder)
        if folder == guided.BASELINES[1]:
            first = next(iter(result.values()))
            first['examples'].reverse()
        return result
    monkeypatch.setattr(guided, 'prompts', changed)
    monkeypatch.setattr('residue_experiment.runner.Provider',
                        lambda *a, **k: pytest.fail('Unexpected API client'))
    with pytest.raises(ValueError, match='Examples, order'):
        guided.prepare()


def test_fake_live_resume_analyze_and_changed_plan(tmp_path, monkeypatch):
    calls = []
    class FakeProvider:
        def __init__(self, provider, model, config, *, system_prompt):
            assert provider == 'openai' and model == guided.MODEL
            assert system_prompt == guided.GUIDED_SYSTEM
        def call(self, prompt):
            calls.append(prompt)
            return 'Yes', {}, 'fake'
    monkeypatch.setattr('residue_experiment.runner.Provider', FakeProvider)
    out = tmp_path/'guided'
    guided.execute(out, 'live', True, 1)
    assert len(calls) == 210
    guided.execute(out, 'live', True, 1)
    assert len(calls) == 210
    result = guided.execute(out, 'analyze')
    assert result['calls'] == 0 and len(calls) == 210
    freq = read_csv(out/'live/analysis/error_frequency.csv')
    assert len(freq) == 210 and {r['complete'] for r in freq} == {'False'}
    assert {r['damaged_stable_correct'] for r in freq} == {''}
    plan = json.loads((out/'plan.json').read_text())
    plan['system_prompt'] = 'edited'
    (out/'plan.json').write_text(json.dumps(plan))
    with pytest.raises(ValueError, match='changed'):
        guided.execute(out, 'live', True, 2)
    assert len(calls) == 210 and not (out/'.run.lock').exists()


def test_incompatible_result_not_silently_aggregated(tmp_path):
    config, historical, plan, expected = guided.prepare()
    folder = tmp_path/'live/round-01'
    folder.mkdir(parents=True)
    (folder/'manifest.json').write_text(json.dumps(dict(
        mode='live', config=config, system_prompt='wrong')))
    row = dict(next(iter(expected.values())), mode='live', status='success', prediction='Yes')
    from residue_experiment.evaluation import write_csv
    write_csv(folder/'predictions.csv', [row])
    with pytest.raises(ValueError, match='manifest'):
        guided.aggregate(tmp_path, 'live', config, historical, expected)
