import copy
import json

import pytest

from residue_experiment.eval_2026 import load_plan, run, validate_pair, EvaluationCalls
from residue_experiment.prompt_search import read, save


def test_p0_same_frozen_data_separate_requests(tmp_path, monkeypatch):
    plan = load_plan('results/p0-eval-2026')
    reference = load_plan('results/r6c1-eval-2026')
    assert plan['name'] == 'P0'
    assert plan['comparison_plan_hash'] == reference['plan_hash']
    assert plan['prompt'] == read('results/prompt-search-v2-continued-patience2/plan.json')['p0']
    assert plan['prompt'] != reference['prompt']
    for key in ('rows', 'config', 'repeats', 'excluded_overlap_ids'):
        assert plan[key] == reference[key]
    monkeypatch.setattr('residue_experiment.prompt_search.Provider', lambda *a, **kw: pytest.fail('Paid API'))
    with pytest.raises(RuntimeError, match='Total call cap'):
        run(plan, tmp_path, 'mock', 1)
    record = read(next((tmp_path / 'mock/calls').glob('*.json')))
    assert record['request']['key'].startswith('test/2026/P0/1/')
    assert record['request']['system'] == plan['prompt']


def test_frozen_data_and_validation():
    plan = load_plan('results/r6c1-eval-2026')
    assert plan['name'] == 'R6C1'
    assert len(plan['rows']) == 86 and plan['repeats'] == 3 and plan['expected_calls'] == 258
    assert set(plan['excluded_overlap_ids']) == {'2026-22-01', '2026-14-01'}
    assert validate_pair(plan['rows'], plan['rows']) == plan['rows']
    for mutation in ('id', 'EU', 'EFSA', 'year'):
        answers = copy.deepcopy(plan['rows'])
        answers[0][mutation] = 'invalid'
        with pytest.raises(ValueError):
            validate_pair(plan['rows'], answers)
    with pytest.raises(ValueError):
        validate_pair(plan['rows'][:-1], plan['rows'])


def test_mock_resume_repeats_no_leakage_and_subset_metrics(tmp_path, monkeypatch):
    plan = load_plan('results/r6c1-eval-2026')
    monkeypatch.setattr('residue_experiment.prompt_search.Provider', lambda *a, **kw: pytest.fail('Paid API'))
    monkeypatch.setattr('residue_experiment.prompt_search.mock_call', lambda *a: ('Yes', {}, 'mock'))
    with pytest.raises(RuntimeError, match='Total call cap'):
        run(plan, tmp_path, 'mock', 5)
    result = run(plan, tmp_path, 'mock', 258)
    assert result['calls'] == 258
    all_metrics = result['metrics']['all_86']
    assert all_metrics['all']['cases_per_repeat'] == 86
    assert all_metrics['Enforcement']['cases_per_repeat'] == 46
    assert all_metrics['Risk assessment']['cases_per_repeat'] == 40
    assert all_metrics['all']['accuracy_mean'] == pytest.approx(64/86)
    assert all_metrics['all']['fp_total'] == 66
    assert result['metrics']['without_prior_overlap']['all']['cases_per_repeat'] == 84
    assert run(plan, tmp_path, 'mock', 258) == result
    records = list((tmp_path / 'mock/calls').glob('*.json'))
    assert len(records) == 258
    for f in records:
        req = read(f)['request']
        assert req['system'] == plan['prompt']
        payload = json.loads(req['user'])
        assert payload['examples'] == []
        assert set(payload['test']) == {'substance', 'purpose', 'commodity', 'JMPR', 'EU'}


def test_archived_attempt_still_counts(tmp_path, monkeypatch):
    plan = load_plan('results/r6c1-eval-2026')
    save(tmp_path / 'live/connection_error_attempts/old.json', {'status': 'error'})
    monkeypatch.setattr('residue_experiment.prompt_search.Provider', lambda *a, **kw: pytest.fail('Paid API'))
    calls = EvaluationCalls(plan, tmp_path, 'live', 1)
    assert calls.count == 1
    with pytest.raises(RuntimeError, match='Total call cap'):
        calls.call('new', 'system', 'user', 'prediction')
