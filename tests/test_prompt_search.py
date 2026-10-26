import copy
import json
from pathlib import Path

import pytest

from residue_experiment.prompt_search import (
    Calls, final_evaluation, hash_value, load_plan, parse_candidates, prepare, read, save, search,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def prepared(tmp_path):
    config = read(ROOT / 'config.prompt-search.json')
    config['pool'] = str(ROOT / config['pool'])
    config['data_dir'] = str(ROOT / 'data')
    return prepare(config, tmp_path), tmp_path


def test_split_and_plan_are_frozen(prepared):
    plan, output = prepared
    assert plan['expected_calls'] == 2920
    assert len(plan['development']) == 326 and len(plan['selection']) == 140
    assert len(plan['test']) == 70
    ids = lambda rows: {r['id'] for r in rows}
    assert not ids(plan['development']) & ids(plan['selection'])
    assert len(ids([r for batch in plan['batches'] for r in batch])) == 250
    assert load_plan(output) == plan
    assert prepare(plan['config'], output) == plan
    changed = copy.deepcopy(plan)
    changed['p0'] += 'tampered'
    save(output / 'plan.json', changed)
    with pytest.raises(ValueError):
        load_plan(output)


def test_mock_search_resume_isolation_and_final(prepared, monkeypatch):
    plan, output = prepared
    # Tiny complete workflow; never instantiate a provider.
    monkeypatch.setattr('residue_experiment.prompt_search.Provider',
                        lambda *a, **k: pytest.fail('Unexpected paid call'))
    plan['config']['rounds'] = 2
    plan['selection'] = plan['selection'][:4]
    plan['batches'] = [b[:6] for b in plan['batches'][:2]]
    plan['test'] = plan['test'][:3]
    search(plan, output, 'mock')
    folder = output / 'mock' / 'calls'
    count = len(list(folder.glob('*.json')))
    search(plan, output, 'mock')
    assert len(list(folder.glob('*.json'))) == count
    for path in folder.glob('*.json'):
        request = read(path)['request']
        assert not request['key'].startswith('test/')
        if request['kind'] == 'prediction':
            payload = json.loads(request['user'])
            assert set(payload['test']) == {'substance', 'purpose', 'commodity', 'JMPR', 'EU'}
            assert payload['examples'] == []
        elif request['kind'] == 'analysis':
            cases = json.loads(request['user'])['development_cases']
            assert len(cases) == 6
    final_evaluation(plan, output, 'mock')
    assert len(list(folder.glob('*.json'))) == count + 18
    final_evaluation(plan, output, 'mock')
    assert len(list(folder.glob('*.json'))) == count + 18


def test_budget_and_uncertain_call_do_not_retry(prepared):
    plan, output = prepared
    calls = Calls(plan, output, 'mock', 1)
    calls.call('first', 'system', 'user', 'prediction')
    assert calls.call('first', 'system', 'user', 'prediction') in ('Yes', 'No')
    with pytest.raises(RuntimeError, match='cap'):
        calls.call('second', 'system', 'user', 'prediction')
    path = calls.attempts / (hash_value('first') + '.json')
    record = read(path)
    record['status'] = 'started'
    save(path, record)
    with pytest.raises(RuntimeError, match='Unresolved'):
        calls.call('first', 'system', 'user', 'prediction')


def test_invalid_candidates_stop():
    with pytest.raises(ValueError):
        parse_candidates('{"candidates":[]}', 3, '')
    with pytest.raises(ValueError, match='Duplicate'):
        parse_candidates(json.dumps({'candidates': [{'prompt': 'same'}] * 3}), 3, '')
