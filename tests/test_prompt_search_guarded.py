import json
from pathlib import Path

import pytest

from residue_experiment.prompt_search import prepare, read, search, final_evaluation
from residue_experiment.prompt_search_guarded import choose_memory, eligibility, pick_winner, development_feedback

ROOT = Path(__file__).resolve().parents[1]


def test_gate_requires_correction_without_net_regression():
    before = [{'id': 'bad', 'correct': False}, {'id': 'good', 'correct': True}, {'id': 'other', 'correct': True}]
    assert not eligibility(before, before, ['bad'])['eligible']
    after = [dict(r, correct=True) for r in before]
    assert eligibility(before, after, ['bad'])['eligible']
    after[1]['correct'] = after[2]['correct'] = False
    assert not eligibility(before, after, ['bad'])['eligible']
    with pytest.raises(ValueError):
        eligibility(before, after[:1], ['bad'])


def test_selection_ignores_ineligible_and_ties():
    old = {'name': 'P0', 'prompt': 'p', 'metrics': {'accuracy': .9, 'macro_f1': .9}}
    candidate = {'name': 'c', 'prompt': 'c', 'metrics': {'accuracy': 1, 'macro_f1': 1}, 'gate': {'eligible': False}}
    assert pick_winner(old, [candidate]) == (old, False)
    assert pick_winner(old, [candidate], require_memory_gate=False) == (candidate, True)
    candidate['gate']['eligible'] = True
    assert pick_winner(old, [candidate])[1]
    candidate['metrics']['accuracy'] = .9
    assert pick_winner(old, [candidate]) == (old, False)


def test_memory_is_bounded_and_keeps_correct_labels():
    batch = [{'id': str(i), 'EFSA': 'No' if i % 2 else 'Yes'} for i in range(50)]
    predictions = [{'id': str(i), 'correct': i >= 8} for i in range(50)]
    chosen = choose_memory(batch, predictions, 10)
    assert len(chosen) == len({r['id'] for r in chosen}) == 10
    assert sum(int(r['id']) < 8 for r in chosen) == 6
    assert {r['EFSA'] for r in chosen if int(r['id']) >= 8} == {'Yes', 'No'}


def test_early_stop_resume_final_and_no_leak(tmp_path, monkeypatch):
    config = read(ROOT / 'config.prompt-search-v2.json')
    config.update(pool=str(ROOT / config['pool']), data_dir=str(ROOT / 'data'))
    plan = prepare(config, tmp_path)
    assert plan['expected_calls'] == 3370
    plan['selection'] = plan['selection'][:4]
    plan['test'] = plan['test'][:3]
    plan['batches'] = [b[:6] for b in plan['batches']]
    monkeypatch.setattr('residue_experiment.prompt_search.Provider', lambda *a, **k: pytest.fail('paid call'))
    monkeypatch.setattr('residue_experiment.prompt_search.mock_call', lambda *a: ('No', {}, 'mock'))
    # identical predictions cannot correct targeted errors, so stop at two rounds.
    search(plan, tmp_path, 'mock', through_round=1)
    assert not (tmp_path / 'mock/final_prompt.json').exists()
    final = search(plan, tmp_path, 'mock')
    assert final['completed_rounds'] == 2 and final['stop_reason'] == 'patience'
    assert final['name'] == 'P0'
    assert not (tmp_path / 'mock/round-03').exists()
    folder = tmp_path / 'mock/calls'
    count = len(list(folder.glob('*.json')))
    search(plan, tmp_path, 'mock')
    assert len(list(folder.glob('*.json'))) == count
    # Baseline and selected-candidate predictions for old memory are reused.
    keys = [read(p)['request']['key'] for p in folder.glob('*.json')]
    assert len(keys) == len(set(keys))
    assert not any(k.startswith('test/') for k in keys)
    all_dev = {r['id'] for b in plan['batches'] for r in b}
    for p in folder.glob('*.json'):
        r = read(p)['request']
        if r['kind'] == 'analysis':
            payload = json.loads(r['user'])
            assert {c['id'] for c in payload['accumulated_development_cases']} <= all_dev
        if r['kind'] == 'prediction':
            assert 'EFSA' not in json.loads(r['user'])['test']
    final_evaluation(plan, tmp_path, 'mock')
    assert len(list(folder.glob('*.json'))) == count + 18
    final_evaluation(plan, tmp_path, 'mock')
    assert len(list(folder.glob('*.json'))) == count + 18


def test_development_feedback_records_both_directions():
    fields = dict(substance='s', purpose='p', commodity='c', JMPR='j', EU='e')
    memory = [dict(fields, id='a', EFSA='Yes'), dict(fields, id='b', EFSA='No')]
    old = [{'id': 'a', 'prediction': 'No', 'correct': False},
           {'id': 'b', 'prediction': 'No', 'correct': True}]
    new = [{'id': 'a', 'prediction': 'Yes', 'correct': True},
           {'id': 'b', 'prediction': 'Yes', 'correct': False}]
    f = development_feedback(1, {'name': 'P0', 'prompt': 'old'}, 'C1', 'new',
                             {'change': 'edit', 'risk': 'risk'}, memory, old, new)
    assert f['corrected_count'] == f['regressed_count'] == 1
    assert [c['outcome'] for c in f['changed_cases']] == ['corrected', 'regressed']
    assert '-old' in f['instruction_diff'] and '+new' in f['instruction_diff']


def test_feedback_history_is_development_only_and_resume_stable(tmp_path, monkeypatch):
    config = read(ROOT / 'config.prompt-search-v3.json')
    config.update(pool=str(ROOT / config['pool']), data_dir=str(ROOT / 'data'))
    plan = prepare(config, tmp_path)
    assert plan['expected_calls'] == 3370
    plan['selection'] = plan['selection'][:4]
    plan['test'] = plan['test'][:3]
    plan['batches'] = [b[:6] for b in plan['batches']]
    monkeypatch.setattr('residue_experiment.prompt_search.Provider', lambda *a, **k: pytest.fail('paid call'))
    monkeypatch.setattr('residue_experiment.prompt_search.mock_call', lambda *a: ('No', {}, 'mock'))
    search(plan, tmp_path, 'mock', through_round=1)
    folder = tmp_path / 'mock'
    history = read(folder / 'round-01/development_feedback.json')
    assert len(history) == 3
    search(plan, tmp_path, 'mock')
    payload = read(folder / 'round-02/optimizer_feedback_input.json')
    assert payload['previous_development_feedback'] == history
    dev_ids = {r['id'] for b in plan['batches'] for r in b}
    prohibited = {r['id'] for r in plan['selection'] + plan['test']}
    for item in payload['previous_development_feedback']:
        assert set(item['evaluated_development_ids']) <= dev_ids
        assert not set(item['evaluated_development_ids']) & prohibited
        assert 'metrics' not in item and 'gate' not in item
    assert read(folder / 'round-02/selection.json')['memory_gate_applied'] is False
    count = len(list((folder / 'calls').glob('*.json')))
    search(plan, tmp_path, 'mock')
    assert len(list((folder / 'calls').glob('*.json'))) == count
    final_evaluation(plan, tmp_path, 'mock')
    assert len(list((folder / 'calls').glob('*.json'))) == count + 18
