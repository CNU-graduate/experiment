import json
from collections import Counter

import pytest
from residue_experiment import e6_purpose_control as control
from residue_experiment.instruction_repeats import read_csv


def test_matched_rules_and_balanced_schedule():
    assert control.PROMPTS['K1'] == {r: control.j1.guided.GUIDED_SYSTEM for r in control.j1.ROUTES}
    assert control.PROMPTS['K3'] == control.j1.PROMPTS
    assert control.j1.ENFORCEMENT in control.COMBINED and control.j1.RISK in control.COMBINED
    assert 'do not apply the inactive module' in control.COMBINED
    assert len(control.SCHEDULE) == 18
    for c in control.CONDITIONS:
        assert Counter(n for cc, r, n in control.SCHEDULE if cc == c) == {1: 2, 2: 2, 3: 2}
    assert [control.SCHEDULE[i][0] for i in range(0, 18, 2)] == [
        'K1', 'K2', 'K3', 'K2', 'K3', 'K1', 'K3', 'K1', 'K2']


def test_protection_before_preflight(tmp_path, monkeypatch):
    monkeypatch.setattr(control, 'prepare', lambda: pytest.fail('Unexpected preflight'))
    with pytest.raises(ValueError, match='approve-paid-api'):
        control.execute(tmp_path/'paid', 'live')
    with pytest.raises(ValueError, match='dedicated controlled'):
        control.execute(control.j1.DEFAULT_OUTPUT)


def test_dry_run_1890_same_inputs_no_api(tmp_path, monkeypatch):
    monkeypatch.setattr('residue_experiment.runner.Provider', lambda *a, **k: pytest.fail('API client'))
    out = tmp_path/'control'
    info = control.execute(out)
    assert (info['cases'], info['calls'], info['full_evaluations'], info['purpose_subruns']) == (1890, 0, 9, 18)
    original = control.j1.guided.prompts(control.j1.ablation.HISTORICAL[0])
    for c in control.CONDITIONS:
        for n in (1, 2, 3):
            seen = set()
            for r, purpose in control.j1.ROUTES.items():
                folder = out/c/'dry-run'/r/f'round-{n:02d}'
                inputs = control.j1.guided.prompts(folder)
                assert not seen.intersection(inputs)
                seen.update(inputs)
                assert inputs == {i: original[i] for i in inputs}
                assert all(x['test']['purpose'] == purpose and len(x['examples']) == 4 for x in inputs.values())
            assert len(seen) == 210
    summary = read_csv(out/'dry-run/analysis/condition_summary.csv')
    assert {r['condition'] for r in summary} == set(control.CONDITIONS)
    assert all(r['accuracy_mean'] == '' for r in summary)


def test_fake_live_resume_analysis_and_drift(tmp_path, monkeypatch):
    calls = []
    class FakeProvider:
        def __init__(self, provider, model, config, *, system_prompt):
            self.condition = config['purpose_control_condition']
            self.purpose = config['case_purpose']
            assert system_prompt == control.PROMPTS[self.condition][config['j1_route']]
        def call(self, prompt):
            assert json.loads(prompt)['test']['purpose'] == self.purpose
            calls.append(self.condition)
            return 'Yes', {}, 'fake'
    monkeypatch.setattr('residue_experiment.runner.Provider', FakeProvider)
    out = tmp_path/'control'
    control.execute(out, 'live', True, only_round=1)
    assert len(calls) == 630
    assert all(r['n_complete'] == '0' for r in read_csv(out/'live/analysis/comparison.csv'))
    control.execute(out, 'live', True)
    assert Counter(calls) == {c: 630 for c in control.CONDITIONS}
    control.execute(out, 'live', True)
    control.execute(out, 'analyze')
    assert len(calls) == 1890
    assert all(r['n_complete'] == '210' for r in read_csv(out/'live/analysis/comparison.csv'))
    summary = read_csv(out/'live/analysis/condition_summary.csv')
    overall = [r for r in summary if r['year'] == r['purpose'] == 'all']
    assert len(overall) == 3
    assert all(float(r['accuracy_mean']) == pytest.approx(125/210) for r in overall)
    plan = json.loads((out/'plan.json').read_text())
    plan['total_cases'] = 0
    (out/'plan.json').write_text(json.dumps(plan))
    with pytest.raises(ValueError, match='changed'):
        control.execute(out, 'live', True)
    assert len(calls) == 1890 and not (out/'.run.lock').exists()


def test_selected_conditions_only_and_invalid_selection(tmp_path, monkeypatch):
    calls = []
    class FakeProvider:
        def __init__(self, provider, model, config, *, system_prompt):
            self.condition = config['purpose_control_condition']
            assert self.condition in ('K2', 'K3')
        def call(self, prompt):
            calls.append(self.condition)
            return 'Yes', {}, 'fake'
    monkeypatch.setattr('residue_experiment.runner.Provider', FakeProvider)
    out = tmp_path/'selected'
    info = control.execute(out, 'live', True, conditions=['K2', 'K3'])
    assert info['cases'] == 1260 and info['full_evaluations'] == 6
    assert info['purpose_subruns'] == 12
    assert Counter(calls) == {'K2': 630, 'K3': 630}
    assert not (out/'K1/live/J1-E').exists()
    rows = read_csv(out/'live/analysis/condition_summary.csv')
    assert all(r['repeats_complete'] == '0' for r in rows if r['condition'] == 'K1')
    comparison = read_csv(out/'live/analysis/comparison.csv')
    assert next(r for r in comparison if r['reference'] == 'K2')['n_complete'] == '210'
    control.execute(out, 'live', True, conditions=['K2', 'K3'])
    assert len(calls) == 1260
    for invalid in ([], ['K4'], ['K2', 'K2']):
        with pytest.raises(ValueError, match='distinct conditions'):
            control.execute(tmp_path/'invalid', conditions=invalid)
