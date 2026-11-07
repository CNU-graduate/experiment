import hashlib
import json

import pytest

from residue_experiment import e6_h1 as h1
from residue_experiment.instruction_repeats import read_csv


def test_only_first_added_paragraph_replaced():
    assert h1.PROMPTS['C0'] == h1.guided.GUIDED_SYSTEM
    assert h1.PROMPTS['H1'] == h1.PROMPTS['C0'].replace(h1.ablation.REMOVED['G1'], h1.REPLACEMENT, 1)
    assert all(block in h1.PROMPTS['H1'] for c, block in h1.ablation.REMOVED.items() if c != 'G1')
    assert len(h1.SCHEDULE) == len(set(h1.SCHEDULE)) == 6
    assert {n for _, n in h1.SCHEDULE} == {1, 2, 3}
    assert 'Mancozeb' not in h1.REPLACEMENT and 'Thiamethoxam' not in h1.REPLACEMENT


def test_approval_and_protected_paths_before_prepare(tmp_path, monkeypatch):
    monkeypatch.setattr(h1, 'prepare', lambda: pytest.fail('Unexpected prepare'))
    with pytest.raises(ValueError, match='approve-paid-api'):
        h1.execute(tmp_path/'paid', 'live')
    with pytest.raises(ValueError, match='dedicated H1'):
        h1.execute(h1.guided.DEFAULT_OUTPUT)


def test_full_1260_case_dry_run_preserves_archives(tmp_path, monkeypatch):
    monkeypatch.setattr('residue_experiment.runner.Provider',
                        lambda *a, **k: pytest.fail('Dry-run created SDK client'))
    files = [p for folder in h1.ablation.HISTORICAL for p in folder.rglob('*') if p.is_file()]
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    out = tmp_path/'h1'
    info = h1.execute(out)
    assert info['cases'] == 1260 and info['calls'] == 0 and info['runs'] == 6
    for c, n in h1.SCHEDULE:
        folder = out/'dry-run'/c/f'round-{n:02d}'
        rows = read_csv(folder/'predictions.csv')
        assert len(rows) == 210 and {r['status'] for r in rows} == {'planned'}
        assert h1.ablation.examples(folder) == h1.ablation.examples(h1.ablation.HISTORICAL[0])
        for line in (folder/'prompts.jsonl').read_text().splitlines():
            payload = json.loads(json.loads(line)['prompt'])
            assert len(payload['examples']) == 4
            assert set(payload['test']) == {'substance', 'purpose', 'commodity', 'JMPR', 'EU'}
    assert all(hashlib.sha256(p.read_bytes()).hexdigest() == v for p, v in before.items())
    summaries = read_csv(out/'dry-run/analysis/condition_summary.csv')
    assert all(r['repeats_complete'] == '0' and r['accuracy_mean'] == '' for r in summaries)


def test_fake_live_three_round_comparison_resume_and_no_call_analysis(tmp_path, monkeypatch):
    calls = []
    class FakeProvider:
        def __init__(self, provider, model, cfg, *, system_prompt):
            assert provider == 'openai' and model == h1.guided.MODEL
            self.condition = cfg['h1_condition']
            assert system_prompt == h1.PROMPTS[self.condition]
        def call(self, prompt):
            calls.append(self.condition)
            return ('Yes' if self.condition == 'H1' else 'No'), {}, 'fake'
    monkeypatch.setattr('residue_experiment.runner.Provider', FakeProvider)
    out = tmp_path/'h1'
    h1.execute(out, 'live', True, only_round=1)
    rows = read_csv(out/'live/analysis/error_frequency.csv')
    assert all(r['complete'] == 'False' and r['recovered_repeat_error'] == '' for r in rows)
    h1.execute(out, 'live', True)
    assert len(calls) == 1260 and calls.count('H1') == calls.count('C0') == 630
    h1.execute(out, 'live', True)
    assert len(calls) == 1260
    assert h1.execute(out, 'analyze')['calls'] == 0 and len(calls) == 1260
    rows = read_csv(out/'live/analysis/error_frequency.csv')
    assert len(rows) == 210 and all(r['complete'] == 'True' for r in rows)
    assert all(r['recovered_repeat_error'] == 'True' for r in rows if r['actual'] == 'Yes')
    assert all(r['damaged_stable_correct'] == 'True' for r in rows if r['actual'] == 'No')
    plan = json.loads((out/'plan.json').read_text())
    plan['replacement'] = 'changed'
    (out/'plan.json').write_text(json.dumps(plan))
    with pytest.raises(ValueError, match='changed'):
        h1.execute(out, 'live', True)
    assert len(calls) == 1260 and not (out/'.run.lock').exists()


def test_tampered_response_is_not_scored(tmp_path):
    out = tmp_path/'h1'
    h1.execute(out, 'mock', condition='H1', only_round=1)
    path = out/'mock/H1/round-01/api_calls.csv'
    rows = read_csv(path)
    rows[0]['response'] = 'No' if rows[0]['response'] == 'Yes' else 'Yes'
    from residue_experiment.evaluation import write_csv
    write_csv(path, rows)
    config, _, expected = h1.prepare()
    with pytest.raises(ValueError, match='saved response'):
        h1.aggregate(out, 'mock', config, expected)
