import hashlib
import json

import pytest

from residue_experiment import e6_ablation as ablation
from residue_experiment import e6_guided as guided
from residue_experiment.instruction_repeats import read_csv
from residue_experiment.prompt import SYSTEM


def test_exact_single_block_removal_and_two_round_schedule():
    assert ablation.ROUNDS == (1, 2)
    assert len(ablation.SCHEDULE) == 6 and len(set(ablation.SCHEDULE)) == 6
    for condition, removed in ablation.REMOVED.items():
        text = ablation.PROMPTS[condition]
        assert guided.GUIDED_SYSTEM.count(removed) == 1
        assert text == guided.GUIDED_SYSTEM.replace(removed, '', 1)
        assert text.startswith(SYSTEM + '\n\n')
        assert removed not in text
        assert all(block in text for c, block in ablation.REMOVED.items() if c != condition)


def test_approval_and_output_protection_before_preflight(tmp_path, monkeypatch):
    monkeypatch.setattr(ablation, 'prepare', lambda: pytest.fail('Must reject before prepare'))
    with pytest.raises(ValueError, match='approve-paid-api'):
        ablation.execute(tmp_path/'paid', 'live')
    with pytest.raises(ValueError, match='dedicated'):
        ablation.execute(guided.DEFAULT_OUTPUT)
    with pytest.raises(ValueError, match='round 1/2'):
        ablation.execute(tmp_path/'bad', only_round=3)
    assert not (tmp_path/'paid').exists()


def test_full_dry_run_matches_real_archives_without_clients(tmp_path, monkeypatch):
    monkeypatch.setattr('residue_experiment.runner.Provider',
                        lambda *a, **k: pytest.fail('Dry-run created API client'))
    archives = [p for folder in ablation.HISTORICAL for p in folder.rglob('*') if p.is_file()]
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in archives}
    out = tmp_path/'ablation'
    info = ablation.execute(out)
    assert info['cases'] == 1260 and info['calls'] == 0 and info['runs'] == 6
    plan = json.loads((out/'plan.json').read_text())
    assert plan['rounds'] == [1, 2] and plan['historical_rounds'] == 3
    for c, n in ablation.SCHEDULE:
        folder = out/'dry-run'/c/f'round-{n:02d}'
        rows = read_csv(folder/'predictions.csv')
        assert len(rows) == 210 and {r['status'] for r in rows} == {'planned'}
        assert ablation.examples(folder) == ablation.examples(ablation.HISTORICAL[0])
        for line in (folder/'prompts.jsonl').read_text().splitlines():
            payload = json.loads(json.loads(line)['prompt'])
            assert len(payload['examples']) == 4
            assert set(payload['test']) == {'substance', 'purpose', 'commodity', 'JMPR', 'EU'}
    summary = read_csv(out/'dry-run/analysis/condition_summary.csv')
    old = next(r for r in summary if r['historical'] == 'True' and r['year'] == 'all')
    assert float(old['accuracy_mean']) == pytest.approx(613/630)
    new = [r for r in summary if r['historical'] == 'False']
    assert all(r['repeats_planned'] == '2' and r['accuracy_mean'] == '' for r in new)
    assert all(hashlib.sha256(p.read_bytes()).hexdigest() == h for p, h in before.items())


def test_archive_drift_blocks_paid_client(tmp_path, monkeypatch):
    original = guided.prompts
    def drift(folder):
        result = original(folder)
        if folder == ablation.HISTORICAL[1]:
            next(iter(result.values()))['examples'].reverse()
        return result
    monkeypatch.setattr(guided, 'prompts', drift)
    monkeypatch.setattr('residue_experiment.runner.Provider',
                        lambda *a, **k: pytest.fail('Client must not be created'))
    with pytest.raises(ValueError, match='user inputs differ'):
        ablation.execute(tmp_path/'bad', 'live', True)


def test_fake_live_two_rounds_resume_and_analysis(tmp_path, monkeypatch):
    calls = []
    class FakeProvider:
        def __init__(self, provider, model, cfg, *, system_prompt):
            assert provider == 'openai' and model == guided.MODEL
            assert cfg['ablation_condition'] == 'G1' and cfg['ablation_round'] in (1, 2)
            assert system_prompt == ablation.PROMPTS['G1']
        def call(self, prompt):
            calls.append(prompt)
            return 'Yes', {}, 'fake'
    monkeypatch.setattr('residue_experiment.runner.Provider', FakeProvider)
    out = tmp_path/'ablation'
    ablation.execute(out, 'live', True, condition='G1', only_round=1)
    incomplete = read_csv(out/'live/analysis/error_frequency.csv')
    assert all(r['damaged_stable_correct'] == '' for r in incomplete)
    info = ablation.execute(out, 'live', True, condition='G1')
    assert info['runs'] == 2 and len(calls) == 420
    ablation.execute(out, 'live', True, condition='G1')
    assert len(calls) == 420
    assert ablation.execute(out, 'analyze')['calls'] == 0 and len(calls) == 420
    freq = [r for r in read_csv(out/'live/analysis/error_frequency.csv') if r['condition'] == 'G1']
    assert len(freq) == 210 and all(r['valid_runs'] == '2' and r['complete'] == 'True' for r in freq)
    # Fake Yes responses recover stable historical Yes errors and damage stable No answers.
    assert all(r['recovered_repeat_error'] == 'True' for r in freq
               if r['actual'] == 'Yes' and int(r['historical_wrong_count']) >= 2)
    assert all(r['damaged_stable_correct'] == 'True' for r in freq
               if r['actual'] == 'No' and r['historical_wrong_count'] == '0')
    assert not (out/'live/G1/round-03').exists()
    plan = json.loads((out/'plan.json').read_text())
    plan['system_prompts']['G1'] = 'changed'
    (out/'plan.json').write_text(json.dumps(plan))
    with pytest.raises(ValueError, match='changed'):
        ablation.execute(out, 'live', True, condition='G1')
    assert len(calls) == 420 and not (out/'.run.lock').exists()


def test_tampered_raw_response_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr('residue_experiment.runner.Provider',
                        lambda *a, **k: pytest.fail('Mock must not create SDK'))
    out = tmp_path/'ablation'
    ablation.execute(out, 'mock', condition='G2', only_round=1)
    path = out/'mock/G2/round-01/api_calls.csv'
    rows = read_csv(path)
    rows[0]['response'] = 'No' if rows[0]['response'] == 'Yes' else 'Yes'
    from residue_experiment.evaluation import write_csv
    write_csv(path, rows)
    config, historical, _, expected = ablation.prepare()
    with pytest.raises(ValueError, match='saved successful API response'):
        ablation.aggregate(out, 'mock', config, historical, expected)
