import copy
import json

import pytest

from residue_experiment.error_diversity import build_evidence, comparisons, load_plan, prepare, run
from residue_experiment.prompt_search import hash_value, read, save


def fixture_rows():
    rows, predictions = [], []
    for i, (actual, prediction) in enumerate([('No', 'Yes'), ('Yes', 'No'), ('No', 'No'), ('Yes', 'Yes')]):
        rows.append(dict(id=str(i), year='2022', EFSA=actual, substance='x', purpose='risk',
                         commodity='plant', JMPR='parent', EU='parent'))
        predictions.append(dict(id=str(i), actual=actual, prediction=prediction))
    return rows, predictions


def test_evidence_directions_and_missing_groups():
    rows, predictions = fixture_rows()
    evidence = build_evidence(rows, predictions, 10)
    assert evidence['examples_per_group'] == 1
    for name, actual, opposite in [('B', 'No', 'Yes'), ('C', 'Yes', 'No')]:
        pair = evidence[name]['pairs'][0]
        assert pair['target_error']['actual'] == actual
        assert pair['target_error']['p0_prediction'] == opposite
        assert pair['correct_counterexample']['actual'] == opposite
        assert pair['correct_counterexample']['p0_prediction'] == opposite
    predictions[0]['prediction'] = 'No'
    with pytest.raises(ValueError, match='Both error directions'):
        build_evidence(rows, predictions, 10)


def test_pairwise_counts():
    predictions = {n: [dict(id=str(i), actual='No', prediction=p) for i, p in enumerate(ps)]
                   for n, ps in {'P0': ['Yes', 'No', 'Yes'], 'B': ['No', 'Yes', 'Yes'], 'C': ['No', 'No', 'No']}.items()}
    pair = comparisons(predictions)[0]
    assert pair['shared_error_ids'] == ['2']
    assert pair['a_wrong_b_correct_ids'] == ['0']
    assert pair['a_correct_b_wrong_ids'] == ['1']
    assert pair['disagreement_count'] == 2


def test_offline_prepare_freeze_and_run_resume(tmp_path, monkeypatch):
    plan = prepare('results/prompt-search-2023', {'examples_per_direction': 10}, tmp_path)
    assert plan['expected_calls'] == 748
    assert 'test' not in plan and len(plan['development']) == 326
    assert load_plan(tmp_path) == plan
    changed = copy.deepcopy(plan)
    changed['p0'] += 'tampered'
    save(tmp_path / 'plan.json', changed)
    with pytest.raises(ValueError, match='Frozen'):
        load_plan(tmp_path)
    save(tmp_path / 'plan.json', plan)
    rows, _ = fixture_rows()
    plan['development'] = rows
    plan['selection'] = [dict(r, id='selection-' + r['id']) for r in rows]
    plan['expected_calls'] = 18
    plan['plan_hash'] = hash_value(plan)
    monkeypatch.setattr('residue_experiment.prompt_search.Provider', lambda *a, **kw: pytest.fail('Paid call'))
    responses = iter(['Yes', 'No', 'No', 'Yes'] + ['No', 'Yes', 'No', 'Yes'] * 3)
    monkeypatch.setattr('residue_experiment.prompt_search.mock_call', lambda *a: (next(responses), {}, 'mock'))
    result = run(plan, tmp_path, 'mock')
    assert result['calls'] == 18
    assert run(plan, tmp_path, 'mock') == result
    assert len(list((tmp_path / 'mock/calls').glob('*.json'))) == 18
    for path in (tmp_path / 'mock/calls').glob('*.json'):
        request = read(path)['request']
        payload = json.loads(request['user'])
        if request['kind'] == 'generation':
            assert 'selection-' not in request['user']
            assert payload['p0'] == plan['p0']
        else:
            assert payload['examples'] == []
            assert 'EFSA' not in payload['test'] and 'actual' not in payload['test']


def test_call_cap_stops_before_more_calls(tmp_path):
    plan = prepare('results/prompt-search-2023', {'examples_per_direction': 10}, tmp_path)
    with pytest.raises(RuntimeError, match='Total call cap'):
        run(plan, tmp_path, 'mock', max_calls=1)
    assert len(list((tmp_path / 'mock/calls').glob('*.json'))) == 1
