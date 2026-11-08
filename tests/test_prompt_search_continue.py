import copy
import json
import shutil
from pathlib import Path

import pytest

from residue_experiment.prompt_search import read, save, hash_value
from residue_experiment.prompt_search_continue import prepare, ContinuationCalls, run_round, progress, run_through
from residue_experiment.prompt_search_guarded import search_guarded
from residue_experiment.prompt_search_continue import repair_empty


def test_empty_repair_preserves_budget_and_other_records(prepared, tmp_path, monkeypatch):
    plan, source = prepared
    shutil.copyfile(source / 'seed_cache.json', tmp_path / 'seed_cache.json')
    monkeypatch.setattr('residue_experiment.prompt_search.Provider', lambda *a, **k: pytest.fail('Paid call'))
    calls = ContinuationCalls(plan, tmp_path, 'live', max_calls=1)
    req = dict(next(iter(read(source / 'seed_cache.json').values()))['request'],
               plan_hash=plan['plan_hash'], key='empty-test')
    save(calls.attempts / 'empty.json', {'status': 'success', 'request': req, 'response': ''})
    save(calls.attempts / 'valid.json', {'status': 'success', 'request': dict(req, key='valid'), 'response': 'No'})
    save(calls.attempts / 'started.json', {'status': 'started', 'request': dict(req, key='started')})
    assert repair_empty(plan, tmp_path, 'live')['archived_empty_predictions'] == ['empty-test']
    assert read(calls.attempts / 'valid.json')['response'] == 'No'
    assert (calls.attempts / 'started.json').exists()
    assert len(list((calls.folder / 'empty_response_attempts').glob('*.json'))) == 1
    assert repair_empty(plan, tmp_path, 'live')['archived_empty_predictions'] == []
    with pytest.raises(RuntimeError, match='Unresolved call'):
        ContinuationCalls(plan, tmp_path, 'live', max_calls=1)
    (calls.attempts / 'started.json').unlink()
    resumed = ContinuationCalls(plan, tmp_path, 'live', max_calls=2)
    assert resumed.count == 2
    with pytest.raises(RuntimeError, match='Total call cap'):
        resumed.call('retry', req['system'] + 'unique', req['user'], 'prediction')


@pytest.fixture(scope='module')
def prepared(tmp_path_factory):
    folder = tmp_path_factory.mktemp('continuation-plan')
    plan = prepare('results/prompt-search-2023-v2', folder)
    return plan, folder


def test_batches_and_initial_state(prepared):
    plan, _ = prepared
    assert plan['seed_state']['winner']['name'] == 'R4C2'
    assert plan['expected_calls'] == 3960
    assert 'test' not in plan
    assert len(plan['batches']) == 10
    assert all(len(b) == 50 for b in plan['batches'])
    first = [r['id'] for b in plan['batches'][:6] for r in b]
    second = [r['id'] for b in plan['batches'][6:] for r in b]
    assert len(set(first)) == 300 and len(set(second)) == 200
    omitted = set(plan['continuation']['epoch1_omitted_ids'])
    assert len(omitted) == 26 and not omitted.intersection(first)
    assert omitted <= {r['id'] for r in plan['batches'][6]}
    assert len(plan['seed_state']['memory_ids']) == 50
    assert plan['seed_state']['stale'] == 0
    assert plan['config']['continuation_early_stop'] is True


def test_run_through_resumes_and_stops_at_requested_round(tmp_path, monkeypatch):
    state = {'completed_rounds': 5}
    attempts = []
    interrupt = [True]
    monkeypatch.setattr('residue_experiment.prompt_search_continue.progress', lambda *a: dict(state))
    def fake_round(plan, output, mode, number, approved, cap):
        assert approved and cap == 3960
        attempts.append(number)
        if number == 8 and interrupt[0]:
            interrupt[0] = False
            raise RuntimeError('budget or API interruption')
        state['completed_rounds'] = number
        return {'completed_round': number, 'next_round_requires_approval': number + 1 if number < 10 else None}
    monkeypatch.setattr('residue_experiment.prompt_search_continue.run_round', fake_round)
    plan = {'plan_hash': 'test', 'expected_calls': 3960}
    with pytest.raises(RuntimeError, match='interruption'):
        run_through(plan, tmp_path, 'mock', 10, 3960)
    assert state['completed_rounds'] == 7
    assert run_through(plan, tmp_path, 'mock', 10, 3960)['rounds_run'] == [8, 9, 10]
    assert attempts == [6, 7, 8, 8, 9, 10]
    assert run_through(plan, tmp_path, 'mock', 10, 3960)['rounds_run'] == []
    with pytest.raises(ValueError, match='between'):
        run_through(plan, tmp_path, 'mock', 11, 3960)


def test_source_cache_only_exact_requests(prepared, tmp_path, monkeypatch):
    plan, source = prepared
    shutil.copyfile(source / 'seed_cache.json', tmp_path / 'seed_cache.json')
    monkeypatch.setattr('residue_experiment.prompt_search.Provider', lambda *a, **k: pytest.fail('Paid call'))
    calls = ContinuationCalls(plan, tmp_path, 'live', max_calls=0)
    record = next(iter(read(source / 'seed_cache.json').values()))
    req = record['request']
    assert calls.call('new-key', req['system'], req['user'], 'prediction') == record['response']
    assert calls.count == 0
    with pytest.raises(RuntimeError, match='Total call cap'):
        calls.call('changed', req['system'] + 'changed', req['user'], 'prediction')
    save(calls.attempts / 'uncertain.json', {'status': 'started', 'request': dict(req, plan_hash=plan['plan_hash'])})
    with pytest.raises(RuntimeError, match='Unresolved call'):
        ContinuationCalls(plan, tmp_path, 'live')


def test_approval_dedup_resume_and_stop_at_seven(prepared, tmp_path, monkeypatch):
    plan, source = prepared
    plan = copy.deepcopy(plan)
    shutil.copyfile(source / 'seed_cache.json', tmp_path / 'seed_cache.json')
    plan['selection'] = plan['selection'][:2]
    # Revisit existing memory with current errors: no new IDs, but still eligible targets.
    plan['seed_state']['memory_ids'] = [r['id'] for r in plan['development'] if r['EFSA'] == 'Yes'][:2]
    selected = {r['id']: r for r in plan['development']}
    batch = [selected[i] for i in plan['seed_state']['memory_ids']]
    plan['batches'][5:] = [batch] * 5
    plan['config']['memory_per_round'] = 2
    monkeypatch.setattr('residue_experiment.prompt_search.Provider', lambda *a, **k: pytest.fail('Paid call'))
    monkeypatch.setattr('residue_experiment.prompt_search.mock_call', lambda *a: ('No', {}, 'mock'))
    with pytest.raises(ValueError, match='approve'):
        run_round(plan, tmp_path, 'mock', 6)
    with pytest.raises(ValueError, match='Next round'):
        run_round(plan, tmp_path, 'mock', 7, True)
    with pytest.raises(ValueError, match='explicitly approved'):
        search_guarded(plan, tmp_path, 'mock')
    with pytest.raises(RuntimeError, match='Total call cap'):
        run_round(plan, tmp_path, 'mock', 6, True, max_calls=1)
    for number in range(6, 8):
        result = run_round(plan, tmp_path, 'mock', number, True, max_calls=150)
        assert result['completed_round'] == number
        state = progress(plan, tmp_path, 'mock')
        assert len(state['memory_ids']) == len(set(state['memory_ids'])) == 2
        memory = read(tmp_path / 'mock' / f'round-{number:02d}/memory.json')
        assert memory['added_ids'] == [] and len(memory['target_ids']) == 2
        if number < 7:
            assert not (tmp_path / 'mock/final_prompt.json').exists()
            assert not (tmp_path / 'mock' / f'round-{number+1:02d}').exists()
    assert read(tmp_path / 'mock/final_prompt.json')['completed_rounds'] == 7
    assert read(tmp_path / 'mock/final_prompt.json')['stop_reason'] == 'patience'
    assert result['stagnation_warning']
    assert run_through(plan, tmp_path, 'mock', 10, 150)['rounds_run'] == []
    assert not (tmp_path / 'mock/round-08').exists()
    with pytest.raises(ValueError, match='already stopped'):
        run_round(plan, tmp_path, 'mock', 8, True)
    with pytest.raises(ValueError, match='Next round'):
        run_round(plan, tmp_path, 'mock', 10, True)
    for f in (tmp_path / 'mock/calls').glob('*.json'):
        req = read(f)['request']
        assert not req['key'].startswith('test/')
        if req['kind'] == 'analysis':
            payload = json.loads(req['user'])
            assert all(not r['correct'] for r in payload['development_cases'])
