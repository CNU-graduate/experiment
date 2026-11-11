import json

import pytest

from residue_experiment.risk_development import prepare, load_plan, run, SOURCE
from residue_experiment.prompt_search import read, save


def test_frozen_68_reused_79_additional_resume_and_payload(tmp_path, monkeypatch):
    plan = prepare(SOURCE, tmp_path)
    assert len(plan['rows']) == 147
    assert len(plan['reused']) == 68
    assert plan['expected_calls'] == 79
    assert plan == load_plan(tmp_path)
    requests = []

    class FakeProvider:
        def __init__(self, *args, **kwargs):
            assert kwargs['system_prompt'] == plan['prompt']

        def call(self, user):
            payload = json.loads(user)
            assert payload['examples'] == []
            assert set(payload['test']) == {'substance', 'purpose', 'commodity', 'JMPR', 'EU'}
            assert payload['test']['purpose'] == 'Risk assessment'
            requests.append(user)
            return 'Yes', {}, 'fake'

    monkeypatch.setattr('residue_experiment.prompt_search.Provider', FakeProvider)
    with pytest.raises(RuntimeError, match='Total call cap'):
        run(plan, tmp_path, 'live', max_calls=2)
    result = run(plan, tmp_path, 'live', max_calls=79)
    assert result['calls'] == len(requests) == 79
    assert run(plan, tmp_path, 'live', max_calls=79) == result
    assert len(requests) == 79
    for f in (tmp_path / 'live/calls').glob('*.json'):
        record = read(f)
        assert record['request']['key'].split('/')[-1] not in plan['reused']
    assert (tmp_path / 'live/errors.csv').exists()
    plan['prompt'] += 'changed'
    save(tmp_path / 'plan.json', plan)
    with pytest.raises(ValueError, match='changed'):
        load_plan(tmp_path)
