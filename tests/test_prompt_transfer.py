import json
import pytest
from residue_experiment.prompt_transfer import prepare, load_plan, run
from residue_experiment.prompt_search import read, save


def test_prepare_frozen_winner(tmp_path):
    plan = prepare('results/prompt-search-2023-v2', tmp_path)
    assert plan['expected_calls'] == 840
    assert plan['final_name'] == 'R4C2'
    assert len(plan['tests']['2024']) == len(plan['tests']['2025']) == 70
    assert plan == load_plan(tmp_path)
    plan['final_prompt'] += 'tampered'
    save(tmp_path / 'plan.json', plan)
    with pytest.raises(ValueError, match='changed'):
        load_plan(tmp_path)


def test_mock_resume_budget_and_no_label_leakage(tmp_path, monkeypatch):
    plan = prepare('results/prompt-search-2023-v2', tmp_path)
    plan['tests'] = {y: rows[:2] for y, rows in plan['tests'].items()}
    monkeypatch.setattr('residue_experiment.prompt_search.Provider', lambda *a, **kw: pytest.fail('Paid call'))
    with pytest.raises(RuntimeError, match='Total call cap'):
        run(plan, tmp_path, 'mock', max_calls=1)
    result = run(plan, tmp_path, 'mock', max_calls=24)
    assert result['calls'] == 24
    assert run(plan, tmp_path, 'mock', max_calls=24) == result
    for path in (tmp_path / 'mock/calls').glob('*.json'):
        req = read(path)['request']
        assert req['kind'] == 'prediction'
        assert req['system'] in (plan['p0'], plan['final_prompt'])
        payload = json.loads(req['user'])
        assert payload['examples'] == []
        assert set(payload['test']) == {'substance', 'purpose', 'commodity', 'JMPR', 'EU'}
    assert (tmp_path / 'mock/2024/test_changes.csv').exists()
    assert (tmp_path / 'mock/2025/test_summary.json').exists()
