import copy
import json

import pytest

from residue_experiment.prompt_search import hash_value, save, read
from residue_experiment.prompt_search_continue import ContinuationCalls
from residue_experiment.risk_search import load_plan, choose, run
from residue_experiment.risk_search import select_ten
from residue_experiment.risk_search import repair_connection


def test_connection_repair_preserves_budget_and_rejects_other_states(tmp_path, monkeypatch):
    import shutil
    plan = load_plan('results/r6c1-risk-search-mixed')
    shutil.copyfile('results/r6c1-risk-search-mixed/seed_cache.json', tmp_path / 'seed_cache.json')
    monkeypatch.setattr('residue_experiment.prompt_search.Provider', lambda *a, **kw: pytest.fail('Paid call'))
    call_id = 'a' * 64
    path = tmp_path / 'live/calls' / f'{call_id}.json'
    record = {'status': 'started', 'request': {'plan_hash': plan['plan_hash'], 'key': 'selection/test'}}
    save(path, record)
    with pytest.raises(ValueError, match='Only recorded'):
        repair_connection(plan, tmp_path, 'live', call_id)
    record.update(status='error', error_type='APIConnectionError')
    save(path, record)
    result = repair_connection(plan, tmp_path, 'live', call_id)
    assert result['api_calls'] == 0 and not path.exists()
    assert read(result['archived']) == record
    assert repair_connection(plan, tmp_path, 'live', call_id)['already_archived'] == call_id
    calls = ContinuationCalls(plan, tmp_path, 'live', 1)
    assert calls.count == 1
    with pytest.raises(RuntimeError, match='Total call cap'):
        calls.call('new', 'unique system', 'unique user', 'prediction')
    save(path, dict(record, status='success', response='Yes'))
    with pytest.raises(ValueError, match='Only recorded'):
        repair_connection(plan, tmp_path, 'live', call_id)
    with pytest.raises(ValueError, match='64-character'):
        repair_connection(plan, tmp_path, 'live', '../bad')


def test_mixed_batches_coverage_first_ten_and_selection():
    plan = load_plan('results/r6c1-risk-search-mixed')
    first = {r['id'] for r in plan['optimizer_cases']}
    assert first <= {r['id'] for r in plan['batches'][0]}
    seen_risk = []
    for batch in plan['batches']:
        assert len(batch) == len({r['id'] for r in batch}) == 50
        assert sum(r['purpose'] == 'Risk assessment' for r in batch) == 35
        assert sum(r['purpose'] == 'Enforcement' for r in batch) == 15
        seen_risk.extend(r['id'] for r in batch if r['purpose'] == 'Risk assessment')
    assert len(set(seen_risk[:147])) == 147
    assert plan['expected_calls'] == 3650
    batch = plan['batches'][1]
    preds = [dict(id=r['id'], correct=False) for r in batch]
    chosen = select_ten(batch, preds, plan['optimizer_excluded_ids'])
    assert len(chosen) <= 10
    assert not {r['id'] for r in chosen} & set(plan['optimizer_excluded_ids'])
    assert all(r['purpose'] == 'Risk assessment' for r in chosen)
    assert select_ten(batch, [dict(id=r['id'], correct=True) for r in batch], []) == []


def test_mixed_run_refreshes_ten_and_replays_memory(tmp_path, monkeypatch):
    import shutil
    plan = load_plan('results/r6c1-risk-search-mixed')
    shutil.copyfile('results/r6c1-risk-search-mixed/seed_cache.json', tmp_path / 'seed_cache.json')
    monkeypatch.setattr('residue_experiment.prompt_search.Provider', lambda *a, **kw: pytest.fail('Paid call'))
    monkeypatch.setattr('residue_experiment.prompt_search.mock_call', lambda *a: ('Yes', {}, 'mock'))
    run(plan, tmp_path, 'mock', 3650, through_round=1)
    first = read(tmp_path / 'mock/round-01/memory.json')
    assert first['optimizer_ids'] == [r['id'] for r in plan['optimizer_cases']]
    result = run(plan, tmp_path, 'mock', 3650, through_round=2)
    assert result['stop_reason'] == 'patience'
    second = read(tmp_path / 'mock/round-02/memory.json')
    assert set(first['optimizer_ids']) <= set(second['memory_ids'])
    assert second['optimizer_ids'] != first['optimizer_ids']
    assert set(second['optimizer_ids']) <= set(second['batch_ids'])
    payload = read(tmp_path / 'mock/round-02/optimizer_input.json')
    assert len(payload['development_cases']) <= 10
    assert payload['previous_ten_case_feedback'] == []
    assert run(plan, tmp_path, 'mock', 3650) == result


def test_real_baseline_fully_cached(tmp_path, monkeypatch):
    import shutil
    plan = load_plan('results/r6c1-risk-search')
    shutil.copyfile('results/r6c1-risk-search/seed_cache.json', tmp_path / 'seed_cache.json')
    monkeypatch.setattr('residue_experiment.prompt_search.Provider', lambda *a, **kw: pytest.fail('Paid call'))
    calls = ContinuationCalls(plan, tmp_path, 'live', max_calls=0)
    for key in ['risk_rows', 'enforcement_rows', 'selection']:
        predictions, _ = calls.evaluate(plan['start_prompt'], plan[key], key)
        assert len(predictions) == len(plan[key])
    assert calls.count == 0
    assert calls.cache_hits == 328


def test_choose_requires_both_metrics_and_gate():
    def candidate(name, ra, enf, eligible=True):
        return {'name': name, 'prompt': name, 'gate': {'eligible': eligible},
                'metrics': {'Risk assessment': {'accuracy': ra}, 'Enforcement': {'accuracy': enf},
                            'all': {'accuracy': (ra+enf)/2, 'macro_f1': (ra+enf)/2}}}
    current = candidate('base', .8, .9)
    for bad in [candidate('same', .8, 1), candidate('enf_drop', .9, .8), candidate('gate_fail', 1, 1, False)]:
        assert choose(current, [bad]) == (current, False)
    good = candidate('good', .9, .9)
    assert choose(current, [good]) == (good, True)


def test_rounds_resume_patience_and_optimizer_isolation(tmp_path, monkeypatch):
    plan = copy.deepcopy(load_plan('results/r6c1-risk-search'))
    def row(i, purpose, label):
        return {'id': i, 'year': '2020', 'substance': i, 'purpose': purpose,
                'commodity': 'Plant products', 'JMPR': 'A', 'EU': 'A', 'EFSA': label}
    ten = [row(f'dev{i}', 'Risk assessment', 'No' if i % 2 else 'Yes') for i in range(10)]
    plan.update(optimizer_cases=ten, risk_rows=ten,
                enforcement_rows=[row('safe1', 'Enforcement', 'Yes')],
                selection=[row('heldout1', 'Enforcement', 'Yes'), row('heldout2', 'Risk assessment', 'No')])
    plan['continuation']['seed_cache_hash'] = hash_value({})
    save(tmp_path / 'seed_cache.json', {})
    monkeypatch.setattr('residue_experiment.prompt_search.Provider', lambda *a, **kw: pytest.fail('Paid call'))
    monkeypatch.setattr('residue_experiment.prompt_search.mock_call', lambda *a: ('Yes', {}, 'mock'))
    with pytest.raises(RuntimeError, match='Total call cap'):
        run(plan, tmp_path, 'mock', 1)
    result = run(plan, tmp_path, 'mock', 200)
    assert result['completed_rounds'] == 2
    assert result['stop_reason'] == 'patience'
    assert result['name'] == 'R6C1'
    count = len(list((tmp_path / 'mock/calls').glob('*.json')))
    assert run(plan, tmp_path, 'mock', 200) == result
    assert len(list((tmp_path / 'mock/calls').glob('*.json'))) == count
    for path in (tmp_path / 'mock/calls').glob('*.json'):
        req = read(path)['request']
        if req['kind'] in ('analysis', 'generation'):
            payload = json.loads(req['user'])
            assert len(payload['development_cases']) == 10
            assert 'heldout' not in req['user'] and 'safe1' not in req['user']
        else:
            assert 'EFSA' not in json.loads(req['user'])['test']
    second = read(tmp_path / 'mock/round-02/optimizer_input.json')
    assert len(second['previous_ten_case_feedback']) == 3
