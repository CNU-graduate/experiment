import hashlib
import json

import pytest

from residue_experiment import e6_j1 as j1
from residue_experiment.instruction_repeats import read_csv
from residue_experiment.runner import run


def test_routes_are_explicit_and_not_item_specific(tmp_path):
    assert j1.route_for('Enforcement') == 'J1-E'
    assert j1.route_for('Risk assessment') == 'J1-R'
    for purpose in ('unknown', '', 'enforcement', None):
        with pytest.raises(ValueError, match='no fallback'):
            j1.route_for(purpose)
    assert j1.PROMPTS['J1-E'] != j1.PROMPTS['J1-R']
    assert all(name not in '\n'.join(j1.PROMPTS.values()) for name in ('Mancozeb', 'Thiamethoxam', '2023-04-03'))
    with pytest.raises(ValueError, match='case_purpose'):
        run({'conditions': ['E6'], 'case_purpose': 'unknown'}, tmp_path/'invalid')


def test_approval_and_protected_outputs_before_prepare(tmp_path, monkeypatch):
    monkeypatch.setattr(j1, 'prepare', lambda: pytest.fail('Unexpected preflight'))
    with pytest.raises(ValueError, match='approve-paid-api'):
        j1.execute(tmp_path/'paid', 'live')
    with pytest.raises(ValueError, match='dedicated J1'):
        j1.execute(j1.guided.DEFAULT_OUTPUT)
    assert not (tmp_path/'paid').exists()


def test_630_cases_partition_purposes_and_keep_all_four_examples(tmp_path, monkeypatch):
    monkeypatch.setattr('residue_experiment.runner.Provider',
                        lambda *a, **k: pytest.fail('Dry-run created API client'))
    files = [p for folder in j1.ablation.HISTORICAL for p in folder.rglob('*') if p.is_file()]
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    out = tmp_path/'j1'
    info = j1.execute(out)
    assert info['cases'] == 630 and info['calls'] == 0 and info['runs'] == 6
    plan = json.loads((out/'plan.json').read_text())
    assert plan['route_counts'] == {'J1-E': 119, 'J1-R': 91}
    original = j1.guided.prompts(j1.ablation.HISTORICAL[0])
    for n in j1.ROUNDS:
        seen = set()
        for c, purpose in j1.ROUTES.items():
            folder = out/'dry-run'/c/f'round-{n:02d}'
            inputs = j1.guided.prompts(folder)
            assert not seen.intersection(inputs)
            seen.update(inputs)
            for ident, value in inputs.items():
                assert value == original[ident]
                assert value['test']['purpose'] == purpose
                assert len(value['examples']) == 4
                assert set(value['test']) == {'substance', 'purpose', 'commodity', 'JMPR', 'EU'}
        assert len(seen) == 210
        assert len([i for i in seen if i.startswith('2023-')]) == 70
        assert len([i for i in seen if i.startswith('2024-')]) == 70
        assert len([i for i in seen if i.startswith('2025-')]) == 70
    summary = read_csv(out/'dry-run/analysis/condition_summary.csv')
    old = next(r for r in summary if r['condition'] == 'E6-guided-historical'
               and r['year'] == 'all' and r['purpose'] == 'all')
    assert float(old['accuracy_mean']) == pytest.approx(613/630)
    assert all(r['accuracy_mean'] == '' for r in summary if r['condition'] == 'J1')
    assert all(hashlib.sha256(p.read_bytes()).hexdigest() == h for p, h in before.items())


def test_fake_live_routes_correct_client_resumes_and_analyzes_without_calls(tmp_path, monkeypatch):
    calls = []
    class FakeProvider:
        def __init__(self, provider, model, config, *, system_prompt):
            assert provider == 'openai' and model == j1.guided.MODEL
            self.route = config['j1_route']
            self.purpose = config['case_purpose']
            assert system_prompt == j1.PROMPTS[self.route]
        def call(self, prompt):
            payload = json.loads(prompt)
            assert payload['test']['purpose'] == self.purpose
            calls.append(self.route)
            return 'Yes', {}, 'fake'
    monkeypatch.setattr('residue_experiment.runner.Provider', FakeProvider)
    out = tmp_path/'j1'
    j1.execute(out, 'live', True, only_round=1)
    assert len(calls) == 210
    freq = read_csv(out/'live/analysis/error_frequency.csv')
    assert all(r['complete'] == 'False' and r['damaged_stable_correct'] == '' for r in freq)
    info = j1.execute(out, 'live', True)
    assert info['cases'] == 630 and len(calls) == 630
    assert calls.count('J1-E') == 357 and calls.count('J1-R') == 273
    j1.execute(out, 'live', True)
    assert len(calls) == 630
    assert j1.execute(out, 'analyze')['calls'] == 0 and len(calls) == 630
    freq = read_csv(out/'live/analysis/error_frequency.csv')
    assert len(freq) == 210 and all(r['complete'] == 'True' and r['valid_runs'] == '3' for r in freq)
    summaries = read_csv(out/'live/analysis/condition_summary.csv')
    overall = next(r for r in summaries if r['condition'] == 'J1' and r['year'] == 'all' and r['purpose'] == 'all')
    assert float(overall['accuracy_mean']) == pytest.approx(125/210)
    plan = json.loads((out/'plan.json').read_text())
    plan['system_prompts']['J1-E'] = 'changed'
    (out/'plan.json').write_text(json.dumps(plan))
    with pytest.raises(ValueError, match='changed'):
        j1.execute(out, 'live', True)
    assert len(calls) == 630 and not (out/'.run.lock').exists()


def test_wrong_purpose_result_and_tampered_response_rejected(tmp_path):
    out = tmp_path/'j1'
    j1.execute(out, 'mock', only_round=1)
    config, historical, _, expected = j1.prepare()
    folder = out/'mock/J1-E/round-01'
    from residue_experiment.evaluation import write_csv
    path = folder/'predictions.csv'
    rows = read_csv(path)
    original = [dict(r) for r in rows]
    rows[0]['id'] = next(iter(expected['J1-R']))
    write_csv(path, rows)
    with pytest.raises(ValueError, match='wrong-purpose'):
        j1.aggregate(out, 'mock', config, historical, expected)
    write_csv(path, original)
    path = folder/'api_calls.csv'
    rows = read_csv(path)
    rows[0]['response'] = 'No' if rows[0]['response'] == 'Yes' else 'Yes'
    write_csv(path, rows)
    with pytest.raises(ValueError, match='saved API response'):
        j1.aggregate(out, 'mock', config, historical, expected)
