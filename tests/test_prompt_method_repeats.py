import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from residue_experiment.data import FIELDS
from residue_experiment.evaluation import write_csv
from residue_experiment.instruction_repeats import read_csv
from residue_experiment.prompt import parse_label
from residue_experiment.prompt_methods import MODEL, P3, P4, P5, PROMPTS, parse_p5
from residue_experiment.prompt_method_repeats import (
    ROOT, SCHEDULE, aggregate, child_config, execute, prepare, user_prompt)
from residue_experiment.providers import Provider


@pytest.fixture
def setup():
    config = json.loads((ROOT/'config.openrouter.prompt-methods.json').read_text())
    config['data_dir'] = str(ROOT/'data')
    return (config, ROOT/'results/zero-shot-repeats/gpt-6-sol/2023-2025',
            ROOT/'results/instruction-v1/gpt-6-sol/2023-2025')


def test_independent_frozen_prompts():
    assert P4.startswith('You are a regulatory scientist')
    assert 'regulatory scientist' not in P3 + P5
    assert 'step by step' in P5 and 'step by step' not in P3 + P4
    assert 'Keep definitions from different sources separate.' in P3
    assert 'Keep definitions from different sources separate.' not in P4 + P5
    assert 'Apply the following comparison procedure:' not in P3 + P4 + P5
    assert len(set(PROMPTS.values())) == 3
    assert len(SCHEDULE) == 9 and len(set(SCHEDULE)) == 9
    assert SCHEDULE[:3] == [('P3', 1), ('P4', 1), ('P5', 1)]


@pytest.mark.parametrize('raw,label', [
    ('A concise comparison.\nFinal label: Yes', 'Yes'),
    ('The definitions differ.\n\nFinal label: No\n', 'No'),
    ('"Yes" occurs in the source, but scope differs.\nFinal label: No', 'No'),
])
def test_parse_p5_uses_only_last_label(raw, label):
    assert parse_p5(raw) == label


@pytest.mark.parametrize('raw', [
    'Yes', 'Final label: Yes', 'Reason.\nFinal label: Yes\nextra text',
    'Reason.\nFinal label: No\nFinal label: Yes', 'Reason.\nFinal label: Yes.',
    'Reason.\nFinal label: Maybe', 'Reason.\nFinal label:Yes',
])
def test_parse_p5_rejects_missing_or_ambiguous_final_label(raw):
    with pytest.raises(ValueError):
        parse_p5(raw)


def test_old_label_parser_remains_strict():
    with pytest.raises(ValueError):
        parse_label('Reason.\nFinal label: Yes')


def test_full_dry_run_is_1890_without_calls_and_without_answers(setup, tmp_path, monkeypatch):
    config, b0, b12 = setup
    monkeypatch.setattr('residue_experiment.runner.Provider',
                        lambda *a, **k: pytest.fail('SDK created during dry run'))
    original = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                for root in (b0, b12) for p in root.rglob('*.csv')}
    output = tmp_path/'methods'
    info = execute(config, output, b0, b12)
    assert info['cases'] == 1890 and info['calls'] == 0 and len(info['runs']) == 9
    assert [(r['condition'], r['round']) for r in info['runs']] == SCHEDULE
    hashes = {}
    for c, n in SCHEDULE:
        folder = output/'dry-run'/c/f'round-{n:02d}'
        rows = read_csv(folder/'predictions.csv')
        assert len(rows) == 210 and {r['status'] for r in rows} == {'planned'}
        assert read_csv(folder/'examples.csv') == []
        assert {r['condition'] for r in rows} == {c} and {r['seed'] for r in rows} == {''}
        assert json.loads((folder/'manifest.json').read_text())['system_prompt'] == PROMPTS[c]
        these = {r['id']: r['prompt_sha256'] for r in rows}
        if c in hashes:
            assert hashes[c] == these
        hashes[c] = these
        for line in (folder/'prompts.jsonl').read_text().splitlines():
            problem = json.loads(json.loads(line)['prompt'])
            assert problem['examples'] == [] and set(problem['test']) == set(FIELDS)
    assert all(len({hashes[c][i] for c in PROMPTS}) == 3 for i in hashes['P3'])
    comparisons = read_csv(output/'dry-run/analysis/baseline_comparison.csv')
    assert all(r['n_complete'] == '0' and r['p2_new_error_recovered'] == '0' for r in comparisons)
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == h for p, h in original.items())


def test_independent_live_rounds_resume_and_analyze_without_calls(setup, tmp_path, monkeypatch):
    config, b0, b12 = setup
    calls, instances = [], []
    class FakeProvider:
        def __init__(self, provider, model, cfg, *, system_prompt):
            assert provider == 'openai' and model == MODEL
            self.condition = cfg['conditions'][0]
            assert system_prompt == PROMPTS[self.condition]
            instances.append(self.condition)
        def call(self, prompt):
            p = json.loads(prompt)
            assert p['examples'] == [] and set(p['test']) == set(FIELDS)
            calls.append((self.condition, prompt))
            raw = 'A brief source comparison.\nFinal label: No' if self.condition == 'P5' else 'Yes'
            return raw, {'prompt_tokens': 10, 'completion_tokens': 5}, 'fake'
    monkeypatch.setattr('residue_experiment.runner.Provider', FakeProvider)
    out = tmp_path/'out'
    execute(config, out, b0, b12, 'live', True, only_round=1)
    assert instances == ['P3', 'P4', 'P5'] and len(calls) == 630
    assert {c: sum(x[0] == c for x in calls) for c in PROMPTS} == dict(P3=210, P4=210, P5=210)
    execute(config, out, b0, b12, 'live', True, only_round=1)
    assert len(calls) == 630
    execute(config, out, b0, b12, 'analyze')
    assert len(calls) == 630
    rows = read_csv(out/'live/P5/round-01/predictions.csv')
    assert {r['prediction'] for r in rows} == {'No'}
    assert all(r['response'].endswith('Final label: No') for r in rows)
    stats = read_csv(out/'live/analysis/baseline_comparison.csv')
    assert all(r['n_complete'] == '0' and r['p2_fix_lost'] == '0' for r in stats)
    assert not (out/'.run.lock').exists()


def test_mock_p5_and_real_baseline_cohorts(setup, tmp_path):
    config, b0, b12 = setup
    out = tmp_path/'mock'
    info = execute(config, out, b0, b12, 'mock', condition='P5', only_round=1)
    assert info['cases'] == 210 and info['calls'] == 210
    responses = read_csv(out/'mock/P5/round-01/predictions.csv')
    assert all(parse_p5(r['response']) == r['prediction'] for r in responses)
    comparisons = read_csv(out/'mock/analysis/baseline_comparison.csv')
    assert all(r['p2_new_error_total'] == '8' and r['p2_core_fix_total'] == '6'
               and r['common_stable_total'] == '183' for r in comparisons)


def test_cohort_recovery_retention_and_new_damage(setup, tmp_path):
    config, b0, b12 = setup
    data, old, _ = prepare(config, b0, b12)
    tests = {r['id']: r for y in config['years'] for r in data.tests[y]}
    lost = next(i for i in tests if int(old['P0'][i]['wrong_count']) == 3
                and old['P2'][i]['wrong_count'] == 0)
    damaged = next(i for i in tests if int(old['P0'][i]['wrong_count']) == 0
                   and old['P2'][i]['wrong_count'] == 0)
    out = tmp_path/'out'
    for n in (1, 2, 3):
        folder = out/'mock/P3'/f'round-{n:02d}'
        folder.mkdir(parents=True)
        (folder/'manifest.json').write_text(json.dumps(dict(
            mode='mock', config=child_config(config, 'P3', n), system_prompt=P3)))
        rows = []
        for i, t in tests.items():
            answer = t['EFSA']
            if i == lost or i == damaged and n == 1:
                answer = 'No' if answer == 'Yes' else 'Yes'
            rows.append(dict(id=i, year=t['year'], actual=t['EFSA'], prediction=answer,
                             condition='P3', provider='openai', model=MODEL, seed='',
                             mode='mock', status='success', response=answer,
                             prompt_sha256=hashlib.sha256((P3+user_prompt(t)).encode()).hexdigest()))
        write_csv(folder/'predictions.csv', rows)
    summary = aggregate(out, 'mock', config, data, old)
    p3 = next(r for r in summary if r['condition'] == 'P3')
    assert p3['n_complete'] == 210 and p3['p2_new_error_recovered'] == 8
    assert p3['p2_fix_retained'] == 5 and p3['p2_fix_lost'] == 1
    assert p3['additional_new_error'] == 1


def test_approval_models_protected_outputs_and_changed_plan(setup, tmp_path, monkeypatch):
    config, b0, b12 = setup
    monkeypatch.setattr('residue_experiment.runner.Provider',
                        lambda *a, **k: pytest.fail('SDK must not be created'))
    out = tmp_path/'out'
    with pytest.raises(ValueError, match='approve-paid-api'):
        execute(config, out, b0, b12, 'live')
    assert not out.exists()
    with pytest.raises(ValueError, match='read-only'):
        execute(config, b12/'new-run', b0, b12)
    changed = copy.deepcopy(config)
    changed['models'] = {'anthropic': 'anything'}
    with pytest.raises(ValueError, match='frozen GPT'):
        execute(changed, out, b0, b12)
    execute(config, out, b0, b12, condition='P3', only_round=1)
    plan = json.loads((out/'plan.json').read_text())
    plan['system_prompts']['P3'] = 'changed'
    (out/'plan.json').write_text(json.dumps(plan))
    with pytest.raises(ValueError, match='changed'):
        execute(config, out, b0, b12)
    assert not (out/'.run.lock').exists()


def test_bad_cot_response_is_saved_as_error_not_scored(setup, tmp_path, monkeypatch):
    config, b0, b12 = setup
    class FakeProvider:
        def __init__(self, *a, **k):
            pass
        def call(self, prompt):
            return 'Reason.\nFinal label: Yes\ntrailing output', {}, 'bad'
    monkeypatch.setattr('residue_experiment.runner.Provider', FakeProvider)
    monkeypatch.setattr('residue_experiment.runner.time.sleep', lambda _: None)
    out = tmp_path/'bad'
    with pytest.raises(ValueError, match='repeated API/response errors'):
        execute(config, out, b0, b12, 'live', True, condition='P5', only_round=1)
    rows = read_csv(out/'live/P5/round-01/predictions.csv')
    errors = [r for r in rows if r['status'] == 'error']
    assert len(errors) == 1 and errors[0]['prediction'] == ''
    assert errors[0]['response'].endswith('trailing output')
    assert len(read_csv(out/'live/P5/round-01/api_errors.csv')) == 3
    summary = read_csv(out/'live/analysis/baseline_comparison.csv')
    assert all(r['n_complete'] == '0' for r in summary)


def test_provider_has_no_conversation_history(monkeypatch):
    import openai
    monkeypatch.setenv('OPENROUTER_API_KEY', 'dummy-test')
    factory = MagicMock()
    monkeypatch.setattr(openai, 'OpenAI', factory)
    factory.return_value.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='Yes'))], usage=None, id='test')
    cfg = dict(api_backend='openrouter', timeout_seconds=120, max_output_tokens=1000)
    client = Provider('openai', MODEL, cfg, system_prompt=P4)
    client.call('first problem')
    client.call('second problem')
    requests = factory.return_value.chat.completions.create.call_args_list
    assert [c.kwargs['messages'] for c in requests] == [
        [{'role': 'system', 'content': P4}, {'role': 'user', 'content': p}]
        for p in ('first problem', 'second problem')]
