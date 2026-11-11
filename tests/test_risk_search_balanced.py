import json
import shutil
from collections import Counter

import pytest

from residue_experiment.risk_search import load_plan, select_seven_three, compile_candidates, run
from residue_experiment.prompt_search import read


def test_constrained_candidate_keeps_existing_instruction_verbatim():
    current = 'Enforcement rule.\nRisk assessment rule.\nReturn Yes or No.\n'
    raw = json.dumps({'candidates': [
        {'prompt': 'DO NOT USE THIS REPLACEMENT', 'risk_assessment_rule': 'Compare applicable scopes.'},
        {'prompt': 'second'}, {'prompt': 'third'}]})
    candidates = compile_candidates(raw, current, '\nGUARD', True)
    assert candidates[0] == current + '\n\nFor Risk assessment only (not Enforcement):\nCompare applicable scopes.'
    assert candidates[1:] == ['second\nGUARD', 'third\nGUARD']
    with pytest.raises(ValueError, match='risk_assessment_rule'):
        compile_candidates(json.dumps({'candidates': [{'prompt': 'x'}, {'prompt': 'y'}, {'prompt': 'z'}]}), current, '', True)


def test_fixed_quotas_and_current_error_status():
    plan = load_plan('results/r6c1-risk-search-balanced')
    assert Counter(r['purpose'] for r in plan['optimizer_cases']) == {'Risk assessment': 7, 'Enforcement': 3}
    assert {r['id'] for r in plan['optimizer_cases']} <= {r['id'] for r in plan['batches'][0]}
    batch = plan['batches'][1]
    preds = [{'id': r['id'], 'correct': r['EFSA'] == 'Yes'} for r in batch]
    chosen = select_seven_three(batch, preds, plan['optimizer_excluded_ids'])
    assert len({r['id'] for r in chosen}) == 10
    assert Counter(r['purpose'] for r in chosen) == {'Risk assessment': 7, 'Enforcement': 3}
    assert not {r['id'] for r in chosen} & set(plan['optimizer_excluded_ids'])
    assert select_seven_three(batch, [{'id': r['id'], 'correct': True} for r in batch], []) == []


def test_balanced_rounds_mock_resume_and_scope(tmp_path, monkeypatch):
    root = 'results/r6c1-risk-search-balanced'
    plan = load_plan(root)
    shutil.copyfile(root + '/seed_cache.json', tmp_path / 'seed_cache.json')
    monkeypatch.setattr('residue_experiment.prompt_search.Provider', lambda *a, **kw: pytest.fail('Paid API'))
    monkeypatch.setattr('residue_experiment.prompt_search.mock_call', lambda *a: ('Yes', {}, 'mock'))
    run(plan, tmp_path, 'mock', 3650, through_round=1)
    result = run(plan, tmp_path, 'mock', 3650)
    assert result['completed_rounds'] == 2 and result['stop_reason'] == 'patience'
    for n in (1, 2):
        folder = tmp_path / 'mock' / f'round-{n:02d}'
        cases = read(folder / 'optimizer_input.json')['development_cases']
        assert Counter(r['purpose'] for r in cases) == {'Risk assessment': 7, 'Enforcement': 3}
        prompt = read(folder / 'candidates.json')['prompts'][0]
        assert prompt.startswith(plan['start_prompt'] + '\n\nFor Risk assessment only (not Enforcement):\n')
        assert 'risk_assessment_rule' in read(folder / 'generation_input.json')['task']
    assert run(plan, tmp_path, 'mock', 3650) == result
